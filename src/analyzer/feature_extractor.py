import json
import re
import sys
from pathlib import Path

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger  # noqa: E402

# КРИТИЧНИЙ ФІКС: Відновлено список ключових слів для соціальних проектів (Етап 22)
SOCIAL_KEYWORDS = [
    "health", "mental", "education", "accessib", "sustainab",
    "climate", "poverty", "disaster", "elderly", "disability"
]

def _safe_json_load(data) -> list:
    """Безпечно парсить JSON, запобігаючи падінням."""
    if not data:
        return []
    if isinstance(data, list):
        return data
    try:
        return json.loads(data)
    except Exception:
        return []

def calculate_novelty_score(description: str, tech_tags: list, all_projects_descriptions: list = None) -> float:
    """
    Розраховує унікальність проекту на основі:
    1. TF-IDF схожості з іншими проектами (нижча схожість = вища унікальність)
    2. Рідкісності технологій (рідкісні технології = вища унікальність)
    """
    try:
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        # 1. TF-IDF схожість з іншими проектами
        if all_projects_descriptions and len(all_projects_descriptions) > 10:
            vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')

            # Обмежуємо кількість проектів для швидкодії
            sample_descriptions = all_projects_descriptions[:100]
            sample_descriptions.append(description)

            tfidf_matrix = vectorizer.fit_transform(sample_descriptions)

            # Схожість з усіма іншими проектами
            similarities = cosine_similarity(tfidf_matrix[-1:], tfidf_matrix[:-1])[0]
            avg_similarity = np.mean(similarities)

            # Інвертуємо: нижча схожість = вища унікальність
            novelty_from_text = 1.0 - avg_similarity
        else:
            novelty_from_text = 0.5  # Нейтральне значення

        # 2. Рідкісність технологій (якщо є дані про частоту)
        # Тут можна додати логіку з бази даних
        novelty_from_tech = 0.5

        # Комбінуємо
        novelty_score = (novelty_from_text * 0.7) + (novelty_from_tech * 0.3)
        return round(min(max(novelty_score, 0.0), 1.0), 3)

    except Exception as e:
        logger.debug(f"Помилка розрахунку novelty_score: {e}")
        return 0.5

def extract_features(
    project: dict, hackathon: dict, total_hackathon_projects: int = 1, organizer_count: int = 0
) -> dict:
    """
    Перетворює сирі дані проекту та хакарону на 18+ розширених ознак для ML.
    Захищено від відсутності полів та NaN-значень.
    """
    desc = (project.get("description") or "").lower()
    demo_url = (project.get("demo_url") or "").lower()
    tags = _safe_json_load(project.get("tech_tags"))
    sponsors = _safe_json_load(hackathon.get("sponsors"))
    prize_track = (project.get("prize_track") or "").lower()

    valid_sponsors = [s.lower() for s in sponsors if s]

    # КРИТИЧНИЙ ФІКС: Розрахунок novelty_score
    # Для швидкодії використовуємо кешовані описи з БД (наразі None, але можна передати)
    novelty_score = calculate_novelty_score(desc, tags, all_projects_descriptions=None)

    # 1. Чи використовує технологію спонсора
    sponsor_tech_hit = any(s in desc or any(s in t.lower() for t in tags) for s in valid_sponsors)

    # 2. Соціальний ухил
    has_social = any(kw in desc for kw in SOCIAL_KEYWORDS)

    # 3. Збіг з номінацією спонсора
    sponsor_challenge_match = any(s in prize_track for s in valid_sponsors) if prize_track else False

    # 4. Наявність відео-демо
    video_platforms = ["youtube.com", "youtu.be", "vimeo.com", "loom.com"]
    has_video_demo = any(vid in desc or vid in demo_url for vid in video_platforms)

    # 5. Призовий фонд (число)
    prize_str = str(hackathon.get("prize_total", "0"))
    prize_digits = re.sub(r"\D", "", prize_str)
    prize_numeric = int(prize_digits) if prize_digits else 0

    # 6. Проксі-показники складності та репутації розробників
    team_size = int(project.get("team_size") or 1)
    participants = int(hackathon.get("participant_count") or 1)
    proj_count = max(total_hackathon_projects, 1)
    competition_density = round(participants / proj_count, 2)

    prize_per_team = round(prize_numeric / team_size, 2) if team_size > 0 else 0

    # КРИТИЧНИЙ ФІКС: Розрахунок days_before_deadline
    days_before_deadline = 0
    try:
        scraped_at = project.get("scraped_at")
        end_date = hackathon.get("end_date")

        if scraped_at and end_date:
            from datetime import datetime

            # Парсимо дати (DuckDB повертає строки у форматі "2024-01-15 10:30:00")
            if isinstance(scraped_at, str):
                scraped_dt = datetime.fromisoformat(scraped_at.replace('Z', '+00:00'))
            else:
                scraped_dt = scraped_at

            if isinstance(end_date, str):
                # Devpost end_date може бути "Jan 15, 2024" або "2024-01-15"
                try:
                    end_dt = datetime.fromisoformat(end_date)
                except ValueError:
                    # Спробуємо інший формат
                    from dateutil import parser
                    end_dt = parser.parse(end_date)
            else:
                end_dt = end_date

            # Розраховуємо різницю в днях
            delta = end_dt - scraped_dt
            days_before_deadline = max(0, delta.days)
    except Exception as e:
        logger.debug(f"Не вдалося розрахувати days_before_deadline: {e}")
        days_before_deadline = 0
    return {
        "uses_sponsor_tech": sponsor_tech_hit,
        "tech_count": len(tags),
        "has_social_angle": has_social,
        "description_length": len(desc),
        "has_github": bool(project.get("github_url")),
        "readme_length": int(project.get("readme_length") or 0),
        "commit_count_48h": int(project.get("commit_count_48h") or 0),
        "likes": int(project.get("likes") or 0),
        "team_size": team_size,
        "sponsor_challenge_match": sponsor_challenge_match,
        "has_video_demo": has_video_demo,
        "competition_density": competition_density,
        "prize_numeric": prize_numeric,
        "github_stars": int(project.get("github_stars") or 0),
        "repo_size": int(project.get("repo_size") or 0),
        "repo_issues": int(project.get("repo_issues") or 0),
        "days_before_deadline": days_before_deadline,
        "prize_per_team": prize_per_team,
        "organizer_reputation": organizer_count,
        "novelty_score": novelty_score
    }
