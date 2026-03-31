# ECHO - AI Response Caching System

Self-hosted система кеширования ответов для OpenAI-совместимых API с семантическим поиском.

## Возможности

- Точное кеширование - мгновенный ответ для идентичных запросов
- Семантический кеш - AI-поиск похожих запросов (настраиваемый порог)
- Веб-панель управления с real-time статистикой
- Мастер первоначальной настройки (3 шага)
- Авторизация с управлением сессиями
- Поддержка OpenAI, Claude, Groq, локальных моделей

## Быстрый старт

1. Клонируйте репозиторий:
```bash
git clone https://github.com/trovutech/echo.git
cd echo
```

2. Запустите Docker Compose:
```bash
docker compose up -d
```

3. Откройте браузер:
```
http://localhost:8000
```

4. Следуйте инструкциям мастера настройки (3 шага)

## Использование

После настройки измените в вашем коде:

```python
# Было:
openai.api_base = "https://api.openai.com/v1"

# Стало:
openai.api_base = "http://localhost:8000/v1"
```

Все запросы будут автоматически кешироваться!

## Производительность

- 50-70% попаданий в кеш в production
- В 200+ раз быстрее ответы из кеша
- Значительная экономия на API-запросах

## Настройка

Все настройки доступны через веб-панель:
- Upstream API URL и ключ
- Порог семантического кеша (рекомендуется 0.85-0.90)
- Время жизни кеша (TTL)
- Включение/выключение семантического поиска

## SSL и домен

Для использования с SSL настройте Nginx:

```nginx
server {
    listen 443 ssl;
    server_name cache.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Архитектура

- FastAPI - API сервер
- Redis - хранилище кеша и настроек
- sentence-transformers - семантический поиск
- Docker - контейнеризация

## Лицензия

MIT

## Автор

trovu.tech - https://trovu.tech
