import numpy as np

def focal_loss_objective(y_true, y_pred):
    """
    Математично стійка реалізація Focal Loss для XGBoost.
    Збережено в окремому файлі для усунення помилок PicklingError при серіалізації.
    """
    gamma = 2.0
    alpha = 0.25
    
    # Переводимо логіти в ймовірність
    p = 1.0 / (1.0 + np.exp(-y_pred))
    
    # Градієнт
    grad = p - y_true
    
    # Модуляція ваг
    weight = alpha * y_true * np.power(1 - p, gamma) + (1 - alpha) * (1 - y_true) * np.power(p, gamma)
    grad = weight * grad
    
    # Стабільний Гессіан
    hess = np.maximum(p * (1 - p) * weight, 1e-16)
    
    return grad, hess
