"""tests/test_predictor.py — Unit-тести для ML-предиктора."""
import pytest

from unittest.mock import patch



class TestPredictor:
    """Тести для src/ml/predictor.py."""

    @patch("src.ml.predictor.os.getenv")
    def test_verify_model_integrity_missing_signature(self, mock_getenv, tmp_path):
        """Якщо підпис відсутній, піднімається RuntimeError."""
        mock_getenv.return_value = "my-secret-key"
        import joblib
        from src.ml.predictor import _safe_model_load
        
        model_file = tmp_path / "model.pkl"
        joblib.dump({"status": "ok"}, model_file)
        
        with pytest.raises(RuntimeError, match="Підпис моделі не валідний"):
            _safe_model_load(model_file)

    @patch("src.ml.predictor.os.getenv")
    def test_verify_model_integrity_valid_signature(self, mock_getenv, tmp_path):
        """Перевірка збігу HMAC підпису."""
        mock_getenv.return_value = "my-secret-key"
        import hmac
        import hashlib
        import joblib
        from src.ml.predictor import _safe_model_load
        
        model_file = tmp_path / "model.pkl"
        joblib.dump({"status": "ok"}, model_file)
        
        sig_file = tmp_path / "model.sig"
        secret = b"my-secret-key"
        sig = hmac.new(secret, model_file.read_bytes(), hashlib.sha256).digest()
        sig_file.write_bytes(sig)
        
        result = _safe_model_load(model_file)
        assert result == {"status": "ok"}

    @patch("src.ml.predictor.os.getenv")
    def test_verify_model_integrity_tampered(self, mock_getenv, tmp_path):
        """Якщо файл скомпрометовано, піднімає RuntimeError."""
        mock_getenv.return_value = "my-secret-key"
        import hmac
        import hashlib
        import joblib
        from src.ml.predictor import _safe_model_load

        model_file = tmp_path / "model.pkl"
        joblib.dump({"status": "ok"}, model_file)
        
        sig_file = tmp_path / "model.sig"
        secret = b"my-secret-key"
        sig = hmac.new(secret, model_file.read_bytes(), hashlib.sha256).digest()
        sig_file.write_bytes(sig)
        
        # Змінюємо файл
        model_file.write_bytes(b"tampered data")
        
        with pytest.raises(RuntimeError, match="Підпис моделі не валідний"):
            _safe_model_load(model_file)

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
        from src.api.routes_analyze import is_safe_devpost_url
        assert is_safe_devpost_url("https://devpost.com/hackathon") is True
        assert is_safe_devpost_url("https://calhacks.devpost.com/") is True

    def test_rejects_http(self):
        from src.api.routes_analyze import is_safe_devpost_url
        assert is_safe_devpost_url("http://devpost.com/") is False

    def test_rejects_ip(self):
        from src.api.routes_analyze import is_safe_devpost_url
        assert is_safe_devpost_url("https://192.168.1.1/") is False
        assert is_safe_devpost_url("https://127.0.0.1:8000/") is False

    def test_rejects_other_domains(self):
        from src.api.routes_analyze import is_safe_devpost_url
        assert is_safe_devpost_url("https://evil.com/devpost") is False
        assert is_safe_devpost_url("https://devpost.com.evil.com/") is False

    def test_rejects_idn_homograph(self):
        from src.api.routes_analyze import is_safe_devpost_url
        assert is_safe_devpost_url("https://dеvpost.com/") is False  # кирилична 'е'
