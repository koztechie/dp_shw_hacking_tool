"""tests/test_predictor.py — Unit-тести для ML-предиктора."""
import pytest

from pathlib import Path
import sys



class TestPredictor:
    """Тести для src/ml/predictor.py."""

    def test_verify_model_integrity_missing_checksum(self, tmp_path):
        """Якщо checksums.txt відсутній, функція завантажує файл без валідації (антикрихкість)."""
        import pickle
        from src.ml.predictor import safe_pickle_load

        model_file = tmp_path / "model.pkl"
        model_file.write_bytes(pickle.dumps({"status": "ok"}))

        result = safe_pickle_load(model_file)
        assert result == {"status": "ok"}

    def test_verify_model_integrity_valid_hash(self, tmp_path):
        """Перевірка збігу хешу."""
        import hashlib
        import pickle
        from src.ml.predictor import safe_pickle_load

        model_file = tmp_path / "model.pkl"
        data = pickle.dumps({"status": "ok"})
        model_file.write_bytes(data)

        expected_hash = hashlib.sha256(data).hexdigest()
        checksum_file = tmp_path / "checksums.txt"
        checksum_file.write_text(f"model.pkl:{expected_hash}\n")

        assert safe_pickle_load(model_file, checksum_file) == {"status": "ok"}

    def test_verify_model_integrity_tampered(self, tmp_path):
        """Якщо файл скомпрометовано, піднімає ValueError."""
        import hashlib
        import pickle
        from src.ml.predictor import safe_pickle_load

        model_file = tmp_path / "model.pkl"
        data = pickle.dumps({"status": "ok"})
        
        # Хеш від оригінальних даних
        original_hash = hashlib.sha256(data).hexdigest()
        checksum_file = tmp_path / "checksums.txt"
        checksum_file.write_text(f"model.pkl:{original_hash}\n")

        # Змінюємо файл
        model_file.write_bytes(b"tampered data")

        with pytest.raises(ValueError, match="скомпрометовано"):
            safe_pickle_load(model_file, checksum_file)

    def test_predict_returns_float(self):
        """predict_win_probability повертає float між 0 та 1."""
        from src.ml.predictor import predict_win_probability

        mock_features = {
            "title": "Test Project",
            "uses_sponsor_tech": True,
            "tech_count": 5,
            "has_social_angle": True,
            "description_length": 500,
            "has_github": True,
        }

        # Функція не повинна падати навіть без моделі
        result = predict_win_probability(mock_features)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


class TestURLValidation:
    """Тести для SSRF-захисту."""

    def test_valid_devpost_url(self):
        from src.api.main import is_safe_devpost_url
        assert is_safe_devpost_url("https://devpost.com/hackathon") is True
        assert is_safe_devpost_url("https://calhacks.devpost.com/") is True

    def test_rejects_http(self):
        from src.api.main import is_safe_devpost_url
        assert is_safe_devpost_url("http://devpost.com/") is False

    def test_rejects_ip(self):
        from src.api.main import is_safe_devpost_url
        assert is_safe_devpost_url("https://192.168.1.1/") is False
        assert is_safe_devpost_url("https://127.0.0.1:8000/") is False

    def test_rejects_other_domains(self):
        from src.api.main import is_safe_devpost_url
        assert is_safe_devpost_url("https://evil.com/devpost") is False
        assert is_safe_devpost_url("https://devpost.com.evil.com/") is False

    def test_rejects_idn_homograph(self):
        from src.api.main import is_safe_devpost_url
        assert is_safe_devpost_url("https://dеvpost.com/") is False  # кирилична 'е'
