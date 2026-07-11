import pytest
from src.analyzer.rl_strategy import thompson_sampling_tech_selector, optimize_timeline

class TestRLStrategy:
    """Тести для RL-стратегії (Thompson Sampling та Timeline Optimization)."""

    def test_thompson_sampling_empty_candidates(self):
        """Thompson sampling повертає Docker при відсутності даних."""
        tech = thompson_sampling_tech_selector(None, None)
        assert tech == "Docker"

    def test_thompson_sampling_exploration_vs_exploitation(self):
        """Перевірка вибору технології на основі трендів та статистики перемог."""
        osint_data = {
            "top_winning_tags": {"Python": 10},
            "top_losing_tags": {"Python": 1}
        }
        trends_data = {
            "hacker_news_discussions": ["Supabase"],
            "latest_arxiv_ai_papers": ["Llama-3"]
        }
        
        # Викличемо кілька разів, щоб переконатися, що повертає одного з кандидатів
        for _ in range(20):
            tech = thompson_sampling_tech_selector(osint_data, trends_data)
            assert tech in ["Python", "Supabase", "Llama-3"]

    def test_optimize_timeline_many_techs(self):
        """Оптимізація таймлайну для багатьох технологій (>=5)."""
        timeline = optimize_timeline(tech_count=5, team_size=2)
        assert "Heavy core" in timeline
        assert "15 hours" in timeline

    def test_optimize_timeline_few_techs(self):
        """Оптимізація таймлайну для малої кількості технологій (<5)."""
        timeline = optimize_timeline(tech_count=3, team_size=2)
        assert "Rapid prototyping" in timeline
        assert "10 hours" in timeline
