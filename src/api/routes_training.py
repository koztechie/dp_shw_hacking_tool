from fastapi import APIRouter, Request, BackgroundTasks, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from src.api.core import templates, AppState, limiter, verify_local_access, get_workflow_context
from src.ui.i18n.system import t
from src.logger import logger
from config.settings import DB_PATH

router = APIRouter()

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
    if pages < 1:
        return JSONResponse({"status": "error", "error": "Кількість сторінок має бути більше 0"}, status_code=400)
    if pages > 10:
        return JSONResponse({"status": "error", "error": "Захист пам'яті: Максимум 10 сторінок для ручного збору."}, status_code=400)
    logger.info(f"Отримано запит на збір {pages} сторінок.")
    from src.scraper.orchestrator import run_full_ingestion
    background_tasks.add_task(run_full_ingestion, pages)
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
    return JSONResponse({"hackathons_collected": AppState.get_count()})
