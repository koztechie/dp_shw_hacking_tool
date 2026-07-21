import asyncio
import contextlib
import os
import signal
import uuid
import traceback
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.core import PROJECT_ROOT, STATIC_DIR, templates, limiter, AppState, t
from src.api.middleware import setup_middlewares
from src.api.routes_training import router as training_router
from src.api.routes_analyze import router as analyze_router
from src.api.routes_ml import router as ml_router
from config.settings import DB_PATH
from src.logger import logger

shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    logger.info(f"🛑 Отримано сигнал {sig}. Ініціюю graceful shutdown...")
    shutdown_event.set()

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 FastAPI запускається...")
    try:
        from src.db import init_db
        init_db()
        logger.info("✅ База даних ініціалізована")
    except Exception as e:
        logger.error(f"❌ Помилка ініціалізації БД: {e}")
    yield
    logger.info("🛑 Отримано сигнал завершення. Чекаємо на фонові задачі...")
    shutdown_event.set()
    await asyncio.sleep(2)
    logger.info("✅ Завершення роботи.")

app = FastAPI(title="DP_SHW_Hacking_Tool", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000", "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With"],
    max_age=600,
)

setup_middlewares(app)
app.state.limiter = limiter

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid.uuid4())[:8]
    logger.error(f"🚨 Unhandled Exception (ID: {error_id}) at {request.url.path}: {exc}")
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except ImportError:
        pass

    is_dev = os.getenv("ENV", "production") == "development"
    if is_dev:
        return JSONResponse(status_code=500, content={"status": "error", "error": str(exc), "error_id": error_id, "debug": traceback.format_exc()})
    return JSONResponse(status_code=500, content={"status": "error", "error": f"Внутрішня помилка сервера. Зверніться до адміністратора. (Код: {error_id})"})

from slowapi.errors import RateLimitExceeded
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(f"🛡️ Rate limit exceeded for {request.client.host} on {request.url.path}")
    return JSONResponse(status_code=429, content={"status": "error", "error": "Занадто багато запитів. Будь ласка, зачекайте."})

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Register Blueprints / Routers
app.include_router(training_router)
app.include_router(analyze_router)
app.include_router(ml_router)

@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "FastAPI is running!"}

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    onboarding_flag = PROJECT_ROOT / "data" / ".onboarding_completed"
    if not onboarding_flag.exists():
        return templates.TemplateResponse(request=request, name="onboarding.html", context={"t": t})

    stats = {
        "hackathons": 0, "projects": 0, "winners": 0, "predictions": 0,
        "error": None, "win_rate": 24, "freshness": "fresh",
        "last_updated": datetime.now().strftime("%H:%M:%S"),
        "hackathons_trend": [10, 25, 20, 40, 55, 50, 75],
        "projects_trend": [5, 12, 10, 22, 35, 30, 45],
        "ml_metrics": {"pr_auc": "0.92", "f1": "0.88", "drift": "1.2%", "version": "1.4.2"}
    }
    try:
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        stats["hackathons"] = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        stats["projects"] = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        stats["winners"] = con.execute("SELECT COUNT(*) FROM projects WHERE is_winner=TRUE").fetchone()[0]
        if stats["projects"] > 0: stats["win_rate"] = int((stats["winners"] / stats["projects"]) * 100)
        AppState.set_count(stats["hackathons"])
        with contextlib.suppress(Exception): stats["predictions"] = con.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    except Exception as e:
        stats["error"] = str(e)
        stats["hackathons"] = AppState.get_count()
    finally:
        if "con" in locals(): con.close()
    return templates.TemplateResponse(request=request, name="index.html", context={"stats": stats, "t": t})

@app.post("/onboarding/complete")
@limiter.limit("10/minute")
async def complete_onboarding(request: Request):
    flag = PROJECT_ROOT / "data" / ".onboarding_completed"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.touch()
    return JSONResponse({"status": "success"})

@app.post("/cache/clear")
async def clear_cache():
    try:
        from src.analyzer.cache import CACHE_DIR
        import shutil
        if CACHE_DIR.exists():
            for filename in os.listdir(CACHE_DIR):
                file_path = os.path.join(CACHE_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path): os.unlink(file_path)
                    elif os.path.isdir(file_path): shutil.rmtree(file_path)
                except Exception: pass
        return JSONResponse({"status": "success", "message": "Кеш успішно очищено!"})
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

@app.get("/health")
@limiter.limit("60/minute")
async def health(request: Request):
    health_status = {"status": "ok", "timestamp": datetime.now().isoformat(), "components": {"database": {"status": "unknown"}, "ml_model": {"status": "unknown"}, "ai_api": {"status": "unknown"}, "disk_space": {"status": "unknown"}, "memory": {"status": "unknown"}, "cpu": {"status": "unknown"}}, "metrics": {"hackathons": 0, "projects": 0, "predictions": 0}}
    critical_failures = []

    try:
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        health_status["metrics"]["hackathons"] = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        health_status["metrics"]["projects"] = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        health_status["metrics"]["predictions"] = con.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        con.execute("SELECT 1")
        health_status["components"]["database"] = {"status": "ok", "details": health_status["metrics"]}
        con.close()
    except Exception as e:
        health_status["components"]["database"] = {"status": "error", "details": {"error": str(e)}}
        critical_failures.append("database")

    model_path = PROJECT_ROOT / "data" / "models" / "best_model.pkl"
    if model_path.exists():
        try:
            import joblib
            model = joblib.load(model_path)
            health_status["components"]["ml_model"] = {"status": "ok", "details": {"model_type": "SoftVotingEnsemble" if isinstance(model, dict) else type(model).__name__, "size_mb": round(model_path.stat().st_size / (1024 * 1024), 2)}}
        except Exception as e:
            health_status["components"]["ml_model"] = {"status": "error", "details": {"error": str(e)}}
            critical_failures.append("ml_model")
    else:
        health_status["components"]["ml_model"] = {"status": "missing", "details": {"error": "Model file not found"}}
        critical_failures.append("ml_model")

    try:
        import httpx
        from config.settings import MIMO_API_KEY, MIMO_BASE_URL
        start_time = datetime.now()
        r = httpx.get(f"{MIMO_BASE_URL}/models", headers={"Authorization": f"Bearer {MIMO_API_KEY}"}, timeout=5.0)
        response_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        health_status["components"]["ai_api"] = {"status": "ok" if r.status_code == 200 else "degraded", "details": {"response_time_ms": response_time_ms, "status_code": r.status_code}}
    except Exception as e:
        health_status["components"]["ai_api"] = {"status": "unreachable", "details": {"error": str(e)}}

    try:
        import psutil
        disk_usage = psutil.disk_usage(str(PROJECT_ROOT))
        health_status["components"]["disk_space"] = {"status": "ok" if disk_usage.percent < 80 else ("warning" if disk_usage.percent < 90 else "critical"), "details": {"used_percent": round(disk_usage.percent, 1), "free_gb": round(disk_usage.free / (1024**3), 2)}}
        if disk_usage.percent >= 90: critical_failures.append("disk_space")

        mem_usage = psutil.virtual_memory()
        health_status["components"]["memory"] = {"status": "ok" if mem_usage.percent < 80 else ("warning" if mem_usage.percent < 90 else "critical"), "details": {"used_percent": round(mem_usage.percent, 1), "available_mb": round(mem_usage.available / (1024**2), 2)}}
        if mem_usage.percent >= 90: critical_failures.append("memory")

        cpu_percent = psutil.cpu_percent(interval=0.1)
        health_status["components"]["cpu"] = {"status": "ok" if cpu_percent < 85 else ("warning" if cpu_percent <= 95 else "degraded"), "details": {"used_percent": cpu_percent}}
    except Exception as e:
        logger.error(f"Health stats error: {e}")

    if critical_failures:
        health_status["status"] = "critical" if any(f in critical_failures for f in ["database", "ml_model", "memory"]) else "degraded"
        health_status["critical_failures"] = critical_failures

    return JSONResponse(health_status, status_code=503 if health_status["status"] == "critical" else 200)

@app.get("/metrics")
async def metrics():
    from src.utils.metrics import CONTENT_TYPE_LATEST, MEMORY_USAGE, generate_latest
    import psutil
    with contextlib.suppress(Exception): MEMORY_USAGE.set(psutil.virtual_memory().percent)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    is_dev = os.getenv("DP_SHW_ENV", "production").lower() == "development"
    logger.info(f"Запуск FastAPI (env={'dev' if is_dev else 'production'})...")
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=int(os.getenv("PORT", 8000)), reload=is_dev, workers=1 if not is_dev else None)
