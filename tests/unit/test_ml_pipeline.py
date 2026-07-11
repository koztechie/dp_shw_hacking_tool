import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

from src.ml.prepare_dataset import prepare_dataset
from src.ml.train_model import train

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
        
        # Перевіряємо розбиття (TimeSeriesSplit n_splits=5 -> train_size збільшується)
        # Останній фолд для 10 елементів: test size ~ 1-2
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

    @patch("src.ml.train_model.pickle.dump")
    @patch("src.ml.train_model.Path.mkdir")
    @patch("builtins.open")
    @patch("src.ml.train_model.RandomForestClassifier")
    @patch("src.ml.train_model.prepare_dataset")
    def test_train_model_success(self, mock_prepare, mock_rf_class, mock_open, mock_mkdir, mock_dump):
        """Успішне тренування моделі та збереження артефактів."""
        # Мокуємо підготовлені дані
        X_train = pd.DataFrame({"feature1": [1, 2, 3], "feature2": [4, 5, 6]})
        X_test = pd.DataFrame({"feature1": [7, 8], "feature2": [9, 10]})
        y_train = pd.Series([0, 1, 0])
        y_test = pd.Series([1, 0])
        mock_prepare.return_value = (X_train, X_test, y_train, y_test)
        
        # Мокуємо модель
        mock_rf = MagicMock()
        mock_rf_class.return_value = mock_rf
        mock_rf.predict.return_value = np.array([1, 0])
        mock_rf.predict_proba.return_value = np.array([[0.2, 0.8], [0.9, 0.1]])
        mock_rf.feature_importances_ = np.array([0.7, 0.3])
        
        model = train()
        
        # Перевіряємо виклики
        mock_prepare.assert_called_once()
        mock_rf.fit.assert_called_once_with(X_train, y_train)
        mock_rf.predict.assert_called_once_with(X_test)
        mock_rf.predict_proba.assert_called_once_with(X_test)
        
        assert model == mock_rf
        
        # Перевіряємо збереження (model, best_model, feature_names)
        assert mock_open.call_count == 3
        assert mock_dump.call_count == 3
