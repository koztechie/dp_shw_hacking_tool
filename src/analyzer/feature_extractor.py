import json
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

SOCIAL_KEYWORDS = [
    "health", "mental", "education", "accessib", "sustainab",
    "climate", "poverty", "disaster", "elderly", "disability"
]

def _safe_json_load(data) -> list:
    if not data: return []
    if isinstance(data, list): return data
    try: return json.loads(data)
    except Exception: return []

def extract_features(project: dict, hackathon: dict, total_hackathon_projects: int = 1) -> dict:
    desc = (project.get("description") or "").lower()
    demo_url = (project.get("demo_url") or "").lower()
    tags = _safe_json_load(project.get("tech_tags"))
    sponsors = _safe_json_load(hackathon.get("sponsors"))
    prize_track = (project.get("prize_track") or "").lower()

    valid_sponsors = [s.lower() for s in sponsors if s]

    sponsor_tech_hit = any(s in desc or any(s in t.lower() for t in tags) for s in valid_sponsors)
    has_social = any(kw in desc for kw in SOCIAL_KEYWORDS)
    sponsor_challenge_match = any(s in prize_track for s in valid_sponsors) if prize_track else False

    # НОВА ФІЧА: Наявність відео-демо (Critical for winning)
    video_platforms = ["youtube.com", "youtu.be", "vimeo.com", "loom.com"]
    has_video_demo = any(vid in desc or vid in demo_url for vid in video_platforms)

    # НОВА ФІЧА: Конвертація призів у числа
    prize_str = str(hackathon.get("prize_total", "0"))
    prize_digits = re.sub(r"\D", "", prize_str)
    prize_numeric = int(prize_digits) if prize_digits else 0

    # НОВА ФІЧА: Щільність конкуренції (скільки учасників припадає на 1 проект)
    participants = int(hackathon.get("participant_count") or 1)
    # Щоб уникнути ділення на нуль
    proj_count = max(total_hackathon_projects, 1)
    competition_density = round(participants / proj_count, 2)

    return {
        "uses_sponsor_tech": sponsor_tech_hit,
        "tech_count": len(tags),
        "has_social_angle": has_social,
        "description_length": len(desc),
        "has_github": bool(project.get("github_url")),
        "readme_length": int(project.get("readme_length") or 0),
        "commit_count_48h": int(project.get("commit_count_48h") or 0),
        "likes": int(project.get("likes") or 0),
        "team_size": int(project.get("team_size") or 1),
        "sponsor_challenge_match": sponsor_challenge_match,
        "has_video_demo": has_video_demo,
        "competition_density": competition_density,
        "prize_numeric": prize_numeric,
        "github_stars": int(project.get("github_stars") or 0)
    }

def compute_novelty_scores(descriptions: list[str]) -> list[float]:
    """Залишаємо стару логіку TF-IDF унікальності"""
    if not descriptions or len(descriptions) < 2:
        return [0.5] * len(descriptions)
    clean_desc = [str(d) if d else "" for d in descriptions]
    try:
        vec = TfidfVectorizer(max_features=500, stop_words="english")
        matrix = vec.fit_transform(clean_desc)
        sim_matrix = cosine_similarity(matrix)
        avg_sim = (sim_matrix.sum(axis=1) - 1) / (len(descriptions) - 1)
        return [round(float(score), 4) for score in (1.0 - avg_sim)]
    except ValueError:
        return [0.5] * len(descriptions)
