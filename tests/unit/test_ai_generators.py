from unittest.mock import patch

from src.analyzer.idea_generator import generate_winning_ideas
from src.analyzer.techspec_generator import generate_techspec

class TestAIGenerators:
    """Тести для AI генераторів ідей та технічних специфікацій."""
    
    @patch("src.scraper.app_store_scraper.check_existing_apps")
    @patch("src.analyzer.idea_generator.prompt_manager")
    @patch("src.analyzer.idea_generator.generate_json_with_failover")
    def test_generate_winning_ideas_success(self, mock_generate, mock_prompt_manager, mock_check_apps):
        """Успішна генерація ідей через три агенти (Brainstormer -> Uniqueness -> Critic)."""
        mock_check_apps.return_value = [{"title": "Competitor App"}]
        
        # Мокуємо відповіді для агентів
        mock_generate.side_effect = [
            {"draft_ideas": [{"title": "Draft Idea"}]},  # Відповідь Brainstormer
            {"reasoning": "Unique", "is_unique": True, "max_similarity_percentage": 10, "prompt_modification": ""}, # Відповідь Uniqueness Checker
            {"ideas": [{"title": "Super Idea", "tech_stack": ["Python"]}]}  # Відповідь Critic
        ]
        
        hackathon_data = {"title": "Test Hackathon"}
        constraints = {"rule": "No web2"}
        
        result = generate_winning_ideas(hackathon_data, {}, constraints)
        
        assert len(result) == 1
        assert result[0]["title"] == "Super Idea"
        assert mock_generate.call_count == 3
        mock_prompt_manager.update_prompt_metrics.assert_called()

    @patch("src.scraper.app_store_scraper.check_existing_apps")
    @patch("src.analyzer.idea_generator.prompt_manager")
    @patch("src.analyzer.idea_generator.generate_json_with_failover")
    def test_generate_winning_ideas_retry_uniqueness(self, mock_generate, mock_prompt_manager, mock_check_apps):
        """Перевірка циклу регенерації, якщо ідея не унікальна."""
        mock_check_apps.return_value = []
        
        mock_generate.side_effect = [
            {"draft_ideas": [{"title": "Clone Idea"}]},  # Спроба 1
            {"reasoning": "Too similar", "is_unique": False, "max_similarity_percentage": 85, "prompt_modification": "Avoid clones"}, # Не унікально
            {"draft_ideas": [{"title": "Unique Idea"}]},  # Спроба 2
            {"reasoning": "Okay", "is_unique": True, "max_similarity_percentage": 20, "prompt_modification": ""}, # Унікально
            {"ideas": [{"title": "Super Unique Idea", "tech_stack": ["Rust"]}]}  # Critic
        ]
        
        result = generate_winning_ideas({"title": "Hackathon"}, {}, {})
        
        assert len(result) == 1
        assert result[0]["title"] == "Super Unique Idea"
        assert mock_generate.call_count == 5

    @patch("src.scraper.app_store_scraper.check_existing_apps")
    @patch("src.analyzer.idea_generator.prompt_manager")
    @patch("src.analyzer.idea_generator.generate_json_with_failover")
    def test_generate_winning_ideas_fallback(self, mock_generate, mock_prompt_manager, mock_check_apps):
        """Антикрихкість: при падінні API Critic'а повертаються дефолтні ідеї."""
        mock_check_apps.return_value = []
        
        mock_generate.side_effect = [
            {"draft_ideas": [{"title": "Draft Idea"}]},
            {"reasoning": "Unique", "is_unique": True, "max_similarity_percentage": 10, "prompt_modification": ""},
            {"fallback": True, "error": "API failed"}
        ]
        
        result = generate_winning_ideas({"title": "Test Hackathon"}, {}, {})
        
        assert len(result) == 3
        assert result[0]["title"] == "Offline Web App"
        assert mock_generate.call_count == 3

    @patch("src.analyzer.techspec_generator.context_manager")
    @patch("src.analyzer.techspec_generator.generate_json_with_failover")
    def test_generate_techspec_success(self, mock_generate, mock_context):
        """Успішна генерація технічної специфікації."""
        mock_context.truncate_to_fit.return_value = ("truncated prompt", {})
        
        expected_spec = {
            "project_name": "Test Project",
            "architecture": {"frontend": "React"}
        }
        mock_generate.return_value = expected_spec
        
        result = generate_techspec({"title": "Idea"}, {"title": "Hack"})
        
        assert result == expected_spec
        mock_generate.assert_called_once()
        mock_context.truncate_to_fit.assert_called_once()

    @patch("src.analyzer.techspec_generator.context_manager")
    @patch("src.analyzer.techspec_generator.generate_json_with_failover")
    def test_generate_techspec_fallback(self, mock_generate, mock_context):
        """Антикрихкість: при падінні API повертається детерміноване офлайн ТЗ."""
        mock_context.truncate_to_fit.return_value = ("truncated prompt", {})
        
        # API повертає помилку
        mock_generate.return_value = {"fallback": True, "error": "Timeout"}
        
        idea = {"title": "My Fallback Idea", "tagline": "Test"}
        result = generate_techspec(idea, {"title": "Hack"})
        
        assert result["project_name"] == "My Fallback Idea"
        assert result["tagline"] == "Test"
        assert result["architecture"]["database"] == "SQLite - zero config"
        assert mock_generate.assert_called_once
