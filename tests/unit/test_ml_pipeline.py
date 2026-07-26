import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

from src.ml.prepare_dataset import prepare_dataset
from src.ml.train_model import train
from src.ml.focal_loss import focal_loss_objective
from src.ml.global_ate import calculate_global_ate
from src.ml.experiment_tracker import log_experiment, generate_weekly_report
from src.ml.train_xgboost import train_xgboost
from src.ml.train_ensemble import optimize_hyperparameters

import pathlib as _pl

def _ensure_model_dir():
    """Створює data/models/ з dummy best_model.pkl для HMAC-підпису в CI."""
    model_dir = _pl.Path("data/models")
    model_dir.mkdir(parents=True, exist_ok=True)
    dummy = model_dir / "best_model.pkl"
    if not dummy.exists():
        dummy.write_bytes(b"dummy-model-bytes-for-ci-hmac")



class TestMLPipeline:
    """Тести для ML-пайплайну: підготовка датасету та тренування моделі."""
    
    @patch("src.ml.prepare_dataset.LightweightFeatureStore")
    def test_prepare_dataset_success(self, mock_store_class):
        """Перевірка правильної підготовки датасету з TimeSeriesSplit."""
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        
        # Створюємо синтетичний датасет
        dates = pd.date_range("2024-01-01", periods=10)
        df = pd.DataFrame({
            "scraped_at": dates,
            "uses_sponsor_tech": [True, False] * 5,
            "team_size": np.random.randint(1, 5, 10),
            "is_winner": [0, 1] * 5
        })
        
        # Перемішаємо дати, щоб перевірити сортування
        df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
        mock_store.get_training_data.return_value = df
        
        X_train, X_test, y_train, y_test = prepare_dataset()
        
        # Перевіряємо виклики
        mock_store.snapshot_features.assert_called_once()
        mock_store.get_training_data.assert_called_once()
        
        # Перевіряємо, що scraped_at було видалено з X
        assert "scraped_at" not in X_train.columns
        assert "scraped_at" not in X_test.columns
        
        # Перевіряємо булеві колонки
        assert X_train["uses_sponsor_tech"].dtype == int
        
        # Перевіряємо розбиття (TimeSeriesSplit n_splits=5)
        assert len(X_train) + len(X_test) <= 10
        assert len(X_train) > 0
        assert len(X_test) > 0

    @patch("src.ml.prepare_dataset.LightweightFeatureStore")
    def test_prepare_dataset_empty(self, mock_store_class):
        """Антикрихкість: обробка порожнього датасету."""
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.get_training_data.return_value = pd.DataFrame()
        
        with pytest.raises(ValueError, match="Датасет порожній!"):
            prepare_dataset()

    @patch("src.ml.train_model.cross_val_score")
    @patch("src.ml.train_model.joblib.dump")
    @patch("src.ml.train_model.Path.mkdir")
    @patch("src.ml.train_model.RandomForestClassifier")
    @patch("src.ml.train_model.prepare_dataset_full")
    @patch("pathlib.Path.read_bytes", return_value=b"dummy-model-bytes-for-ci")
    @patch("pathlib.Path.write_bytes")
    @patch("pathlib.Path.read_bytes", return_value=b"dummy-model-bytes-for-ci-hmac")
    def test_train_model_success(self, mock_read_bytes, mock_write_bytes, mock_read, mock_prepare, mock_rf_class, mock_mkdir, mock_dump, mock_cv_score):
        """Успішне тренування класичної моделі та збереження артефактів."""
        mock_cv_score.return_value = np.array([0.9, 0.95])
        X = pd.DataFrame({"feature1": [1, 2, 3], "feature2": [4, 5, 6]})
        y = pd.Series([0, 1, 0])
        mock_prepare.return_value = (X, y)
        
        mock_rf = MagicMock()
        mock_rf_class.return_value = mock_rf
        mock_rf.feature_importances_ = np.array([0.7, 0.3])
        
        model = train()
        
        mock_prepare.assert_called_once()
        mock_rf.fit.assert_called_once_with(X, y)
        assert model == mock_rf
        assert mock_dump.call_count >= 1

class TestFocalLoss:
    """Тести для Focal Loss функції."""
    
    def test_focal_loss_objective(self):
        y_true = np.array([1, 0, 1])
        y_pred = np.array([0.5, -0.5, 2.0]) # logits
        
        grad, hess = focal_loss_objective(y_true, y_pred)
        
        assert grad.shape == (3,)
        assert hess.shape == (3,)
        assert np.all(hess >= 1e-16)

class TestGlobalATE:
    """Тести для статистичного аналізу ATE."""
    
    @patch("src.ml.global_ate.prepare_dataset")
    @patch("src.ml.global_ate.load_model")
    @patch("src.ml.global_ate.Path.exists")
    def test_calculate_global_ate(self, mock_exists, mock_load, mock_prepare):
        mock_exists.return_value = True
        X_train = pd.DataFrame({"uses_sponsor_tech": [1, 0], "has_github": [0, 1]})
        X_test = pd.DataFrame({"uses_sponsor_tech": [1, 0], "has_github": [0, 1]})
        y_train = pd.Series([1, 0])
        y_test = pd.Series([1, 0])
        mock_prepare.return_value = (X_train, X_test, y_train, y_test)
        
        mock_model = MagicMock()
        mock_model.predict_proba.return_value = np.array([[0.1, 0.9], [0.8, 0.2]])
        mock_load.return_value = (mock_model, MagicMock())
        
        calculate_global_ate()
        mock_load.assert_called_once()
        assert mock_model.predict_proba.call_count == 4

class TestExperimentTracker:
    """Тести для трекера експериментів."""
    
    @patch("src.ml.experiment_tracker.duckdb.connect")
    @patch("src.ml.experiment_tracker.joblib.dump")
    @patch("src.ml.experiment_tracker.Path.mkdir")
    def test_log_experiment(self, mock_mkdir, mock_dump, mock_connect):
        mock_con = MagicMock()
        mock_connect.return_value = mock_con
        
        run_id = log_experiment("TestModel", {"lr": 0.01}, {"accuracy": 0.95}, MagicMock())
        
        assert isinstance(run_id, str)
        mock_con.execute.assert_called_once()
        mock_con.close.assert_called_once()

    @patch("src.ml.experiment_tracker.duckdb.connect")
    @patch("src.ml.experiment_tracker.sentry_sdk")
    def test_generate_weekly_report(self, mock_sentry, mock_connect):
        mock_con = MagicMock()
        # Повертаємо фейковий DataFrame з одним рядком
        mock_df = pd.DataFrame({
            "run_id": ["123"],
            "model_name": ["XGBoost"],
            "metrics": ['{"f1_score": 0.85}'],
            "timestamp": ["2026-07-11"]
        })
        mock_con.execute.return_value.fetchdf.return_value = mock_df
        mock_connect.return_value = mock_con
        
        generate_weekly_report()
        mock_sentry.capture_message.assert_called_once()
        mock_con.close.assert_called_once()

class TestTrainXGBoost:
    """Тести для тренування XGBoost моделі."""
    
    @patch("src.ml.train_xgboost.cross_val_score")
    @patch("src.ml.train_xgboost.prepare_dataset_full")
    @patch("src.ml.train_xgboost.SMOTETomek")
    @patch("src.ml.train_xgboost.log_experiment")
    @patch("src.ml.train_xgboost.joblib.dump")
    @patch("src.ml.train_xgboost.XGBClassifier")
    def test_train_xgboost_success(self, mock_xgb_class, mock_dump, mock_log_exp, mock_smote_class, mock_prepare, mock_cv_score):
        mock_cv_score.return_value = np.array([0.9, 0.95])
        X_train = pd.DataFrame({"f1": [1, 2, 3] * 5, "f2": [4, 5, 6] * 5})
        y_train = pd.Series([0, 1, 0] * 5)
        mock_prepare.return_value = (X_train, y_train)
        
        mock_smt = MagicMock()
        mock_smt.fit_resample.return_value = (X_train, y_train)
        mock_smote_class.return_value = mock_smt
        
        mock_xgb = MagicMock()
        mock_xgb.predict_proba.return_value = np.array([[0.2, 0.8], [0.9, 0.1]] * 7 + [[0.5, 0.5]])
        mock_xgb_class.return_value = mock_xgb
        
        train_xgboost()
        
        mock_xgb.fit.assert_called_once()
        mock_log_exp.assert_called_once()
        assert mock_dump.call_count >= 1

class TestTrainEnsemble:
    """Тести для оптимізації та тренування ансамблю моделей."""
    
    @patch("src.ml.train_ensemble.optuna.create_study")
    def test_optimize_hyperparameters(self, mock_create_study):
        mock_study = MagicMock()
        mock_study.best_params = {"rf_max_depth": 5, "xgb_learning_rate": 0.1, "xgb_n_estimators": 150}
        mock_study.best_value = 0.88
        mock_create_study.return_value = mock_study
        
        X_train = pd.DataFrame({"f1": [1, 2, 3], "f2": [4, 5, 6]})
        y_train = pd.Series([0, 1, 0])
        
        best_params = optimize_hyperparameters(X_train, y_train)
        
        assert best_params["rf_max_depth"] == 5
        mock_study.optimize.assert_called_once()

    @patch("src.utils.memory_guard.MemoryGuard.check_memory")
    @patch("src.ml.train_ensemble.prepare_dataset")
    @patch("src.ml.train_ensemble.optimize_hyperparameters")
    @patch("src.ml.train_ensemble.CalibratedClassifierCV")
    @patch("src.ml.train_ensemble.log_experiment")
    @patch("src.ml.predictor._safe_model_load")
    @patch("src.ml.train_ensemble.joblib.dump")
    @patch("src.ml.train_ensemble.Path.exists")
    def test_train_ensemble_success(self, mock_exists, mock_dump, mock_load, mock_log_exp, mock_calibrated_class, mock_opt, mock_prepare, mock_check_mem):
        mock_check_mem.return_value = True
        X_train = pd.DataFrame({"f1": [1, 2, 3], "f2": [4, 5, 6]})
        X_test = pd.DataFrame({"f1": [7, 8], "f2": [9, 10]})
        y_train = pd.Series([0, 1, 0])
        y_test = pd.Series([1, 0])
        mock_prepare.return_value = (X_train, X_test, y_train, y_test)
        mock_opt.return_value = {"rf_max_depth": 5}
        
        mock_calibrated = MagicMock()
        mock_calibrated.predict_proba.return_value = np.array([[0.2, 0.8], [0.9, 0.1]])
        mock_calibrated_class.return_value = mock_calibrated
        
        mock_exists.return_value = False # немає старого лідера
        
        from src.ml.train_ensemble import train_ensemble
        
        with patch.dict("os.environ", {"MODEL_SIGN_KEY": "my-secret-key"}):
            train_ensemble()
        
        mock_calibrated.fit.assert_called()
        mock_log_exp.assert_called_once()
        assert mock_dump.call_count >= 1
