#!/bin/bash
set -e

# АНТИКРИХКІСТЬ: Максимально знижуємо пріоритет процесора (19) та I/O диску (7)
renice -n 19 -p $$ >/dev/null 2>&1 || true
ionice -c2 -n7 -p $$ >/dev/null 2>&1 || true

cd "$(dirname "$0")"
PYTHON_BIN="./venv/bin/python"

echo "=== [$(date)] ЗАПУСК АВТОНОМНОГО MLOps ОНОВЛЕННЯ (Низький пріоритет) ===" >> logs/anacron.log

echo "1. Збір свіжих хакатонів..." >> logs/anacron.log
$PYTHON_BIN -c "from src.scraper.orchestrator import run_full_ingestion; run_full_ingestion(pages=2)" >> logs/anacron.log 2>&1

echo "1.5. Оновлення глобальних трендів..." >> logs/anacron.log
$PYTHON_BIN src/scraper/trend_scraper.py >> logs/anacron.log 2>&1

echo "2. Генерація ознак..." >> logs/anacron.log
$PYTHON_BIN src/analyzer/batch_features.py >> logs/anacron.log 2>&1

echo "3. Перенавчання та змагання моделей..." >> logs/anacron.log
$PYTHON_BIN src/ml/train_ensemble.py >> logs/anacron.log 2>&1

current_count=$($PYTHON_BIN -c "import duckdb; print(duckdb.connect('data/dp_shw.duckdb', read_only=True).execute('SELECT COUNT(*) FROM hackathons').fetchone()[0])")
echo -n "$current_count" > data/models/last_train_count.txt

echo "=== [$(date)] ОНОВЛЕННЯ УСПІШНО ЗАВЕРШЕНО (База: $current_count хак.) ===" >> logs/anacron.log
