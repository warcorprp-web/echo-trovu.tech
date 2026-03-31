# ECHO - Система кеширования AI-ответов

Self-hosted прокси-кеш для OpenAI-совместимых API с семантическим поиском. Экономьте до 70% на API-запросах и получайте ответы в 100+ раз быстрее.

---

## Возможности

### Основные
- **Точное кеширование** - мгновенный ответ для идентичных запросов
- **Семантический поиск** - находит похожие вопросы ("Как установить Docker?" = "Инструкция по установке Docker")
- **Streaming support** - кеширует потоковые ответы (в 40-300x быстрее из кеша)
- **Function calling** - поддержка tools/functions
- **Temperature-aware** - автоматически пропускает креативные запросы (temperature > 1.0)

### Управление
- **Веб-панель** с real-time статистикой и графиками
- **Мастер настройки** - 3 простых шага для старта
- **Авторизация** - защита панели управления
- **Health check** - проверка консистентности кеша

### Технические
- **Faiss IndexIDMap** - быстрый векторный поиск с поддержкой удаления
- **Redis LRU** - автоматическая очистка старых данных
- **Персистентность** - данные сохраняются между перезапусками
- **Нормализация текста** - умное сравнение запросов

---

##  Быстрый старт

### Вариант 1: Docker Compose (рекомендуется)

```bash
# Скачайте конфигурацию
wget https://raw.githubusercontent.com/warcorprp-web/echo-trovu.tech/main/docker-compose.yml

# Запустите (с выводом логов)
docker compose up

# После появления сообщения "Панель управления доступна" нажмите Ctrl+C
# Запустите в фоне
docker compose up -d
```

**Вы увидите:**
```
======================================================================
███████╗ ██████╗██╗  ██╗ ██████╗ 
██╔════╝██╔════╝██║  ██║██╔═══██╗
█████╗  ██║     ███████║██║   ██║
██╔══╝  ██║     ██╔══██║██║   ██║
███████╗╚██████╗██║  ██║╚██████╔╝
╚══════╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ 

Система кеширования AI-ответов
https://trovu.tech/echo

(c) 2026 Trovu.Tech - All Rights Reserved
======================================================================

[*] Загрузка модели эмбеддингов...
[+] Модель загружена

[*] Загрузка Faiss индекса...
[+] Faiss индекс загружен

[!] ТРЕБУЕТСЯ ПЕРВОНАЧАЛЬНАЯ НАСТРОЙКА

Откройте в браузере:
  -> http://localhost:8000
  -> http://<ваш-ip>:8000

Следуйте инструкциям мастера настройки (3 шага)
======================================================================
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

---

##  Первоначальная настройка

Откройте `http://localhost:8000` (или IP вашего сервера) и пройдите 3 шага:

### Шаг 1: Upstream API
```
URL: https://api.openai.com/v1
API ключ: sk-proj-xxxxx
```

**Поддерживаются:**
- OpenAI (api.openai.com)
- Claude (api.anthropic.com)
- Groq (api.groq.com)
- Локальные модели (Ollama, LM Studio, vLLM)
- Любые OpenAI-совместимые API

### Шаг 2: Настройки кеша
```
Порог семантического поиска: 0.88 (рекомендуется 0.85-0.90)
Время жизни кеша (TTL): 86400 секунд (24 часа)
Семантический поиск: Включен
```

**Что влияет на что:**
- **Порог 0.85-0.90** - оптимальный баланс (находит похожие, но не слишком разные запросы)
- **Порог < 0.85** - больше попаданий, но могут быть неточные совпадения
- **Порог > 0.90** - только очень похожие запросы, меньше попаданий
- **TTL** - как долго хранить ответы (по умолчанию 24 часа)

### Шаг 3: Авторизация
```
Логин: admin
Пароль: ваш_пароль
```

---

##  Использование

### Python (OpenAI SDK)

```python
from openai import OpenAI

# Было:
# client = OpenAI(api_key="sk-proj-xxxxx")

# Стало (просто измените base_url):
client = OpenAI(
    api_key="любой_ключ",  # можно любой, настоящий ключ в панели ECHO
    base_url="http://localhost:8000/v1"
)

# Используйте как обычно
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Что такое Docker?"}]
)
print(response.choices[0].message.content)
```

### cURL

```bash
curl -X POST "http://localhost:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer любой_ключ" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Что такое Docker?"}],
    "temperature": 0.7
  }'
```

### Streaming

```python
stream = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Напиши Hello World на Python"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### Function Calling

```python
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Какая погода в Москве?"}],
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Получить погоду в городе",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"}
                }
            }
        }
    }]
)
```

---

##  Производительность

### Реальные тесты на VPS

**Обычные запросы:**
```
Первый запрос:  16.3 секунды  (промах кеша, запрос к API)
Второй запрос:  0.13 секунды  (попадание в кеш)
Ускорение:      125x быстрее! 
```

**Streaming:**
```
Первый запрос:  5.5 секунды   (промах кеша)
Второй запрос:  0.14 секунды  (из кеша)
Ускорение:      40x быстрее! 
```

**Семантический поиск:**
```
"Как установить Docker на Ubuntu?"           → 10.7s (промах)
"Как поставить Docker на Ubuntu Linux?"      → 0.17s (попадание!)
"Инструкция по установке Docker в Ubuntu"    → 0.14s (попадание!)
"Как приготовить пиццу?"                     → 17.3s (промах, другая тема)
```

### Экономия

**Пример для GPT-4:**
- Цена: $5 за 1M входных токенов
- 1000 запросов по 100 токенов = 100K токенов = $0.50
- С кешем (70% попаданий): $0.15
- **Экономия: $0.35 (70%)**

**Для больших объемов:**
- 1M запросов без кеша: $500
- 1M запросов с кешем (70%): $150
- **Экономия: $350 в месяц**

---

##  Как работает кеширование

### 1. Точное совпадение (Exact Match)
```python
# Запрос 1
"Что такое Docker?"  → API → Ответ сохранен

# Запрос 2 (идентичный)
"Что такое Docker?"  → Кеш → Мгновенный ответ (0.1s)
```

### 2. Семантический поиск (Semantic Search)
```python
# Запрос 1
"Как установить Docker?"  → API → Ответ сохранен + эмбеддинг

# Запрос 2 (похожий, но другими словами)
"Инструкция по установке Docker"  
  → Faiss поиск → Similarity 0.92 > 0.88 
  → Кеш → Быстрый ответ (0.15s)
```

### 3. Temperature отсев
```python
# Temperature 0.0-1.0 - кешируется
response = client.chat.completions.create(
    messages=[...],
    temperature=0.7  #  Будет кешироваться
)

# Temperature > 1.0 - НЕ кешируется (креативные запросы)
response = client.chat.completions.create(
    messages=[...],
    temperature=1.5  #  Каждый раз новый ответ
)
```

---

##  Настройки

### Порог семантического поиска (Threshold)

**Что это:** Минимальная схожесть запросов для попадания в кеш (0.0 - 1.0)

**Рекомендации:**
- **0.85-0.88** - оптимально для большинства случаев
- **0.90-0.95** - строгий режим (только очень похожие запросы)
- **0.75-0.85** - мягкий режим (больше попаданий, но могут быть неточности)

**Примеры:**

```
Порог 0.95 (строгий):
"Как установить Docker?" 
"Как поставить Docker?"   (similarity 0.96)
"Установка Docker"        (similarity 0.89)

Порог 0.85 (оптимальный):
"Как установить Docker?" 
"Как поставить Docker?"   (similarity 0.96)
"Установка Docker"        (similarity 0.89)
"Docker инструкция"       (similarity 0.78)

Порог 0.75 (мягкий):
"Как установить Docker?" 
"Docker инструкция"       (similarity 0.78)
"Контейнеризация"         (similarity 0.65)
```

### Время жизни кеша (TTL)

**Что это:** Как долго хранить ответы в кеше

**Рекомендации:**
- **86400 (24 часа)** - для общих вопросов
- **3600 (1 час)** - для данных, которые часто меняются
- **604800 (7 дней)** - для статичной информации (документация, туториалы)
- **0 (без ограничений)** - пока не заполнится Redis (512MB по умолчанию)

### Redis LRU

Redis автоматически удаляет старые записи при заполнении памяти (512MB):
- Самые старые записи удаляются первыми
- Faiss индекс синхронизируется автоматически

---

##  Мониторинг

### Веб-панель

Откройте `http://localhost:8000` после настройки:

**Статистика:**
- Общее количество запросов
- Попадания в кеш (Cache Hits)
- Промахи кеша (Cache Misses)
- Hit Rate (процент попаданий)
- Средняя скорость ответа

**Графики:**
- Запросы по времени
- Hit Rate динамика
- Топ кешированных запросов

**Управление:**
- Очистка кеша
- Изменение настроек
- Health check (проверка консистентности)

### Логи

```bash
# Просмотр логов
docker logs echo-api -f

# Что вы увидите:
Cache HIT - returning cached response (0.089s)
Cache MISS - forwarding to upstream API (16.3s)
Semantic search: found match with similarity 0.92
Temperature 1.5 > 1.0, skipping cache
```

---

##  Управление

### Очистка кеша

```bash
# Полная очистка
docker exec echo-redis redis-cli FLUSHALL

# Очистка только ответов (сохранить настройки)
docker exec echo-redis redis-cli --scan --pattern "resp:*" | xargs docker exec -i echo-redis redis-cli DEL
```

### Изменение настроек

```bash
# Через панель управления (рекомендуется)
http://localhost:8000

# Или вручную через Redis
docker exec echo-redis redis-cli SET cache_threshold "0.90"
docker exec echo-redis redis-cli SET cache_ttl "3600"
docker exec echo-redis redis-cli SET upstream_url "https://api.openai.com/v1"
```

### Backup данных

```bash
# Backup Redis
docker exec echo-redis redis-cli SAVE
docker cp echo-redis:/data/dump.rdb ./backup-redis.rdb

# Backup Faiss индекса
docker cp echo-api:/app/data/faiss.index ./backup-faiss.index

# Восстановление
docker cp ./backup-redis.rdb echo-redis:/data/dump.rdb
docker cp ./backup-faiss.index echo-api:/app/data/faiss.index
docker compose restart
```

---

##  Безопасность

### SSL/HTTPS

Для production используйте Nginx с SSL:

```nginx
server {
    listen 443 ssl http2;
    server_name cache.example.com;
    
    ssl_certificate /etc/letsencrypt/live/cache.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cache.example.com/privkey.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Для streaming
        proxy_buffering off;
        proxy_cache off;
    }
}
```

### Firewall

```bash
# Разрешить только локальный доступ
ufw allow from 127.0.0.1 to any port 8000

# Или с определенных IP
ufw allow from 192.168.1.0/24 to any port 8000
```

---

##  Troubleshooting

### Проблема: Панель не открывается

```bash
# Проверьте статус контейнеров
docker ps -a | grep echo

# Проверьте логи
docker logs echo-api --tail 50

# Проверьте порт
curl http://localhost:8000
```

### Проблема: Ошибка 404 от upstream

```bash
# Проверьте настройки
docker exec echo-redis redis-cli GET upstream_url
docker exec echo-redis redis-cli GET upstream_api_key

# Исправьте URL (без /chat/completions в конце!)
docker exec echo-redis redis-cli SET upstream_url "https://api.openai.com/v1"
```

### Проблема: Низкий Hit Rate

**Возможные причины:**
1. **Слишком высокий порог** (0.95+) - уменьшите до 0.85-0.88
2. **Разные формулировки** - семантический поиск должен помочь
3. **Высокая temperature** (>1.0) - такие запросы не кешируются
4. **Мало повторяющихся запросов** - это нормально для разнообразных задач

```bash
# Проверьте текущий порог
docker exec echo-redis redis-cli GET cache_threshold

# Уменьшите порог
docker exec echo-redis redis-cli SET cache_threshold "0.85"
```

---

##  Архитектура

```
┌─────────────┐
│   Клиент    │
│  (OpenAI    │
│    SDK)     │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│         ECHO Proxy (FastAPI)        │
│                                     │
│  1. Нормализация запроса            │
│  2. Проверка temperature            │
│  3. Поиск в кеше (Redis + Faiss)    │
│  4. Если нет - запрос к Upstream    │
│  5. Сохранение ответа               │
└──────┬──────────────────────┬───────┘
       │                      │
       ▼                      ▼
┌─────────────┐      ┌─────────────────┐
│    Redis    │      │  Faiss Index    │
│             │      │                 │
│ - Ответы    │      │ - Эмбеддинги    │
│ - Настройки │      │ - Векторный     │
│ - Сессии    │      │   поиск         │
└─────────────┘      └─────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│      Upstream API (OpenAI, etc)     │
└─────────────────────────────────────┘
```

**Компоненты:**
- **FastAPI** - API сервер и веб-панель
- **Redis** - хранилище кеша, настроек, сессий (LRU eviction)
- **Faiss** - векторный поиск для семантического кеша
- **sentence-transformers** - генерация эмбеддингов (all-MiniLM-L6-v2)

---

##  Поддержка

- **Сайт:** https://trovu.tech/echo
- **GitHub:** https://github.com/warcorprp-web/echo-trovu.tech
- **Docker Hub:** https://hub.docker.com/r/trovutech/echo

---

##  Лицензия

MIT License - используйте свободно в коммерческих и личных проектах.

---

##  Автор

**Trovu.Tech** - https://trovu.tech

© 2026 Trovu.Tech - All Rights Reserved
