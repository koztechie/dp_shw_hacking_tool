import sys
from pathlib import Path
import duckdb

# Гарантуємо правильні шляхи імпорту

from config.settings import DB_PATH

def validate():
    db_file = Path(DB_PATH)
    if not db_file.exists():
        print(f"❌ База даних не знайдена: {DB_PATH}")
        print("Будь ласка, зачекайте на створення бази оркестратором.")
        return

    print("=== АНАЛІТИКА БАЗИ ДАНИХ (DuckDB) ===")
    
    try:
        # read_only=True дозволяє читати БД навіть якщо оркестратор у цей час записує дані
        con = duckdb.connect(DB_PATH, read_only=True)
        
        # Базова статистика
        h_count = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        p_count = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        w_count = con.execute("SELECT COUNT(*) FROM projects WHERE is_winner = TRUE").fetchone()[0]
        
        # Обчислення відсотка переможців (Win Rate)
        win_rate_val = con.execute("SELECT AVG(CAST(is_winner AS INT)) FROM projects").fetchone()[0]
        win_rate = f"{win_rate_val * 100:.2f}%" if win_rate_val is not None else "0.00%"
        
        print(f"🏆 Хакатонів у базі: {h_count}")
        print(f"🚀 Проектів зібрано: {p_count}")
        print(f"🏅 З них переможців: {w_count}")
        print(f"📊 Загальний Win rate: {win_rate}")
        
        # Аналіз найпопулярніших технологій серед ПЕРЕМОЖЦІВ
        print("\n=== ТОП-20 ТЕХНОЛОГІЙ ПЕРЕМОЖЦІВ ===")
        
        query = """
            SELECT tag, COUNT(*) as cnt
            FROM (
                SELECT unnest(from_json(tech_tags, '["VARCHAR"]')) as tag
                FROM projects 
                WHERE is_winner = TRUE 
                  AND tech_tags IS NOT NULL 
                  AND tech_tags != '[]'
            )
            GROUP BY tag 
            ORDER BY cnt DESC 
            LIMIT 20
        """
        
        result = con.execute(query).fetchall()
        
        if not result:
            print("  [Інформація] Теги переможців поки відсутні (або база збирається).")
        else:
            for i, row in enumerate(result, 1):
                print(f"  {i:>2}. {row[0]:<25} ({row[1]} перемог)")
                
    except Exception as e:
        print(f"❌ Помилка під час зчитування даних: {e}")
    finally:
        if 'con' in locals():
            con.close()

if __name__ == "__main__":
    validate()
