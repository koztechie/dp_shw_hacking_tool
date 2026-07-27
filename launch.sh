#!/bin/bash
cd /home/koztechie/dev/dp_shw_hacking_tool || { echo "❌ Папку не знайдено"; read; exit 1; }

echo "========================================="
echo "  DP_SHW_Hacking_Tool — запуск..."
echo "========================================="
echo ""

# Перевірка venv
if [ ! -f "venv/bin/python" ]; then
    echo "⚠️  venv відсутній. Створюю..."
    python3 -m venv venv || { echo "❌ Не вдалося створити venv"; read; exit 1; }
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt || { echo "❌ Помилка встановлення залежностей"; read; exit 1; }
fi

# Перевірка .env
if [ ! -f ".env" ]; then
    echo "⚠️  .env відсутній! Створюю приклад..."
    cp .env.example .env 2>/dev/null || echo "MIMO_API_KEY=your_key" > .env
    echo "   ⚡ Відредагуй .env перед використанням!"
fi

echo ""
echo "🚀 Запуск сервера на http://127.0.0.1:8000"
echo "   Натисни Ctrl+C для зупинки"
echo "========================================="
echo ""

# Запуск сервера + браузер
./venv/bin/python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!

sleep 3
xdg-open http://127.0.0.1:8000 2>/dev/null

# Чекаємо на сервер. Якщо він впав — показуємо помилку
wait $SERVER_PID
EXIT_CODE=$?

echo ""
echo "========================================="
if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ Сервер завершився з помилкою (код: $EXIT_CODE)"
else
    echo "✅ Сервер зупинено"
fi
echo "========================================="
read -p "Натисни Enter для виходу..."
