import redis
import json
import hashlib
import re
import os
import faiss
from typing import Optional, Dict, Any, List
from config import settings
from embeddings import embedding_service
from faiss_service import faiss_service
import numpy as np
import logging

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True
        )
        # Загружаем статистику из Redis
        self._load_stats()
        # Faiss загружается в startup event после инициализации всего
    
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
    
    def _load_faiss_index(self):
        """Загрузка существующих эмбеддингов в Faiss индекс"""
        try:
            # Проверяем есть ли сохраненный индекс
            if os.path.isfile(faiss_service.index_path):
                logger.info(f"Loading Faiss index from {faiss_service.index_path}")
                faiss_service.index = faiss.read_index(faiss_service.index_path)
                
                # Восстанавливаем маппинг hash_to_id из Redis
                cursor = 0
                faiss_id = 0
                while True:
                    cursor, keys = self.redis_client.scan(cursor, match="emb:*", count=100)
                    for key in keys:
                        faiss_service.hash_to_id[key] = faiss_id
                        faiss_id += 1
                    if cursor == 0:
                        break
                
                faiss_service.next_id = faiss_id
                logger.info(f"Loaded Faiss index with {faiss_service.index.ntotal} vectors from file")
                return
            
            # Если файла нет - загружаем из Redis
            logger.info("Loading embeddings into Faiss index from Redis...")
            cursor = 0
            count = 0
            
            while True:
                cursor, keys = self.redis_client.scan(cursor, match="emb:*", count=100)
                
                for key in keys:
                    stored_data = self.redis_client.get(key)
                    if stored_data:
                        try:
                            data = json.loads(stored_data)
                            embedding = np.array(data["embedding"])
                            faiss_service.add(key, embedding)
                            count += 1
                        except Exception as e:
                            logger.error(f"Failed to load embedding {key}: {e}")
                
                if cursor == 0:
                    break
            
            logger.info(f"Loaded {count} embeddings into Faiss index from Redis")
            
            # Сохраняем индекс на диск
            if count > 0:
                faiss_service.flush()
                logger.info("Faiss index saved to disk")
        except Exception as e:
            logger.error(f"Failed to load Faiss index: {e}")
    
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
        """Проверка semantic кеша с Faiss и temperature softmax"""
        if not settings.enable_semantic:
            return None
        
        # Нормализуем запрос
        normalized_query = self._normalize_text(query)
        
        # Получаем embedding запроса
        query_emb = embedding_service.get_embedding(normalized_query)
        
        # Поиск через Faiss (в 1000x быстрее чем Redis SCAN)
        faiss_results = faiss_service.search(query_emb, k=top_k * 2)
        
        if not faiss_results:
            logger.info(f"No semantic matches found (threshold: {settings.cache_threshold})")
            return None
        
        # Проверяем результаты и фильтруем по threshold
        candidates = []
        for emb_key, similarity in faiss_results:
            logger.debug(f"Faiss candidate: {emb_key}, similarity: {similarity:.4f}")
            
            if similarity < settings.cache_threshold:
                logger.debug(f"Filtered out: {similarity:.4f} < {settings.cache_threshold}")
                continue
            
            # Получаем данные из Redis
            stored_data = self.redis_client.get(emb_key)
            if not stored_data:
                continue
            
            try:
                data = json.loads(stored_data)
                response_key = data["response_key"]
                
                # Health check
                if not self._check_cache_health(emb_key, response_key):
                    continue
                
                cached_response = self.redis_client.get(response_key)
                if cached_response:
                    candidates.append({
                        'similarity': similarity,
                        'response': json.loads(cached_response),
                        'query': data.get("query", ""),
                        'response_key': response_key,
                        'emb_key': emb_key
                    })
            except Exception as e:
                logger.error(f"Error processing candidate: {e}")
                continue
        
        if not candidates:
            logger.info(f"No valid candidates after filtering (threshold: {settings.cache_threshold})")
            return None
        
        # Сортируем по similarity
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
                
                # Добавляем в Faiss индекс
                try:
                    faiss_service.add(emb_key, query_emb)
                    faiss_service.flush()  # Сохраняем после каждого добавления
                    logger.debug(f"Added to Faiss: {emb_key}")
                except Exception as e:
                    logger.error(f"Failed to add to Faiss: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики"""
        hit_rate = 0.0
        if self.stats["total_requests"] > 0:
            hit_rate = self.stats["cache_hits"] / self.stats["total_requests"]
        
        return {
            **self.stats,
            "hit_rate": round(hit_rate, 2),
            "estimated_savings_usd": round(self.stats["tokens_saved"] * 0.00003, 2),
            "faiss_vectors": faiss_service.size()
        }
    
    def clear_cache(self):
        """Очистка кеша"""
        self.redis_client.flushdb()
        faiss_service.clear()
        logger.info("Cache cleared (Redis + Faiss)")
    
    def cleanup_faiss(self):
        """Очистка удаленных векторов из Faiss"""
        # Получаем все ключи из Redis
        redis_keys = set()
        cursor = 0
        while True:
            cursor, keys = self.redis_client.scan(cursor, match="emb:*", count=100)
            redis_keys.update(keys)
            if cursor == 0:
                break
        
        # Удаляем из Faiss то, чего нет в Redis
        faiss_keys = set(faiss_service.hash_to_id.keys())
        to_remove = faiss_keys - redis_keys
        
        for key in to_remove:
            faiss_service.remove(key)
        
        if to_remove:
            faiss_service.flush()
            logger.info(f"Cleaned up {len(to_remove)} orphaned vectors from Faiss")

cache_service = CacheService()
