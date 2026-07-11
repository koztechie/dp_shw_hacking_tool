from unittest.mock import patch

from src.analyzer.idea_generator import generate_winning_ideas
from src.analyzer.techspec_generator import generate_techspec

class TestAIGenerators:
    """Тести для AI генераторів ідей та технічних специфікацій."""
    
    @patch("src.analyzer.idea_generator.prompt_manager")
    @patch("src.analyzer.idea_generator.generate_json_with_failover")
    def test_generate_winning_ideas_success(self, mock_generate, mock_prompt_manager):
        """Успішна генерація ідей через два агенти (Brainstormer + Critic)."""
        # Мокуємо відповіді для обох агентів
        mock_generate.side_effect = [
            {"draft": "draft idea"},  # Відповідь Brainstormer
            {"ideas": [{"title": "Super Idea", "tech_stack": ["Python"]}]}  # Відповідь Critic
        ]
        
        hackathon_data = {"title": "Test Hackathon"}
        constraints = {"rule": "No web2"}
        
        result = generate_winning_ideas(hackathon_data, {}, constraints)
        
        assert len(result) == 1
        assert result[0]["title"] == "Super Idea"
        assert mock_generate.call_count == 2
        mock_prompt_manager.update_prompt_metrics.assert_called()

    @patch("src.analyzer.idea_generator.prompt_manager")
    @patch("src.analyzer.idea_generator.generate_json_with_failover")
    def test_generate_winning_ideas_fallback(self, mock_generate, mock_prompt_manager):
        """Антикрихкість: при падінні API Critic'а повертаються дефолтні ідеї."""
        # Другий агент повертає помилку fallback
        mock_generate.side_effect = [
            {"draft": "draft idea"},
            {"fallback": True, "error": "API failed"}
        ]
        
        result = generate_winning_ideas({"title": "Test Hackathon"}, {}, {})
        
        assert len(result) == 3
        assert result[0]["title"] == "Offline Web App"
        assert mock_generate.call_count == 2

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
