import json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SOCIAL_KEYWORDS = [
    "health", "mental", "education", "accessib", "sustainab",
    "climate", "poverty", "disaster", "elderly", "disability"
]

def _safe_json_load(data) -> list:
    """Безпечно парсить JSON."""
    if not data:
        return []
    if isinstance(data, list):
        return data
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return []

def extract_features(project: dict, hackathon: dict) -> dict:
    """Перетворює сирі словники проекту та хакатону на ознаки для ML."""
    desc = (project.get("description") or "").lower()
    tags = _safe_json_load(project.get("tech_tags"))
    sponsors = _safe_json_load(hackathon.get("sponsors"))
    prize_track = (project.get("prize_track") or "").lower()

    valid_sponsors = [s.lower() for s in sponsors if s]

    sponsor_tech_hit = any(
        s in desc or any(s in t.lower() for t in tags)
        for s in valid_sponsors
    )

    has_social = any(kw in desc for kw in SOCIAL_KEYWORDS)
    
    sponsor_challenge_match = False
    if prize_track:
        sponsor_challenge_match = any(s in prize_track for s in valid_sponsors)

    likes = int(project.get("likes") or 0)
    team_size = int(project.get("team_size") or 1)
    readme_length = int(project.get("readme_length") or 0)
    commit_count_48h = int(project.get("commit_count_48h") or 0)

    return {
        "uses_sponsor_tech": sponsor_tech_hit,
        "tech_count": len(tags),
        "has_social_angle": has_social,
        "description_length": len(desc),
        "has_github": bool(project.get("github_url")),
        "readme_length": readme_length,
        "commit_count_48h": commit_count_48h,
        "likes": likes,
        "team_size": team_size,
        "sponsor_challenge_match": sponsor_challenge_match
    }

def compute_novelty_scores(descriptions: list[str]) -> list[float]:
    """
    Обчислює унікальність ідей на основі TF-IDF та косинусної схожості.
    Низький novelty_score = схожа на інші ідеї (клон).
    Високий = унікальна.
    """
    if not descriptions or len(descriptions) < 2:
        return [0.5] * len(descriptions)
        
    # Замінюємо None на порожні рядки
    clean_desc = [str(d) if d else "" for d in descriptions]
    
    vec = TfidfVectorizer(max_features=500, stop_words="english")
    
    try:
        matrix = vec.fit_transform(clean_desc)
    except ValueError:
        # Спрацьовує, якщо всі описи порожні або містять лише стоп-слова
        return [0.5] * len(descriptions)
        
    sim_matrix = cosine_similarity(matrix)
    
    # Середня схожість проекту з усіма іншими проектами хакатону
    # Віднімаємо 1, щоб не враховувати схожість проекту самого з собою (по діагоналі матриці завжди 1.0)
    avg_sim = (sim_matrix.sum(axis=1) - 1) / (len(descriptions) - 1)
    
    # Новизна обернено пропорційна схожості
    novelty = 1.0 - avg_sim
    return [round(float(score), 4) for score in novelty]

if __name__ == "__main__":
    print("=== ТЕСТУВАННЯ NOVELTY SCORE ===")
    
    test_descriptions = [
        "We built an AI chatbot using OpenAI to help students learn math.",  # Ідея 1
        "Our project is an AI chatbot that uses OpenAI for learning math.", # Ідея 2 (клон першої)
        "A hardware device for detecting water leaks in urban pipes using IoT sensors." # Ідея 3 (унікальна)
    ]
    
    scores = compute_novelty_scores(test_descriptions)
    
    for i, (desc, score) in enumerate(zip(test_descriptions, scores), 1):
        print(f"\nПроект {i}: {desc}")
        print(f"Novelty Score: {score}")
        if score < 0.6:
            print("Висновок: Клон / Банальна ідея")
        else:
            print("Висновок: Висока унікальність")
