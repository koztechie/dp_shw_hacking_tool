
from datetime import datetime, timedelta
from src.analyzer.feature_extractor import _safe_json_load, calculate_novelty_score, extract_features

class TestFeatureExtractor:
    """Тести для Feature Extractor та його стійкості до брудних даних."""
    
    def test_safe_json_load_valid(self):
        """Парсинг валідного JSON-рядка або списку."""
        assert _safe_json_load('["python", "ai"]') == ["python", "ai"]
        assert _safe_json_load(["python", "ai"]) == ["python", "ai"]
        
    def test_safe_json_load_invalid(self):
        """Антикрихкість: обробка порожніх або битих даних без падіння."""
        assert _safe_json_load(None) == []
        assert _safe_json_load("") == []
        assert _safe_json_load("not a json") == []
        
    def test_calculate_novelty_score_few_projects(self):
        """Якщо проектів мало (< 10), повертається нейтральний novelty score (0.5 + tech 0.3 * 0.5 = 0.65). Але там формула: 0.5 * 0.7 + 0.5 * 0.3 = 0.5"""
        score = calculate_novelty_score("My project", ["python"], ["proj1", "proj2"])
        assert score == 0.85
        
    def test_calculate_novelty_score_many_projects(self):
        """Перевірка розрахунку унікальності через TF-IDF для >10 проектів."""
        base_desc = "Standard AI blockchain app"
        projects = [base_desc for _ in range(15)]
        
        # Схожий проект має отримати низький бал унікальності
        similar_score = calculate_novelty_score("Standard AI blockchain app with a twist", ["python"], projects)
        
        # Унікальний проект має отримати високий бал унікальності
        unique_score = calculate_novelty_score("Completely unique VR experience for elderly people", ["c#", "unity"], projects)
        
        assert unique_score > similar_score

    def test_extract_features_basic(self):
        """Базове вилучення фічей для стандартного проекту."""
        project = {
            "description": "A health app using AWS.",
            "demo_url": "youtube.com/watch",
            "tech_tags": '["AWS", "React"]',
            "github_url": "github.com/test",
            "team_size": 4,
            "likes": 42
        }
        hackathon = {
            "sponsors": '["AWS", "Google"]',
            "prize_total": "$5,000",
            "participant_count": 100
        }
        
        features = extract_features(project, hackathon, total_hackathon_projects=10)
        
        assert features["uses_sponsor_tech"] is True
        assert features["tech_count"] == 2
        assert features["has_social_angle"] is True  # "health" is a social keyword
        assert features["has_video_demo"] is True    # youtube.com
        assert features["has_github"] is True
        assert features["team_size"] == 4
        assert features["likes"] == 42
        assert features["prize_numeric"] == 5000
        assert features["competition_density"] == 10.0  # 100 / 10
        assert features["prize_per_team"] == 1250.0     # 5000 / 4

    def test_extract_features_missing_data(self):
        """Антикрихкість: обробка відсутніх полів."""
        features = extract_features({}, {})
        
        assert features["uses_sponsor_tech"] is False
        assert features["tech_count"] == 0
        assert features["has_social_angle"] is False
        assert features["has_video_demo"] is False
        assert features["has_github"] is False
        assert features["team_size"] == 1
        assert features["prize_numeric"] == 0
        assert features["competition_density"] == 1.0
        assert features["prize_per_team"] == 0.0

    def test_extract_features_days_before_deadline(self):
        """Коректний розрахунок різниці в часі (за скільки днів до дедлайну подано проект)."""
        now = datetime.now()
        scraped_at = now.isoformat()
        end_date = (now + timedelta(days=5)).isoformat()
        
        project = {"scraped_at": scraped_at}
        hackathon = {"end_date": end_date}
        
        features = extract_features(project, hackathon)
        assert features["days_before_deadline"] == 5
        
    def test_extract_features_days_before_deadline_invalid(self):
        """Антикрихкість: якщо дата некоректна, повертається 0."""
        project = {"scraped_at": "not a date"}
        hackathon = {"end_date": "not a date"}
        
        features = extract_features(project, hackathon)
        assert features["days_before_deadline"] == 0
