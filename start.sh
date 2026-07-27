#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

# ── Swap 2GB (захист від OOM на 6GB RAM) ──────────────────────
if [ ! -f /swapfile ]; then
    echo "⚙️  Створення 2GB swap файлу..."
    if command -v sudo &>/dev/null && sudo -n true 2>/dev/null; then
        sudo fallocate -l 2G /swapfile
        sudo chmod 600 /swapfile
        sudo mkswap /swapfile
    else
        echo "⚠️  sudo недоступний без пароля. Пропускаю створення swap."
    fi
fi
# Активуємо swap, якщо ще не активний (не падаємо при помилці)
if [ -f /swapfile ] && ! swapon --show=NAME --noheadings | grep -q '/swapfile'; then
    sudo swapon /swapfile 2>/dev/null || echo "⚠️  Не вдалося активувати swap (можливо, вже активний)."
fi

# ── Обмеження пам'яті ─────────────────────────────────────────
# 8GB віртуального простору (numpy/scipy/xgboost резервують багато)
ulimit -v 8388608 2>/dev/null || true
export PYTHONDONTWRITEBYTECODE=1
# НЕ встановлюємо PYTHONMALLOC=malloc — pymalloc ефективніший

# ── Перевірка python3 ─────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "❌ python3 не знайдено. Встановіть: sudo apt install python3 python3-venv"
    exit 1
fi

# ── Антикриткість: venv ───────────────────────────────────────
if [ ! -f "venv/bin/python" ]; then
    echo "🔧 Створення віртуального середовища..."
    python3 -m venv venv
    echo "📦 Встановлення залежностей..."
    ./venv/bin/pip install --upgrade pip
fi

if [ ! -f "requirements.txt" ]; then
    echo "❌ requirements.txt не знайдено у $(pwd)"
    exit 1
fi

./venv/bin/pip install -q -r requirements.txt

# Перевірка цілісності venv
if ! ./venv/bin/python -c "import fastapi" 2>/dev/null; then
    echo "⚠️  Залежності пошкоджено. Перевстановлення..."
    ./venv/bin/pip install -q -r requirements.txt
fi

# ── Перевірка .env ────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "⚠️  Файл .env відсутній! Створюю .env.example..."
    cat > .env.example << 'ENVEOF'
MIMO_API_KEY=your_mimo_api_key_here
SENTRY_DSN=
CSRF_SECRET=generate-a-random-64-char-string
MODEL_SIGN_KEY=generate-a-random-64-char-string
API_SECRET_KEY=generate-a-random-64-char-string
ENVEOF
    echo "   Скопіюйте .env.example → .env і заповніть ключі."
fi

# ── Ініціалізація БД ──────────────────────────────────────────
./venv/bin/python -c "from src.db import init_db; init_db()" 2>/dev/null || true

# ── Запуск ────────────────────────────────────────────────────
echo "====================================================="
echo "⚡ DP_SHW_Hacking_Tool запускається..."
echo "📊 Відкрий браузер: http://127.0.0.1:8000"
echo "🛑 Зупинка: Ctrl+C"
echo "====================================================="

exec ./venv/bin/python -m uvicorn src.api.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 1 \
    --limit-request-line 8190 \
    --limit-request-field_size 8190 \
    --limit-max-requests 1000 \
    --timeout-keep-alive 5 \
    --log-level info
