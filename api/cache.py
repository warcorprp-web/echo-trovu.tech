import redis
import json
import hashlib
import re
from typing import Optional, Dict, Any, List
from config import settings
from embeddings import embedding_service
import numpy as np

class CacheService:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True
        )
        # Загружаем статистику из Redis
        self._load_stats()
    
    def _normalize_text(self, text: str) -> str:
        """Нормализация текста для лучшего кеширования"""
        # Lowercase
        text = text.lower()
        # Убираем лишние пробелы
        text = re.sub(r'\s+', ' ', text).strip()
        # Убираем пунктуацию в конце
        text = text.rstrip('.,!?;:')
        return text
    
    def _extract_user_content(self, messages: List[Dict]) -> str:
        """Извлекает только user messages для кеширования"""
        user_messages = []
        for msg in messages:
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                user_messages.append(self._normalize_text(content))
        return ' '.join(user_messages)
    
    def _should_cache(self, request_data: Dict) -> bool:
        """Проверяет, нужно ли кешировать запрос"""
        # Не кешируем если temperature > 1.0 (креативные запросы)
        temperature = request_data.get('temperature', 0.0)
        if temperature > 1.0:
            return False
        
        # Streaming кешируем, но возвращаем как non-stream
        # if request_data.get('stream', False):
        #     return False
        
        # Не кешируем function calling
        if 'functions' in request_data or 'tools' in request_data:
            return False
        
        return True
    
    def _load_stats(self):
        """Загрузка статистики из Redis"""
        stats_data = self.redis_client.get("stats")
        if stats_data:
            self.stats = json.loads(stats_data)
        else:
            self.stats = {
                "total_requests": 0,
                "cache_hits": 0,
                "cache_misses": 0,
                "tokens_saved": 0
            }
    
    def _save_stats(self):
        """Сохранение статистики в Redis"""
        self.redis_client.set("stats", json.dumps(self.stats))
    
    def _get_cache_key(self, messages: list) -> str:
        """Генерация ключа для exact match на основе нормализованного контента"""
        # Используем нормализованный user content
        normalized_content = self._extract_user_content(messages)
        return f"exact:{hashlib.md5(normalized_content.encode()).hexdigest()}"
    
    def _get_embedding_key(self, query: str) -> str:
        """Ключ для хранения embedding"""
        return f"emb:{hashlib.md5(query.encode()).hexdigest()}"
    
    def get_exact_match(self, messages: list) -> Optional[Dict[Any, Any]]:
        """Проверка exact match кеша"""
        key = self._get_cache_key(messages)
        cached = self.redis_client.get(key)
        if cached:
            # Обновляем TTL при использовании
            self.redis_client.expire(key, settings.cache_ttl)
            return json.loads(cached)
        return None
    
    def _check_cache_health(self, emb_key: str, response_key: str) -> bool:
        """Проверка консистентности кеша"""
        try:
            # Проверяем что оба ключа существуют
            emb_exists = self.redis_client.exists(emb_key)
            response_exists = self.redis_client.exists(response_key)
            
            if not emb_exists or not response_exists:
                # Удаляем битые записи
                if emb_exists:
                    self.redis_client.delete(emb_key)
                if response_exists:
                    self.redis_client.delete(response_key)
                return False
            
            return True
        except Exception:
            return False
    
    def get_semantic_match(self, query: str, temperature: float = 0.0, top_k: int = 5) -> Optional[Dict[Any, Any]]:
        """Проверка semantic кеша с health check и temperature softmax (оптимизированный Redis)"""
        if not settings.enable_semantic:
            return None
        
        # Нормализуем запрос
        normalized_query = self._normalize_text(query)
        
        # Получаем embedding запроса
        query_emb = embedding_service.get_embedding(normalized_query)
        
        # Получаем список всех embeddings (оптимизировано с SCAN)
        candidates = []
        cursor = 0
        
        while True:
            cursor, keys = self.redis_client.scan(cursor, match="emb:*", count=100)
            
            for key in keys:
                stored_data = self.redis_client.get(key)
                if stored_data:
                    try:
                        data = json.loads(stored_data)
                        response_key = data["response_key"]
                        
                        # Health check
                        if not self._check_cache_health(key, response_key):
                            continue
                        
                        stored_emb = np.array(data["embedding"])
                        similarity = embedding_service.similarity(query_emb, stored_emb)
                        
                        if similarity >= settings.cache_threshold:
                            cached_response = self.redis_client.get(response_key)
                            if cached_response:
                                candidates.append({
                                    'similarity': similarity,
                                    'response': json.loads(cached_response),
                                    'query': data.get("query", ""),
                                    'response_key': response_key,
                                    'emb_key': key
                                })
                                
                                # Ранний выход если нашли top_k кандидатов
                                if len(candidates) >= top_k * 2:
                                    break
                    except Exception as e:
                        continue
            
            if cursor == 0 or len(candidates) >= top_k * 2:
                break
        
        if not candidates:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"No semantic matches found (threshold: {settings.cache_threshold})")
            return None
        
        # Сортируем и берем топ
        candidates.sort(key=lambda x: x['similarity'], reverse=True)
        candidates = candidates[:top_k]
        
        # Temperature softmax для выбора
        if temperature > 0 and len(candidates) > 1:
            scores = np.array([c['similarity'] for c in candidates])
            exp_scores = np.exp(scores / temperature)
            probabilities = exp_scores / exp_scores.sum()
            chosen_idx = np.random.choice(len(candidates), p=probabilities)
            chosen = candidates[chosen_idx]
        else:
            chosen = candidates[0]
        
        # Обновляем TTL
        self.redis_client.expire(chosen['response_key'], settings.cache_ttl)
        self.redis_client.expire(chosen['emb_key'], settings.cache_ttl)
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Semantic match: '{chosen['query']}' (similarity: {chosen['similarity']:.4f}, temp: {temperature})")
        
        return chosen['response']
    
    def set_cache(self, messages: list, response: Dict[Any, Any]):
        """Сохранение в кеш с нормализацией"""
        # Exact match
        exact_key = self._get_cache_key(messages)
        self.redis_client.setex(
            exact_key,
            settings.cache_ttl,
            json.dumps(response)
        )
        
        # Semantic cache
        if settings.enable_semantic and messages:
            # Извлекаем и нормализуем user content
            user_content = self._extract_user_content(messages)
            if user_content:
                query_emb = embedding_service.get_embedding(user_content)
                emb_key = self._get_embedding_key(user_content)
                
                emb_data = {
                    "embedding": query_emb.tolist(),
                    "response_key": exact_key,
                    "query": user_content
                }
                
                # Сохраняем в Redis
                self.redis_client.setex(
                    emb_key,
                    settings.cache_ttl,
                    json.dumps(emb_data)
                )
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики"""
        hit_rate = 0.0
        if self.stats["total_requests"] > 0:
            hit_rate = self.stats["cache_hits"] / self.stats["total_requests"]
        
        return {
            **self.stats,
            "hit_rate": round(hit_rate, 2),
            "estimated_savings_usd": round(self.stats["tokens_saved"] * 0.00003, 2)
        }
    
    def clear_cache(self):
        """Очистка кеша"""
        self.redis_client.flushdb()

cache_service = CacheService()
