from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import httpx
from typing import Dict, Any
from config import settings
from cache import cache_service
from embeddings import embedding_service
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Cache", version="0.1.0")

# CORS для dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Загрузка модели при старте"""
    logger.info("=" * 60)
    logger.info("🚀 ECHO - Система кеширования AI-ответов")
    logger.info("=" * 60)
    logger.info("Загрузка модели эмбеддингов...")
    embedding_service.load_model()
    logger.info("✓ Модель загружена!")
    logger.info("")
    
    # Проверяем setup
    setup_completed = cache_service.redis_client.get("setup_completed")
    if not setup_completed:
        logger.info("⚠️  ТРЕБУЕТСЯ ПЕРВОНАЧАЛЬНАЯ НАСТРОЙКА")
        logger.info("")
        logger.info("📍 Откройте в браузере:")
        logger.info("   • Локально:  http://localhost:8000")
        logger.info("   • По сети:   http://<ваш-ip>:8000")
        logger.info("")
        logger.info("Следуйте инструкциям мастера настройки (3 шага)")
    else:
        logger.info("✓ Настройка завершена")
        logger.info("")
        logger.info("📍 Панель управления доступна:")
        logger.info("   • Локально:  http://localhost:8000")
        logger.info("   • По сети:   http://<ваш-ip>:8000")
    
    logger.info("")
    logger.info("=" * 60)

@app.get("/")
async def root(request: Request):
    """Redirect to dashboard or setup"""
    # Проверяем, завершена ли настройка
    try:
        setup_completed = cache_service.redis_client.get("setup_completed")
        if not setup_completed:
            setup_path = Path("/app/setup.html")
            if setup_path.exists():
                with open(setup_path, "r") as f:
                    return HTMLResponse(content=f.read())
    except:
        pass
    
    # Проверяем авторизацию
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        session = cache_service.redis_client.get(f"session:{token}")
        if session:
            # Авторизован - показываем dashboard
            dashboard_path = Path("/app/dashboard.html")
            if dashboard_path.exists():
                with open(dashboard_path, "r") as f:
                    return HTMLResponse(content=f.read())
    
    # Не авторизован - редирект на login
    return HTMLResponse(content="""
        <script>
            const token = localStorage.getItem('auth_token');
            if (token) {
                fetch('/', {
                    headers: { 'Authorization': 'Bearer ' + token }
                }).then(r => r.text()).then(html => {
                    document.open();
                    document.write(html);
                    document.close();
                });
            } else {
                window.location.href = '/login';
            }
        </script>
    """)

@app.post("/setup")
async def setup(request: Request):
    """Первоначальная настройка"""
    body = await request.json()
    
    # Сохраняем настройки API
    settings.upstream_api_url = body.get("upstream_api_url", settings.upstream_api_url)
    settings.upstream_api_key = body.get("upstream_api_key", "")
    settings.cache_threshold = float(body.get("cache_threshold", 0.88))
    settings.cache_ttl = int(body.get("cache_ttl", 3600))
    settings.enable_semantic = bool(body.get("enable_semantic", True))
    settings.save_to_redis()
    
    # Сохраняем логин/пароль
    import hashlib
    username = body.get("username", "admin")
    password = body.get("password", "")
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    cache_service.redis_client.set("auth_username", username)
    cache_service.redis_client.set("auth_password", password_hash)
    cache_service.redis_client.set("setup_completed", "true")
    
    return {"message": "Setup completed"}

@app.get("/login")
async def login_page():
    """Страница логина"""
    login_path = Path("/app/login.html")
    if login_path.exists():
        with open(login_path, "r") as f:
            return HTMLResponse(content=f.read())
    return {"error": "Login page not found"}

@app.post("/login")
async def login(request: Request):
    """Авторизация"""
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    
    # Проверяем логин/пароль
    import hashlib
    stored_username = cache_service.redis_client.get("auth_username")
    stored_password = cache_service.redis_client.get("auth_password")
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    if username == stored_username and password_hash == stored_password:
        # Генерируем простой токен
        import secrets
        token = secrets.token_urlsafe(32)
        cache_service.redis_client.setex(f"session:{token}", 86400, username)  # 24 часа
        return {"token": token, "message": "Login successful"}
    
    return JSONResponse(status_code=401, content={"message": "Неверный логин или пароль"})

@app.get("/dashboard")
async def dashboard():
    """Web dashboard"""
    dashboard_path = Path("/app/dashboard.html")
    if dashboard_path.exists():
        with open(dashboard_path, "r") as f:
            return HTMLResponse(content=f.read())
    return {"error": "Dashboard not found"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

def check_auth(request: Request):
    """Проверка авторизации"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    token = auth_header.replace("Bearer ", "")
    session = cache_service.redis_client.get(f"session:{token}")
    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")
    return session

@app.get("/stats")
async def get_stats(request: Request):
    """Статистика кеша"""
    check_auth(request)
    stats = cache_service.get_stats()
    # Добавляем Redis info
    try:
        info = cache_service.redis_client.info('keyspace')
        db_info = info.get('db0', {})
        stats['redis_keys'] = db_info.get('keys', 0)
        stats['redis_expires'] = db_info.get('expires', 0)
    except:
        stats['redis_keys'] = 0
        stats['redis_expires'] = 0
    return stats

@app.post("/cache/clear")
async def clear_cache(request: Request):
    """Очистка кеша"""
    check_auth(request)
    cache_service.clear_cache()
    return {"message": "Cache cleared"}

@app.get("/config")
async def get_config(request: Request):
    """Получение текущих настроек"""
    check_auth(request)
    return {
        "upstream_api_url": settings.upstream_api_url,
        "upstream_api_key": settings.upstream_api_key if hasattr(settings, 'upstream_api_key') else "",
        "cache_threshold": settings.cache_threshold,
        "cache_ttl": settings.cache_ttl,
        "enable_semantic": settings.enable_semantic
    }

@app.post("/config")
async def update_config(request: Request):
    """Обновление настроек"""
    check_auth(request)
    body = await request.json()
    
    if "upstream_api_url" in body:
        settings.upstream_api_url = body["upstream_api_url"]
    if "upstream_api_key" in body:
        settings.upstream_api_key = body["upstream_api_key"]
    if "cache_threshold" in body:
        settings.cache_threshold = float(body["cache_threshold"])
    if "cache_ttl" in body:
        settings.cache_ttl = int(body["cache_ttl"])
    if "enable_semantic" in body:
        settings.enable_semantic = bool(body["enable_semantic"])
    
    settings.save_to_redis()
    return {"message": "Config updated", "config": {
        "upstream_api_url": settings.upstream_api_url,
        "cache_threshold": settings.cache_threshold,
        "cache_ttl": settings.cache_ttl,
        "enable_semantic": settings.enable_semantic
    }}

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Основной эндпоинт - прокси с кешированием"""
    try:
        body = await request.json()
        messages = body.get("messages", [])
        
        cache_service.stats["total_requests"] += 1
        cache_service._save_stats()
        
        # Проверка exact match
        cached_response = cache_service.get_exact_match(messages)
        if cached_response:
            cache_service.stats["cache_hits"] += 1
            tokens = cached_response.get("usage", {}).get("total_tokens", 0)
            cache_service.stats["tokens_saved"] += tokens
            cache_service._save_stats()
            logger.info(f"Cache HIT (exact) - saved {tokens} tokens")
            return JSONResponse(content=cached_response)
        
        # Проверка semantic match
        if messages:
            last_message = messages[-1].get("content", "")
            if last_message:
                cached_response = cache_service.get_semantic_match(last_message)
                if cached_response:
                    cache_service.stats["cache_hits"] += 1
                    tokens = cached_response.get("usage", {}).get("total_tokens", 0)
                    cache_service.stats["tokens_saved"] += tokens
                    cache_service._save_stats()
                    logger.info(f"Cache HIT (semantic) - saved {tokens} tokens")
                    return JSONResponse(content=cached_response)
                else:
                    logger.info(f"Semantic search: no match found (threshold: {settings.cache_threshold})")
        
        # Cache miss - запрос к upstream API
        cache_service.stats["cache_misses"] += 1
        cache_service._save_stats()
        logger.info("Cache MISS - forwarding to upstream API")
        
        # Получаем Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        # Прокси запрос
        async with httpx.AsyncClient(timeout=60.0) as client:
            upstream_url = f"{settings.upstream_api_url}/chat/completions"
            
            response = await client.post(
                upstream_url,
                json=body,
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Upstream API error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail=response.text)
            
            response_data = response.json()
            
            # Сохраняем в кеш
            cache_service.set_cache(messages, response_data)
            
            tokens = response_data.get("usage", {}).get("total_tokens", 0)
            logger.info(f"Response from upstream - {tokens} tokens")
            
            return JSONResponse(content=response_data)
    
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/completions")
async def completions(request: Request):
    """Completions endpoint (legacy)"""
    return await chat_completions(request)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
