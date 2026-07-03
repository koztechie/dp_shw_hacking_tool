import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.base import BaseEstimator, ClassifierMixin
import numpy as np

class HackathonNN(nn.Module):
    """Архітектура мікро-нейромережі для аналізу хакатонів."""
    def __init__(self, input_dim):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid()
        )

    def forward(self, x):
        return self.network(x)

class PyTorchHackathonClassifier(BaseEstimator, ClassifierMixin):
    """
    Scikit-Learn обгортка для PyTorch.
    Повністю сумісна з API Sklearn (включаючи StackingClassifier та cross_val_predict).
    """
    def __init__(self, epochs=20, lr=0.005, batch_size=64):
        self.epochs = epochs
        self.lr = lr
        self.batch_size = batch_size
        self.model_state = None
        self.input_dim = None
        self.classes_ = None        # Буде ініціалізовано у fit()
        self.n_features_in_ = None  # Буде ініціалізовано у fit()

    def fit(self, X, y):
        # Конвертуємо DataFrame/масиви в тензори
        X_arr = np.array(X, dtype=np.float32)
        y_arr = np.array(y, dtype=np.float32).reshape(-1, 1)

        self.input_dim = X_arr.shape[1]
        self.n_features_in_ = self.input_dim # Додано для сумісності з sklearn
        self.classes_ = np.unique(y_arr)     # КРИТИЧНИЙ ФІКС: додано для StackingClassifier
        
        model = HackathonNN(self.input_dim)
        criterion = nn.BCELoss()
        optimizer = optim.Adam(model.parameters(), lr=self.lr)

        X_tensor = torch.tensor(X_arr)
        y_tensor = torch.tensor(y_arr)

        model.train()
        for epoch in range(self.epochs):
            permutation = torch.randperm(X_tensor.size()[0])
            for i in range(0, X_tensor.size()[0], self.batch_size):
                indices = permutation[i:i+self.batch_size]
                batch_x, batch_y = X_tensor[indices], y_tensor[indices]

                optimizer.zero_grad()
                outputs = model(batch_x)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()

        # Зберігаємо ваги
        self.model_state = model.state_dict()
        return self

    def predict_proba(self, X):
        if self.model_state is None:
            raise ValueError("Модель ще не натренована!")

        X_arr = np.array(X, dtype=np.float32)
        model = HackathonNN(self.input_dim)
        model.load_state_dict(self.model_state)
        model.eval()

        X_tensor = torch.tensor(X_arr)
        with torch.no_grad():
            probs = model(X_tensor).numpy()

        # Повертаємо ймовірності для обох класів [клас_0, клас_1]
        return np.hstack([1 - probs, probs])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)
