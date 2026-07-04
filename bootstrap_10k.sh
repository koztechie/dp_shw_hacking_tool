#!/bin/bash
set -e

# АНТИКРИХКІСТЬ: Заганяємо процес у найнижчий пріоритет (CPU: 19, Disk: 7),
# щоб ви могли комфортно користуватися комп'ютером під час цих 5 годин.
renice -n 19 -p $$ >/dev/null 2>&1 || true
ionice -c2 -n7 -p $$ >/dev/null 2>&1 || true

cd "$(dirname "$0")"
PYTHON_BIN="./venv/bin/python"

mkdir -p logs data/models data/cache data/feature_store

echo "=== [$(date)] ЗАПУСК МАСОВОЇ ІНІЦІАЛІЗАЦІЇ (~10,000 ПРОЕКТІВ) ==="

echo "▶ [1/4] Збір хакатонів та проектів (12 сторінок)..."
$PYTHON_BIN -c "from src.scraper.orchestrator import run_full_ingestion; run_full_ingestion(pages=12)"

echo "▶ [2/4] Збір світових трендів (Hacker News, ArXiv)..."
$PYTHON_BIN src/scraper/trend_scraper.py

echo "▶ [3/4] Розрахунок 23 ознак та Sentence-BERT ембеддингів..."
$PYTHON_BIN src/analyzer/batch_features.py

echo "▶ [4/4] Тренування Ансамблю (RF + XGBoost + PyTorch)..."
$PYTHON_BIN src/ml/train_ensemble.py

# Фіксація успіху
current_count=$($PYTHON_BIN -c "import duckdb; print(duckdb.connect('data/dp_shw.duckdb', read_only=True).execute('SELECT COUNT(*) FROM hackathons').fetchone()[0])")
echo -n "$current_count" > data/models/last_train_count.txt

echo "=== [$(date)] ІНІЦІАЛІЗАЦІЮ ЗАВЕРШЕНО! У БАЗІ: $current_count ХАКАТОНІВ ==="
