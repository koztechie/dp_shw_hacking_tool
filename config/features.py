"""
Єдине джерело істини (Single Source of Truth) для ML-ознак нашої моделі.
Використовується для валідації датасетів та структуризації логіки.
"""

ML_FEATURES = {
    "uses_sponsor_tech": bool,       # Чи згадується технологія спонсора в тегах/описі
    "tech_count": int,               # Кількість технологічних тегів
    "has_social_angle": bool,        # healthcare / education / sustainability в описі
    "description_length": int,       # Довжина опису в символах
    "has_github": bool,              # Чи є GitHub-посилання
    "readme_length": int,            # Довжина README (proxy якості документації)
    "commit_count_48h": int,         # Активність розробки
    "likes": int,                    # Лайки (береться з projects)
    "team_size": int,                # Розмір команди (береться з projects)
    "novelty_score": float,          # Схожість з попередніми переможцями
    "sponsor_challenge_match": bool  # Чи подано проект у sponsor challenge трек
}

# Список ознак, які зберігаються саме в таблиці features (а не в projects)
DB_FEATURE_COLUMNS = [k for k in ML_FEATURES.keys() if k not in ["likes", "team_size"]]
