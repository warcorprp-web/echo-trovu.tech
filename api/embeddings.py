from sentence_transformers import SentenceTransformer
import numpy as np
from typing import Optional

class EmbeddingService:
    def __init__(self):
        self.model: Optional[SentenceTransformer] = None
    
    def load_model(self):
        if self.model is None:
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
    
    def get_embedding(self, text: str) -> np.ndarray:
        if self.model is None:
            self.load_model()
        return self.model.encode(text)
    
    def similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        return float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2)))

embedding_service = EmbeddingService()
