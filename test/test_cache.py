import requests
import time

API_URL = "http://localhost:8000/v1/chat/completions"
API_KEY = "879621"

def test_request(query: str, test_name: str):
    """Тестовый запрос"""
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"Query: {query}")
    print('='*60)
    
    start = time.time()
    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "qwen3-coder-plus",
            "messages": [{"role": "user", "content": query}],
            "max_tokens": 100
        }
    )
    elapsed = time.time() - start
    
    if response.status_code == 200:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        
        print(f"✅ Success")
        print(f"Time: {elapsed:.2f}s")
        print(f"Tokens: {tokens}")
        print(f"Response: {content[:100]}...")
    else:
        print(f"❌ Error: {response.status_code}")
        print(response.text)

def get_stats():
    """Получить статистику"""
    response = requests.get("http://localhost:8000/stats")
    if response.status_code == 200:
        stats = response.json()
        print(f"\n{'='*60}")
        print("CACHE STATISTICS")
        print('='*60)
        print(f"Total requests: {stats['total_requests']}")
        print(f"Cache hits: {stats['cache_hits']}")
        print(f"Cache misses: {stats['cache_misses']}")
        print(f"Hit rate: {stats['hit_rate']*100:.0f}%")
        print(f"Tokens saved: {stats['tokens_saved']}")
        print(f"Estimated savings: ${stats['estimated_savings_usd']}")
        print('='*60)

if __name__ == "__main__":
    print("🧪 Testing AI Cache\n")
    
    # Test 1: First request (cache miss)
    test_request("Что такое Python?", "First request - MISS expected")
    time.sleep(1)
    
    # Test 2: Exact same request (cache hit)
    test_request("Что такое Python?", "Exact match - HIT expected")
    time.sleep(1)
    
    # Test 3: Similar request (semantic cache hit)
    test_request("Расскажи про Python", "Semantic match - HIT expected")
    time.sleep(1)
    
    # Test 4: Different request (cache miss)
    test_request("Как работает JavaScript?", "Different query - MISS expected")
    time.sleep(1)
    
    # Test 5: Similar to test 4 (semantic hit)
    test_request("Объясни JavaScript", "Semantic match - HIT expected")
    
    # Show statistics
    get_stats()
