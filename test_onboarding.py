import asyncio
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

response = client.post("/onboarding/complete")
print("Response status:", response.status_code)
try:
    print("Response body:", response.json())
except Exception as e:
    print("Response text:", response.text)
