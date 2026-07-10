#!/bin/bash
# АНТИКРИХКІСТЬ: Щоденний автоматичний backup з verification

set -euo pipefail

cd /home/koztechie/dev/dp_shw_hacking_tool

# Логування в окремий файл
exec >> /home/koztechie/dev/dp_shw_hacking_tool/logs/backup.log 2>&1

echo "=== [$(date)] Початок щоденного backup ==="

# 1. Створення backup
./venv/bin/python src/db_backup.py

# 2. Verification: перевірка цілісності останнього backup
BACKUP_DIR="data/backups"
LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/dp_shw_*.duckdb.gz 2>/dev/null | head -n1)

if [ -z "$LATEST_BACKUP" ]; then
    echo "❌ КРИТИЧНО: Backup не створено!"
    exit 1
fi

echo "🔍 Перевірка цілісності: $LATEST_BACKUP"

# Розпаковуємо в тимчасову директорію
TEMP_DIR=$(mktemp -d)
gunzip -c "$LATEST_BACKUP" > "$TEMP_DIR/test.duckdb"

# Перевіряємо, чи можна відкрити БД
if ./venv/bin/python -c "
import duckdb
try:
    con = duckdb.connect('$TEMP_DIR/test.duckdb', read_only=True)
    count = con.execute('SELECT COUNT(*) FROM hackathons').fetchone()[0]
    print(f'✅ Backup валідний. Хакатонів: {count}')
    con.close()
except Exception as e:
    print(f'❌ Backup пошкоджений: {e}')
    exit(1)
"; then
    echo "✅ Backup verification пройшло успішно"
else
    echo "❌ КРИТИЧНО: Backup пошкоджений!"
    rm -rf "$TEMP_DIR"
    exit 1
fi

rm -rf "$TEMP_DIR"

# 3. Offsite backup (опціонально: копіювання в хмару)
# rsync -avz "$BACKUP_DIR"/ latest_backups/ user@remote:/backups/dp_shw/

echo "=== [$(date)] Backup завершено успішно ==="
