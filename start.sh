#!/bin/bash
set -e

cd "$(dirname "$0")"

# Swap 2GB (створюємо, якщо ще не існує)
if [ ! -f /swapfile ]; then
    echo "⚙️ Створення 2GB swap файлу для захисту від OOM..."
    sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
    sudo mkswap /swapfile && sudo swapon /swapfile
fi

# Обмеження пам'яті процесу
ulimit -v 5242880  # 5GB virtual memory
export PYTHONDONTWRITEBYTECODE=1
export PYTHONMALLOC=malloc  # Агресивне звільнення

# АНТИКРИХКІСТЬ: Автоматичне створення та відновлення venv
if [ ! -f "venv/bin/python" ]; then
    echo "🔧 Створення віртуального середовища..."
    python3 -m venv venv
    echo "📦 Встановлення залежностей..."
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
fi

# Перевірка цілісності venv
if ! ./venv/bin/python -c "import fastapi" 2>/dev/null; then
    echo "⚠️ Залежності пошкоджено. Перевстановлення..."
    ./venv/bin/pip install -r requirements.txt
fi

# Перевірка .env файлу
if [ ! -f ".env" ]; then
    echo "⚠️ Файл .env відсутній! Створіть його згідно з README.md"
    echo "GEMINI_API_KEY=your_key" > .env.example
    echo "OPENROUTER_API_KEY=sk-or-v1-your_key" >> .env.example
    echo "SENTRY_DSN=" >> .env.example
fi

# Ініціалізація БД
./venv/bin/python -c "from src.db import init_db; init_db()" 2>/dev/null || true

echo "====================================================="
echo "⚡ DP_SHW_Hacking_Tool запускається..."
echo "📊 Відкрий браузер: http://127.0.0.1:8000"
echo "🛑 Зупинка: Ctrl+C"
echo "====================================================="

exec ./venv/bin/python -m uvicorn src.api.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --limit-request-line 8190 \
    --limit-request-field_size 8190 \
    --limit-max-requests 1000 \
    --timeout-keep-alive 5
