#!/bin/bash
set -e

# Переходимо в директорію проекту (антикрихкість шляхів)
cd "$(dirname "$0")"

# Шлях до інтерпретатора віртуального середовища
PYTHON_BIN="./venv/bin/python"

echo "=== [$(date)] ЗАПУСК АВТОНОМНОГО MLOps ОНОВЛЕННЯ ===" >> logs/anacron.log

# 1. Збір свіжих хакатонів (2 сторінки = 48 найсвіжіших хакатонів за тиждень)
echo "1. Збір свіжих хакатонів..." >> logs/anacron.log
$PYTHON_BIN -c "from src.scraper.orchestrator import run_full_ingestion; run_full_ingestion(pages=2)" >> logs/anacron.log 2>&1

# 1.5. Оновлення глобальних технологічних трендів (Hacker News, ArXiv)
echo "1.5. Оновлення глобальних трендів..." >> logs/anacron.log
$PYTHON_BIN src/scraper/trend_scraper.py >> logs/anacron.log 2>&1

# 2. Перерахунок розширених ознак для всієї бази (LSA + Video + Stars)
echo "2. Генерація ознак..." >> logs/anacron.log
$PYTHON_BIN src/analyzer/batch_features.py >> logs/anacron.log 2>&1

# 3. Перенавчання та змагання моделей (Stacking RF + XGBoost)
echo "3. Перенавчання та змагання моделей..." >> logs/anacron.log
$PYTHON_BIN src/ml/train_ensemble.py >> logs/anacron.log 2>&1

# 4. Оновлення лічильника останнього тренування
current_count=$($PYTHON_BIN -c "import duckdb; print(duckdb.connect('data/dp_shw.duckdb', read_only=True).execute('SELECT COUNT(*) FROM hackathons').fetchone()[0])")
echo -n "$current_count" > data/models/last_train_count.txt

echo "=== [$(date)] ОНОВЛЕННЯ УСПІШНО ЗАВЕРШЕНО (База: $current_count хак.) ===" >> logs/anacron.log
