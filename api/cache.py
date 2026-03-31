import redis
import json
import hashlib
from typing import Optional, Dict, Any
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
        """Генерация ключа для exact match"""
        content = json.dumps(messages, sort_keys=True)
        return f"exact:{hashlib.md5(content.encode()).hexdigest()}"
    
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
    
    def get_semantic_match(self, query: str) -> Optional[Dict[Any, Any]]:
        """Проверка semantic кеша"""
        if not settings.enable_semantic:
            return None
        
        # Получаем embedding запроса
        query_emb = embedding_service.get_embedding(query)
        
        # Получаем список всех embeddings
        emb_keys = list(self.redis_client.keys("emb:*"))
        
        if not emb_keys:
            return None
        
        best_similarity = 0.0
        best_response = None
        best_query = None
        
        # Ищем наиболее похожий запрос
        for key in emb_keys:
            stored_data = self.redis_client.get(key)
            if stored_data:
                try:
                    data = json.loads(stored_data)
                    stored_emb = np.array(data["embedding"])
                    similarity = embedding_service.similarity(query_emb, stored_emb)
                    
                    if similarity > best_similarity:
                        best_similarity = similarity
                        if similarity >= settings.cache_threshold:
                            response_key = data["response_key"]
                            cached_response = self.redis_client.get(response_key)
                            if cached_response:
                                best_response = json.loads(cached_response)
                                best_query = data.get("query", "")
                                # Обновляем TTL для найденного кеша
                                self.redis_client.expire(response_key, settings.cache_ttl)
                                self.redis_client.expire(key, settings.cache_ttl)
                except Exception as e:
                    continue
        
        # Логируем лучший результат
        import logging
        logger = logging.getLogger(__name__)
        if best_query:
            logger.info(f"Best match: '{best_query}' (similarity: {best_similarity:.4f})")
        else:
            logger.info(f"Best similarity: {best_similarity:.4f} < threshold {settings.cache_threshold}")
        
        return best_response
    
    def set_cache(self, messages: list, response: Dict[Any, Any]):
        """Сохранение в кеш"""
        # Exact match
        exact_key = self._get_cache_key(messages)
        self.redis_client.setex(
            exact_key,
            settings.cache_ttl,
            json.dumps(response)
        )
        
        # Semantic cache
        if settings.enable_semantic and messages:
            last_message = messages[-1].get("content", "")
            if last_message:
                query_emb = embedding_service.get_embedding(last_message)
                emb_key = self._get_embedding_key(last_message)
                
                emb_data = {
                    "embedding": query_emb.tolist(),
                    "response_key": exact_key,
                    "query": last_message
                }
                
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
