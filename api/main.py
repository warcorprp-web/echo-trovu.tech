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
import hashlib
import time
import json

logging.basicConfig(
    level=logging.WARNING,
    format='%(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI(title="ECHO", version="1.0.0", docs_url=None, redoc_url=None)

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
    import os
    import urllib.request
    
    print("\n" + "=" * 70)
    print("███████╗ ██████╗██╗  ██╗ ██████╗ ")
    print("██╔════╝██╔════╝██║  ██║██╔═══██╗")
    print("█████╗  ██║     ███████║██║   ██║")
    print("██╔══╝  ██║     ██╔══██║██║   ██║")
    print("███████╗╚██████╗██║  ██║╚██████╔╝")
    print("╚══════╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ")
    print("")
    print("Система кеширования AI-ответов")
    print("https://trovu.tech/echo")
    print("")
    print("(c) 2026 Trovu.Tech - All Rights Reserved")
    print("=" * 70)
    print("")
    
    import logging
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    
    print("[*] Загрузка модели эмбеддингов...")
    embedding_service.load_model()
    print("[+] Модель загружена")
    print("")
    
    print("[*] Загрузка Faiss индекса...")
    cache_service._load_faiss_index()
    print("[+] Faiss индекс загружен")
    print("")
    
    server_ip = os.getenv('SERVER_IP')
    if not server_ip:
        try:
            server_ip = urllib.request.urlopen('https://api.ipify.org', timeout=2).read().decode('utf8')
        except:
            server_ip = None
    
    setup_completed = cache_service.redis_client.get("setup_completed")
    
    if not setup_completed:
        print("[!] ТРЕБУЕТСЯ ПЕРВОНАЧАЛЬНАЯ НАСТРОЙКА")
        print("")
        print("Откройте в браузере:")
        print("  -> http://localhost:8000")
        if server_ip:
            print(f"  -> http://{server_ip}:8000")
        print("")
        print("Следуйте инструкциям мастера настройки (3 шага)")
    else:
        print("[+] Настройка завершена")
        print("")
        print("Панель управления доступна:")
        print("  -> http://localhost:8000")
        if server_ip:
            print(f"  -> http://{server_ip}:8000")
    
    print("")
    print("=" * 70)
    print("")
    print("Нажмите D для detach (контейнер продолжит работать)")
    print("")

@app.get("/")
async def root(request: Request):
    """Redirect to dashboard or setup"""
    try:
        setup_completed = cache_service.redis_client.get("setup_completed")
        if not setup_completed:
            setup_path = Path("/app/setup.html")
            if setup_path.exists():
                with open(setup_path, "r") as f:
                    return HTMLResponse(content=f.read())
    except:
        pass
    
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        session = cache_service.redis_client.get(f"session:{token}")
        if session:
            dashboard_path = Path("/app/dashboard.html")
            if dashboard_path.exists():
                with open(dashboard_path, "r") as f:
                    return HTMLResponse(content=f.read())
    
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
    setup_completed = cache_service.redis_client.get("setup_completed")
    if setup_completed:
        raise HTTPException(status_code=403, detail="Setup already completed")
    
    body = await request.json()
    
    upstream_url = body.get("upstream_api_url", settings.upstream_api_url)
    if upstream_url.endswith("/chat/completions"):
        upstream_url = upstream_url[:-len("/chat/completions")]
    if upstream_url.endswith("/completions"):
        upstream_url = upstream_url[:-len("/completions")]
    
    settings.upstream_api_url = upstream_url
    settings.upstream_api_key = body.get("upstream_api_key", "")
    settings.cache_threshold = float(body.get("cache_threshold", 0.88))
    settings.cache_ttl = int(body.get("cache_ttl", 3600))
    settings.enable_semantic = bool(body.get("enable_semantic", True))
    settings.save_to_redis()
    
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
    
    import hashlib
    stored_username = cache_service.redis_client.get("auth_username")
    stored_password = cache_service.redis_client.get("auth_password")
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    if username == stored_username and password_hash == stored_password:
        import secrets
        token = secrets.token_urlsafe(32)
        cache_service.redis_client.setex(f"session:{token}", 86400, username)
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

def _construct_stream_from_cache(content: str, model: str):
    """Создает SSE stream из кешированного контента"""
    created = int(time.time())
    chunk_id = f"chatcmpl-{hashlib.md5(content.encode()).hexdigest()[:8]}"
    
    yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"
    
    yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]})}\n\n"
    
    yield f"data: {json.dumps({'id': chunk_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
    
    yield "data: [DONE]\n\n"

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Основной эндпоинт - прокси с кешированием"""
    try:
        body = await request.json()
        messages = body.get("messages", [])
        is_stream = body.get('stream', False)
        
        cache_service.stats["total_requests"] += 1
        cache_service._save_stats()
        
        should_cache = cache_service._should_cache(body)
        
        if not should_cache:
            logger.info(f"Cache SKIP - temperature={body.get('temperature', 0.0)}, stream={is_stream}")
            cache_service.stats["cache_misses"] += 1
            cache_service._save_stats()
        else:
            cached_response = cache_service.get_exact_match(messages)
            if cached_response:
                cache_service.stats["cache_hits"] += 1
                tokens = cached_response.get("usage", {}).get("total_tokens", 0)
                cache_service.stats["tokens_saved"] += tokens
                cache_service._save_stats()
                logger.info(f"Cache HIT (exact) - saved {tokens} tokens")
                
                if is_stream:
                    content = cached_response['choices'][0]['message']['content']
                    model = cached_response.get('model', body.get('model', 'gpt-3.5-turbo'))
                    return StreamingResponse(_construct_stream_from_cache(content, model), media_type="text/event-stream")
                
                return JSONResponse(content=cached_response)
            
            if messages:
                user_content = cache_service._extract_user_content(messages)
                if user_content:
                    temperature = body.get('temperature', 0.0)
                    cached_response = cache_service.get_semantic_match(user_content, temperature=temperature)
                    if cached_response:
                        cache_service.stats["cache_hits"] += 1
                        tokens = cached_response.get("usage", {}).get("total_tokens", 0)
                        cache_service.stats["tokens_saved"] += tokens
                        cache_service._save_stats()
                        logger.info(f"Cache HIT (semantic) - saved {tokens} tokens")
                        
                        if is_stream:
                            content = cached_response['choices'][0]['message']['content']
                            model = cached_response.get('model', body.get('model', 'gpt-3.5-turbo'))
                            return StreamingResponse(_construct_stream_from_cache(content, model), media_type="text/event-stream")
                        
                        return JSONResponse(content=cached_response)
                    else:
                        logger.info(f"Semantic search: no match found (threshold: {settings.cache_threshold})")
            
            cache_service.stats["cache_misses"] += 1
            cache_service._save_stats()
            logger.info("Cache MISS - forwarding to upstream API")
        
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Authorization header required")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            upstream_url = f"{settings.upstream_api_url}/chat/completions"
            
            if is_stream:
                logger.info("Streaming request - will collect and cache")
                
                full_content = ""
                chunks_buffer = []
                
                async with client.stream(
                    "POST",
                    upstream_url,
                    json=body,
                    headers={
                        "Authorization": auth_header,
                        "Content-Type": "application/json"
                    }
                ) as stream_response:
                    if stream_response.status_code != 200:
                        logger.error(f"Upstream API error: {stream_response.status_code}")
                        raise HTTPException(status_code=stream_response.status_code, detail="Upstream error")
                    
                    async for chunk in stream_response.aiter_text():
                        if chunk.strip():
                            chunks_buffer.append(chunk)
                            
                            for line in chunk.split('\n'):
                                if line.startswith('data: '):
                                    data_str = line[6:]
                                    if data_str.strip() == '[DONE]':
                                        continue
                                    try:
                                        chunk_data = json.loads(data_str)
                                        delta = chunk_data.get('choices', [{}])[0].get('delta', {})
                                        content = delta.get('content', '')
                                        if content:
                                            full_content += content
                                    except:
                                        pass
                
                if should_cache and full_content:
                    response_data = {
                        "id": f"chatcmpl-{hashlib.md5(full_content.encode()).hexdigest()[:8]}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": body.get("model", "gpt-3.5-turbo"),
                        "choices": [{
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": full_content
                            },
                            "finish_reason": "stop"
                        }],
                        "usage": {
                            "prompt_tokens": 0,
                            "completion_tokens": len(full_content.split()),
                            "total_tokens": len(full_content.split())
                        }
                    }
                    cache_service.set_cache(messages, response_data)
                    logger.info(f"Cached streaming response: {len(full_content)} chars")
                
                async def replay_stream():
                    for chunk in chunks_buffer:
                        yield chunk
                
                return StreamingResponse(replay_stream(), media_type="text/event-stream")
            
            else:
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
                
                if should_cache:
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
