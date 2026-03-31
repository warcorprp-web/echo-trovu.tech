"""
Faiss vector store service для быстрого семантического поиска
"""
import faiss
import numpy as np
import logging
import os
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


class FaissService:
    def __init__(self, dimension: int = 384, index_path: str = "/app/data/faiss.index"):
        """
        Инициализация Faiss индекса
        
        Args:
            dimension: размерность эмбеддингов (384 для all-MiniLM-L6-v2)
            index_path: путь для сохранения индекса
        """
        self.dimension = dimension
        self.index_path = index_path
        
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        
        if os.path.isfile(index_path):
            logger.info(f"Loading Faiss index from {index_path}")
            self.index = faiss.read_index(index_path)
            logger.info(f"Loaded Faiss index with {self.index.ntotal} vectors")
        else:
            self.index = faiss.index_factory(dimension, "IDMap,Flat", faiss.METRIC_INNER_PRODUCT)
            logger.info(f"Created new Faiss index with dimension {dimension}")
        
        self.hash_to_id = {}
        self.next_id = 0
        
        if self.index.ntotal > 0:
            self.next_id = self.index.ntotal
    
    def add(self, key: str, embedding: np.ndarray) -> None:
        """
        Добавить эмбеддинг в индекс
        
        Args:
            key: Redis ключ (emb:hash)
            embedding: вектор эмбеддинга
        """
        embedding = embedding.astype('float32').reshape(1, -1)
        faiss.normalize_L2(embedding)
        
        faiss_id = self.next_id
        self.next_id += 1
        
        ids = np.array([faiss_id], dtype=np.int64)
        self.index.add_with_ids(embedding, ids)
        
        self.hash_to_id[key] = faiss_id
        
        logger.debug(f"Added to Faiss: {key} -> ID {faiss_id}")
    
    def search(self, query_embedding: np.ndarray, k: int = 5) -> List[Tuple[str, float]]:
        """
        Поиск топ-K похожих эмбеддингов
        
        Args:
            query_embedding: вектор запроса
            k: количество результатов
            
        Returns:
            List[(redis_key, similarity_score)]
        """
        if self.index.ntotal == 0:
            return []
        
        query_embedding = query_embedding.astype('float32').reshape(1, -1)
        faiss.normalize_L2(query_embedding)
        
        k = min(k, self.index.ntotal)
        distances, indices = self.index.search(query_embedding, k)
        
        id_to_hash = {v: k for k, v in self.hash_to_id.items()}
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx != -1:
                key = id_to_hash.get(idx)
                if key:
                    results.append((key, float(dist)))
        
        return results
    
    def remove(self, key: str) -> bool:
        """
        Удалить эмбеддинг из индекса
        
        Args:
            key: Redis ключ
            
        Returns:
            True если удален, False если не найден
        """
        if key not in self.hash_to_id:
            return False
        
        faiss_id = self.hash_to_id[key]
        
        ids_to_remove = np.array([faiss_id], dtype=np.int64)
        selector = faiss.IDSelectorBatch(ids_to_remove.size, faiss.swig_ptr(ids_to_remove))
        self.index.remove_ids(selector)
        
        del self.hash_to_id[key]
        
        logger.debug(f"Removed from Faiss: {key} (ID {faiss_id})")
        return True
    
    def rebuild(self, embeddings: List[Tuple[str, np.ndarray]]) -> None:
        """
        Пересоздать индекс с нуля
        
        Args:
            embeddings: List[(key, embedding)]
        """
        self.index = faiss.index_factory(self.dimension, "IDMap,Flat", faiss.METRIC_INNER_PRODUCT)
        self.hash_to_id = {}
        self.next_id = 0
        
        for key, embedding in embeddings:
            self.add(key, embedding)
        
        logger.info(f"Faiss index rebuilt with {len(embeddings)} vectors")
        
        self.flush()
    
    def flush(self) -> None:
        """Сохранить индекс на диск"""
        try:
            faiss.write_index(self.index, self.index_path)
            logger.debug(f"Faiss index saved to {self.index_path}")
        except Exception as e:
            logger.error(f"Failed to save Faiss index: {e}")
    
    def size(self) -> int:
        """Количество векторов в индексе"""
        return self.index.ntotal
    
    def clear(self) -> None:
        """Очистить индекс"""
        self.index = faiss.index_factory(self.dimension, "IDMap,Flat", faiss.METRIC_INNER_PRODUCT)
        self.hash_to_id = {}
        self.next_id = 0
        logger.info("Faiss index cleared")
        self.flush()


faiss_service = FaissService(dimension=384)
