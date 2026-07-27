from fastapi import APIRouter, Request, BackgroundTasks, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from src.api.core import templates, AppState, limiter, verify_local_access
from src.ui.i18n.system import t
from src.logger import logger
from config.settings import DB_PATH

import threading

router = APIRouter()

_ingestion_active = False
_ingestion_lock = threading.Lock()

@router.get("/training", response_class=HTMLResponse)
async def training_page(request: Request):
    try:
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        AppState.set_count(count)
        con.close()
    except Exception:
        count = AppState.get_count()
    return templates.TemplateResponse(request=request, name="training.html", context={"t": t, "hackathons_collected": count})

@router.post("/training/start", dependencies=[Depends(verify_local_access)])
@limiter.limit("2/minute")
async def start_training(request: Request, background_tasks: BackgroundTasks, pages: int = Form(1)):
    global _ingestion_active

    if pages < 1:
        return JSONResponse({"status": "error", "error": "Кількість сторінок має бути більше 0"}, status_code=400)
    if pages > 10:
        return JSONResponse({"status": "error", "error": "Захист пам'яті: Максимум 10 сторінок для ручного збору."}, status_code=400)

    # Перевірка: чи вже запущено ingestion
    with _ingestion_lock:
        if _ingestion_active:
            return JSONResponse(
                {"status": "error", "error": "Збір даних вже запущено. Зачекайте."},
                status_code=409,
            )
        _ingestion_active = True

    # Перевірка RAM перед запуском
    from src.utils.memory_guard import memory_guard
    if not memory_guard.check_memory("Training Ingestion"):
        with _ingestion_lock:
            _ingestion_active = False
        return JSONResponse(
            {"status": "error", "error": "Недостатньо RAM для запуску збору."},
            status_code=503,
        )

    def _guarded_ingestion(pages_count: int):
        global _ingestion_active
        try:
            from src.scraper.orchestrator import run_full_ingestion
            run_full_ingestion(pages_count)
        except MemoryError:
            logger.critical("🚨 OOM під час ingestion! Задачу перервано.")
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
        finally:
            with _ingestion_lock:
                _ingestion_active = False
            import gc
            gc.collect()

    logger.info(f"Отримано запит на збір {pages} сторінок.")
    background_tasks.add_task(_guarded_ingestion, pages)
    return JSONResponse({"status": "started", "pages": pages})

@router.get("/training/status")
async def training_status():
    try:
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        AppState.set_count(count)
        con.close()
    except Exception:
        pass
    return JSONResponse({
        "hackathons_collected": AppState.get_count(),
        "is_running": _ingestion_active
    })
