from pydantic_settings import BaseSettings
import redis
import json

class Settings(BaseSettings):
    upstream_api_url: str = "https://api.openai.com/v1"
    upstream_api_key: str = ""
    cache_threshold: float = 0.95
    cache_ttl: int = 3600
    enable_semantic: bool = True
    redis_host: str = "redis"
    redis_port: int = 6379
    
    class Config:
        env_file = ".env"
    
    def load_from_redis(self):
        """Загрузка настроек из Redis (приоритет над .env)"""
        try:
            r = redis.Redis(host=self.redis_host, port=self.redis_port, decode_responses=True)
            config_data = r.get("config")
            if config_data:
                config = json.loads(config_data)
                self.upstream_api_url = config.get("upstream_api_url", self.upstream_api_url)
                self.upstream_api_key = config.get("upstream_api_key", self.upstream_api_key)
                self.cache_threshold = config.get("cache_threshold", self.cache_threshold)
                self.cache_ttl = config.get("cache_ttl", self.cache_ttl)
                self.enable_semantic = config.get("enable_semantic", self.enable_semantic)
        except:
            pass
    
    def save_to_redis(self):
        """Сохранение настроек в Redis"""
        r = redis.Redis(host=self.redis_host, port=self.redis_port, decode_responses=True)
        config = {
            "upstream_api_url": self.upstream_api_url,
            "upstream_api_key": self.upstream_api_key,
            "cache_threshold": self.cache_threshold,
            "cache_ttl": self.cache_ttl,
            "enable_semantic": self.enable_semantic
        }
        r.set("config", json.dumps(config))

settings = Settings()
settings.load_from_redis()
