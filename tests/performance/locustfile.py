from locust import HttpUser, task, between

class APIUser(HttpUser):
    # Імітуємо очікування реального користувача між діями (від 1 до 3 секунд)
    wait_time = between(1, 3)
    
    # Визначаємо заголовки, щоб обійти базовий CSRF/CORS та авторизацію
    headers = {
        "Origin": "http://localhost:8000",
        "Referer": "http://localhost:8000/",
        "x-api-key": "dev_test_key"  # Або будь-який інший валідний ключ для локального тестування
    }

    @task(3)
    def check_health(self):
        """Часто перевіряємо /health endpoint (легка операція)."""
        with self.client.get("/health", headers=self.headers, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed with {response.status_code}")

    @task(1)
    def analyze_url(self):
        """Рідше відправляємо запит на аналіз (важка операція + Rate Limit)."""
        payload = {
            "url": "https://devpost.com/software/dummy-project",
            "hard_constraints": {"rule": "must use React"}
        }
        
        with self.client.post("/analyze/url", json=payload, headers=self.headers, catch_response=True) as response:
            # Очікуємо 200 OK або 429 Rate Limit (обидва варіанти означають, що сервер "тримає удар")
            if response.status_code in [200, 429]:
                response.success()
            elif response.status_code == 403:
                response.failure("CSRF/CORS Blocked (403 Forbidden)")
            elif response.status_code == 422:
                response.failure("Validation Error (422 Unprocessable Entity)")
            else:
                response.failure(f"Failed with status code: {response.status_code}")
