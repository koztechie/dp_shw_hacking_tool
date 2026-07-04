import sys
from pathlib import Path
import duckdb
import numpy as np
from fastapi import FastAPI, Request, Form, BackgroundTasks, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

# Гарантуємо абсолютні шляхи
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.logger import logger
from config.settings import DB_PATH
from src.ml.drift_detector import detect_drift

TEMPLATES_DIR = PROJECT_ROOT / "src" / "ui" / "templates"
STATIC_DIR = PROJECT_ROOT / "src" / "ui" / "static"

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="DP_SHW_Hacking_Tool")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Глобальний кеш для лічильника
LAST_COLLECTED_COUNT = 0

@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "FastAPI is running!"}

# 1. Ендпоінт Дашборду
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    global LAST_COLLECTED_COUNT
    stats = {"hackathons": 0, "projects": 0, "winners": 0, "predictions": 0, "error": None}
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        stats["hackathons"] = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        stats["projects"] = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        stats["winners"] = con.execute("SELECT COUNT(*) FROM projects WHERE is_winner=TRUE").fetchone()[0]
        
        LAST_COLLECTED_COUNT = stats["hackathons"]
        
        try:
            stats["predictions"] = con.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        except Exception:
            pass
    except Exception as e:
        stats["error"] = str(e)
        stats["hackathons"] = LAST_COLLECTED_COUNT
    finally:
        if 'con' in locals(): con.close()
    return templates.TemplateResponse(request=request, name="index.html", context={"stats": stats})

# 2. Ендпоінти Панелі Навчання
@app.get("/training", response_class=HTMLResponse)
async def training_page(request: Request):
    return templates.TemplateResponse(request=request, name="training.html", context={})

@app.post("/training/start")
async def start_training(background_tasks: BackgroundTasks, pages: int = Form(1)):
    logger.info(f"Отримано запит на збір {pages} сторінок.")
    from src.scraper.orchestrator import run_full_ingestion
    background_tasks.add_task(run_full_ingestion, pages)
    return JSONResponse({"status": "started", "pages": pages})

@app.get("/training/status")
async def training_status():
    global LAST_COLLECTED_COUNT
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        LAST_COLLECTED_COUNT = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        con.close()
    except Exception:
        pass
    return JSONResponse({"hackathons_collected": LAST_COLLECTED_COUNT})

# 3. Ендпоінти Панелі Аналізу хакаронів
@app.get("/analyze", response_class=HTMLResponse)
async def analyze_page(request: Request):
    return templates.TemplateResponse(request=request, name="analyze.html", context={})

@app.post("/analyze/url")
async def analyze_url(url: str = Form(...)):
    try:
        from src.analyzer.pipeline import analyze_hackathon
        result = analyze_hackathon(url)
        if "error" in result:
            return JSONResponse({"status": "error", "error": result["error"]}, status_code=400)
        return JSONResponse({"status": "success", "prediction_id": result["prediction_id"]})
    except Exception as e:
        logger.exception(f"Помилка в ендпоінті /analyze/url: {e}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

@app.post("/analyze/html")
async def analyze_html(file: UploadFile = File(...)):
    try:
        content = await file.read()
        html_str = content.decode("utf-8", errors="ignore")
        
        from src.analyzer.pipeline import analyze_hackathon_offline
        result = analyze_hackathon_offline(html_str)
        
        if "error" in result:
            return JSONResponse({"status": "error", "error": result["error"]}, status_code=400)
            
        return JSONResponse({"status": "success", "prediction_id": result["prediction_id"]})
    except Exception as e:
        logger.exception(f"Помилка в ендпоінті /analyze/html: {e}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

# 4. Ендпоінти Панелі відображення ідей
@app.get("/ideas/{prediction_id}", response_class=HTMLResponse)
async def ideas_page(request: Request, prediction_id: str):
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        query = """
            SELECT hackathon_url, idea_1_description, idea_2_description, idea_3_description 
            FROM predictions 
            WHERE id = ?
        """
        row = con.execute(query, [prediction_id]).fetchone()
    except Exception as e:
        logger.error(f"Помилка зчитування передбачень: {e}")
        return HTMLResponse(f"Помилка бази даних: {e}", status_code=500)
    finally:
        if 'con' in locals(): con.close()

    if not row:
        return HTMLResponse("Передбачення не знайдено (404)", status_code=404)

    import json
    def safe_parse(json_str):
        try: return json.loads(json_str) if json_str else {}
        except Exception: return {}

    hackathon_url = row[0]
    ideas = [safe_parse(row[1]), safe_parse(row[2]), safe_parse(row[3])]
    valid_ideas = [i for i in ideas if i and "title" in i]

    return templates.TemplateResponse(
        request=request, 
        name="ideas.html", 
        context={"prediction_id": prediction_id, "ideas": valid_ideas, "hackathon_url": hackathon_url}
    )

# 5. Ендпоінти Панелі генерації та відображення ТЗ
@app.post("/techspec/{prediction_id}/{idea_index}")
async def get_techspec(prediction_id: str, idea_index: int):
    from src.analyzer.techspec_pipeline import generate_and_save_techspec
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute("SELECT hackathon_url FROM predictions WHERE id = ?", [prediction_id]).fetchone()
    except Exception as e:
        logger.error(f"Помилка доступу до БД при генерації ТЗ: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if 'con' in locals(): con.close()

    hackathon_url = row[0] if row else ""
    techspec = generate_and_save_techspec(prediction_id, idea_index, hackathon_url)
    
    if "error" in techspec:
        return JSONResponse({"error": techspec["error"]}, status_code=500)
    return JSONResponse(techspec)

@app.get("/techspec/{prediction_id}", response_class=HTMLResponse)
async def techspec_page(request: Request, prediction_id: str):
    import json
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute("SELECT techspec, selected_idea FROM predictions WHERE id = ?", [prediction_id]).fetchone()
    except Exception as e:
        logger.error(f"Помилка доступу до БД для сторінки ТЗ: {e}")
        return HTMLResponse(f"Помилка БД: {e}", status_code=500)
    finally:
        if 'con' in locals(): con.close()

    techspec = json.loads(row[0]) if row and row[0] else {}
    selected_idea = row[1] if row else None

    return templates.TemplateResponse(
        request=request, 
        name="techspec.html", 
        context={"techspec": techspec, "selected_idea": selected_idea}
    )

# 6. Ендпоінт Панелі історії передбачень з підтримкою Feedback_Won
@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    predictions = []
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        # Антикрихкість: Витягуємо feedback_won через LEFT JOIN
        df = con.execute("""
            SELECT p.id, p.hackathon_url, strftime(p.generated_at, '%Y-%m-%d %H:%M') as gen_date, p.idea_1_title, p.idea_1_score, p.selected_idea, f.won as feedback_won
            FROM predictions p
            LEFT JOIN feedback f ON p.id = f.prediction_id
            ORDER BY p.generated_at DESC LIMIT 50
        """).fetchdf()
        df = df.replace({np.nan: None})
        predictions = df.to_dict("records")
    except Exception as e:
        logger.error(f"Помилка завантаження історії: {e}")
    finally:
        if 'con' in locals(): con.close()
    return templates.TemplateResponse(request=request, name="history.html", context={"predictions": predictions})

# 7. Ендпоінт системи самодіагностики (Health Check)
@app.get("/health")
async def health():
    health_status = {"status": "ok", "hackathons": 0, "projects": 0, "model_ready": False, "error": None}
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        health_status["hackathons"] = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        health_status["projects"] = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    except Exception as e:
        health_status["status"] = "error"
        health_status["error"] = f"Database Error: {str(e)}"
        logger.error(f"Health check failed (DB): {e}")
    finally:
        if 'con' in locals(): con.close()
        
    model_path = PROJECT_ROOT / "data" / "models" / "best_model.pkl"
    health_status["model_ready"] = model_path.exists()
    
    if health_status["status"] == "ok" and not health_status["model_ready"]:
        health_status["status"] = "degraded"
        
    return JSONResponse(health_status)

# 8. Ендпоінти для перенавчання ML-моделі (MLOps)
@app.get("/ml/retrain-check")
async def retrain_check():
    suggest_retrain = False
    current_count = 0
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        current_count = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
    except Exception:
        pass
    finally:
        if 'con' in locals(): con.close()

    count_file = PROJECT_ROOT / "data" / "models" / "last_train_count.txt"
    last_count = 0
    if count_file.exists():
        try:
            last_count = int(count_file.read_text(encoding="utf-8").strip())
        except:
            pass

    # Якщо різниця більше 20 - пропонуємо перенавчання або виявлено дрейф даних
    if (current_count - last_count) >= 20 or detect_drift():
        suggest_retrain = True

    # Якщо моделі взагалі ще немає
    if not (PROJECT_ROOT / "data" / "models" / "best_model.pkl").exists():
        suggest_retrain = True

    return JSONResponse({
        "hackathons": current_count,
        "last_train_count": last_count,
        "suggest_retrain": suggest_retrain
    })

def run_ml_pipeline():
    try:
        from src.analyzer.batch_features import run_batch_feature_extraction
        from src.ml.train_ensemble import train_ensemble
        
        logger.info("🧠 Запуск фонового MLOps пайплайну...")
        run_batch_feature_extraction()
        train_ensemble()
        
        con = duckdb.connect(DB_PATH, read_only=True)
        current_count = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        con.close()
        
        count_file = PROJECT_ROOT / "data" / "models" / "last_train_count.txt"
        count_file.parent.mkdir(parents=True, exist_ok=True)
        count_file.write_text(str(current_count), encoding="utf-8")
        
        logger.info("🧠 Пайплайн перенавчання успішно завершено.")
    except Exception as e:
        logger.error(f"Помилка MLOps пайплайну: {e}")

@app.post("/ml/retrain")
async def retrain_model(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_ml_pipeline)
    return JSONResponse({"status": "retraining started"})

@app.get("/ml/evolution")
async def ml_evolution():
    from src.analyzer.evolution_engine import analyze_system_performance
    result = analyze_system_performance()
    return JSONResponse(result)

# --- НОВИЙ ЕНДПОІНТ ФІДБЕКУ (Етап 63) ---
@app.post("/feedback/{prediction_id}")
async def submit_feedback(prediction_id: str, background_tasks: BackgroundTasks, won: bool = Form(...), actual_place: int = Form(0)):
    """Фіксуємо реальний результат та запускаємо перевірку еволюції моделі."""
    try:
        con = duckdb.connect(DB_PATH)
        con.execute("INSERT INTO feedback VALUES (?, ?, ?, current_timestamp)", [prediction_id, won, actual_place])
        con.commit()
        
        # АНТИКРИХКІСТЬ: Запускаємо Self-Evolution Engine у фоні!
        from src.analyzer.evolution_engine import trigger_auto_evolution_check
        background_tasks.add_task(trigger_auto_evolution_check)
        
    except Exception as e:
        logger.error(f"Помилка збереження фідбеку: {e}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
    finally:
        if "con" in locals(): con.close()
        
    return JSONResponse({"status": "success"})

if __name__ == "__main__":
    logger.info("Запуск локального сервера FastAPI...")
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=True)
