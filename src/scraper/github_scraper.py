import sys
from pathlib import Path
import re
import json
import os
import httpx

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger

# Зчитуємо токен з оточення (для розширення ліміту запитів до 5000/год)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or None

def get_github_metrics(github_url: str) -> dict:
    """
    Отримує README length та кількість комітів (останні 30) для репозиторію.
    Захищено від лімітів запитів GitHub API та помилок невалідних URL.
    """
    if not github_url or "github.com" not in github_url:
        return {}
        
    try:
        # Очищення URL від зайвих слешів та суфіксів .git
        clean_url = github_url.rstrip("/").replace(".git", "")
        
        # Регулярний вираз для вилучення власника та репозиторію
        match = re.search(r"github\.com/([^/]+)/([^/]+)", clean_url)
        if not match:
            return {}
            
        owner = match.group(1)
        # Захист від посилань на підпапки: беремо лише першу частину назви репо
        repo = match.group(2).split("/")[0]
        
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "DP-SHW-Hacking-Tool"
        }
        
        # Якщо в .env вказано токен, додаємо авторизацію
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
            
        metrics = {
            "readme_length": 0,
            "commit_count_48h": 0
        }
        
        # 1. Запит README length
        readme_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        try:
            r = httpx.get(readme_url, headers=headers, timeout=10.0)
            if r.status_code == 200:
                # Довжина закодованого Base64 вмісту файлу README
                metrics["readme_length"] = len(r.json().get("content", ""))
            elif r.status_code in [403, 429]:
                logger.warning(f"GitHub API повернув ліміт {r.status_code} для {owner}/{repo}. Метрики встановлено в 0.")
                return metrics
        except Exception as e:
            logger.warning(f"Не вдалося зчитати README для {owner}/{repo}: {e}")
            
        # 2. Запит кількості комітів
        commits_url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=30"
        try:
            r2 = httpx.get(commits_url, headers=headers, timeout=10.0)
            if r2.status_code == 200:
                metrics["commit_count_48h"] = len(r2.json())
            elif r2.status_code in [403, 429]:
                logger.warning(f"GitHub API повернув ліміт {r2.status_code} при запиті комітів для {owner}/{repo}.")
        except Exception as e:
            logger.warning(f"Не вдалося зчитати коміти для {owner}/{repo}: {e}")
            
        return metrics
        
    except Exception as e:
        logger.error(f"Помилка при зборі GitHub-метрик для {github_url}: {e}")
        return {}

if __name__ == "__main__":
    test_repo = "https://github.com/psf/requests"
    print(f"🔄 Тестуємо збір метрик для відомого репозиторію: '{test_repo}'")
    
    result = get_github_metrics(test_repo)
    print("\n📋 ОТРИМАНІ МЕТРИКИ REPOSITORY:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
