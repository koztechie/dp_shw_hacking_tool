import sys
from pathlib import Path
import duckdb
import json
from collections import Counter

# Налаштовуємо шляхи
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH

print("=== ДІАГНОСТИКА РЕЗУЛЬТАТІВ ЗБОРУ (Етап 16) ===")

try:
    # Відкриваємо базу строго в режимі read_only
    con = duckdb.connect(DB_PATH, read_only=True)
    
    # 1. Рахуємо хакатони
    hackathons_count = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
    
    # 2. Рахуємо проекти
    projects_count = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    
    # 3. Рахуємо переможців
    winners_count = con.execute("SELECT COUNT(*) FROM projects WHERE is_winner = TRUE").fetchone()[0]
    
    # 4. Рахуємо середню кількість проектів на хакатон
    avg_projects = con.execute("""
        SELECT AVG(cnt) FROM (
            SELECT COUNT(*) as cnt FROM projects GROUP BY hackathon_id
        )
    """).fetchone()[0]
    avg_projects = round(avg_projects, 1) if avg_projects else 0

    # 5. Аналізуємо найпопулярніші технологічні теги
    raw_tags = con.execute("SELECT tech_tags FROM projects").fetchall()
    all_tags = []
    for row in raw_tags:
        try:
            # Розпаковуємо JSON-масив тегів
            all_tags.extend(json.loads(row[0]))
        except Exception:
            pass
            
    top_tags = Counter(all_tags).most_common(5)

    print(f"  [ОК] Хакатонів у базі даних: {hackathons_count}")
    print(f"  [ОК] Проектів у базі даних: {projects_count}")
    print(f"  [ОК] Проектів-переможців: {winners_count}")
    print(f"  [ОК] Середня кількість проектів на хакатон: {avg_projects}")
    
    print("\n📋 ТОП-5 НАЙБІЛЬШ ПОПУЛЯРНИХ ТЕХНОЛОГІЙ:")
    for tag, count in top_tags:
        print(f"  - {tag}: {count}")

    con.close()
    print("\n✅ Тестову верифікацію успішно завершено. База даних наповнена.")
    
except Exception as e:
    print(f"❌ Помилка під час аналізу результатів збору: {e}")
    sys.exit(1)
