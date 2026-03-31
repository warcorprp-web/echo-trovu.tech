# ECHO - AI Response Caching System

Self-hosted система кеширования ответов для OpenAI-совместимых API с семантическим поиском.

## Возможности

- **Точное кеширование** - мгновенный ответ для идентичных запросов
- **Семантический кеш** - AI-поиск похожих запросов (настраиваемый порог 0.95)
- **Streaming support** - кеширование streaming запросов (в 334x быстрее из кеша)
- **Temperature-aware** - автоматический пропуск креативных запросов (temperature > 1.0)
- **Cache health check** - проверка консистентности данных
- **Нормализация текста** - умное сравнение запросов
- **Веб-панель управления** с real-time статистикой
- **Мастер первоначальной настройки** (3 шага)
- **Авторизация** с управлением сессиями
- **Redis LRU eviction** - автоматическая очистка старых данных
- Поддержка OpenAI, Claude, Groq, локальных моделей

## Быстрый старт

### Вариант 1: Docker Compose (рекомендуется)

```bash
# Скачайте docker-compose.yml
wget https://raw.githubusercontent.com/warcorprp-web/echo-trovu.tech/main/docker-compose.prod.yml -O docker-compose.yml

# Запустите
docker compose up -d

# Дождитесь загрузки (10-15 секунд) и посмотрите логи
docker logs echo-api

# Или запустите с выводом логов сразу
docker compose up
# После появления сообщения "Панель управления доступна" нажмите Ctrl+C
# Затем запустите в фоне: docker compose up -d
```

### Вариант 2: Только Docker

```bash
# Запустите Redis
docker run -d --name echo-redis redis:7-alpine

# Запустите ECHO
docker run -d \
  -p 8000:8000 \
  -e REDIS_HOST=echo-redis \
  --link echo-redis \
  --name echo-api \
  trovutech/echo:latest

# Посмотрите логи
docker logs -f echo-api
```

### Вариант 3: Разработка (из исходников)

```bash
git clone https://github.com/warcorprp-web/echo-trovu.tech.git
cd echo-trovu.tech
docker compose up
```

Откройте браузер: `http://localhost:8000` или `http://<ваш-ip>:8000`

Следуйте инструкциям мастера настройки (3 шага)

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

- **50-70%** попаданий в кеш в production
- **В 200-334x быстрее** ответы из кеша (streaming до 334x)
- **Значительная экономия** на API-запросах ($5,250 на 1M токенов GPT-5.4)
- **< 10ms** время ответа из кеша

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
