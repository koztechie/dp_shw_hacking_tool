import contextlib
import ipaddress
import json
import os
import socket
import sys
import threading
import traceback
import uuid
from pathlib import Path
from urllib.parse import urlparse

import duckdb
import pandas as pd
import sentry_sdk
import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Гарантуємо правильні шляхи імпорту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH  # noqa: E402
from src.logger import logger  # noqa: E402
from src.ml.drift_detector import detect_drift  # noqa: E402

TEMPLATES_DIR = PROJECT_ROOT / "src" / "ui" / "templates"
STATIC_DIR = PROJECT_ROOT / "src" / "ui" / "static"

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="DP_SHW_Hacking_Tool")

# АНТИКРИХКІСТЬ: Сувора політика CORS (OWASP), яка не ламає локальні ШІ-фронтенди (Vite/React)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000", "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With"],
    max_age=600,
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """
    АНТИКРИХКІСТЬ: Встановлення HTTP-заголовків безпеки за стандартом OWASP.
    Захист від XSS, Clickjacking та ін'єкцій iframe.
    """
    response = await call_next(request)

    # Суворий CSP: ніяких зовнішніх API-дзвінків з фронтенду
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    return response


limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


# АНТИКРИХКІСТЬ: Глобальний обробник (Information Disclosure Protection)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid.uuid4())[:8]
    logger.error(f"🚨 Unhandled Exception (ID: {error_id}) at {request.url.path}: {exc}")

    # Відправляємо повний трейсбек у Sentry
    sentry_sdk.capture_exception(exc)

    is_dev = os.getenv("ENV", "production") == "development"
    if is_dev:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(exc), "error_id": error_id, "debug": traceback.format_exc()},
        )

    # У продакшені жорстко приховуємо деталі
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": f"Внутрішня помилка сервера. Зверніться до адміністратора. (Код: {error_id})",
        },
    )


# Кастомний обробник лімітів для стандартизації JSON відповідей
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(f"🛡️ Rate limit exceeded for {request.client.host} on {request.url.path}")
    return JSONResponse(
        status_code=429, content={"status": "error", "error": "Занадто багато запитів. Будь ласка, зачекайте."}
    )


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# Потокобезпечний кеш для лічильника
class AppState:
    _lock = threading.Lock()
    _last_count = 0

    @classmethod
    def get_count(cls):
        with cls._lock:
            return cls._last_count

    @classmethod
    def set_count(cls, value):
        with cls._lock:
            cls._last_count = value


@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    """
    АНТИКРИХКІСТЬ: Захист від CSRF-атак на основі перевірки заголовків Origin та Referer (OWASP Standard).
    Запобігає міжсайтовому підробленню запитів без потреби переписувати HTML-шаблони чи JS-скрипти.
    """
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")

        # Дозволені локальні хости та порти розробника
        allowed_hosts = ("127.0.0.1:8000", "localhost:8000", "localhost:5173", "localhost:3000")

        from urllib.parse import urlparse

        if origin:
            parsed = urlparse(origin)
            if parsed.netloc and parsed.netloc not in allowed_hosts:
                logger.critical(f"🚨 CSRF БЛОКОВАНО: Спроба запиту з підозрілого Origin: {origin}")
                return JSONResponse(
                    {"status": "error", "error": "CSRF Protection: Request blocked due to untrusted Origin."},
                    status_code=403,
                )
        elif referer:
            parsed = urlparse(referer)
            if parsed.netloc and parsed.netloc not in allowed_hosts:
                logger.critical(f"🚨 CSRF БЛОКОВАНО: Спроба запиту з підозрілого Referer: {referer}")
                return JSONResponse(
                    {"status": "error", "error": "CSRF Protection: Request blocked due to untrusted Referer."},
                    status_code=403,
                )

    return await call_next(request)


@app.get("/ping")
async def ping():
    return {"status": "ok", "message": "FastAPI is running!"}


# 1. Ендпоінт Дашборду
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    stats = {"hackathons": 0, "projects": 0, "winners": 0, "predictions": 0, "error": None}
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        stats["hackathons"] = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        stats["projects"] = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        stats["winners"] = con.execute("SELECT COUNT(*) FROM projects WHERE is_winner=TRUE").fetchone()[0]

        AppState.set_count(stats["hackathons"])

        with contextlib.suppress(Exception):
            stats["predictions"] = con.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    except Exception as e:
        stats["error"] = str(e)
        stats["hackathons"] = AppState.get_count()
    finally:
        if "con" in locals():
            con.close()
    return templates.TemplateResponse(request=request, name="index.html", context={"stats": stats})


# 2. Ендпоінти Панелі Навчання
@app.get("/training", response_class=HTMLResponse)
async def training_page(request: Request):
    return templates.TemplateResponse(request=request, name="training.html", context={})


def verify_local_access(request: Request):
    """Антикрихкий захист: дозволяємо важкі MLOps операції ТІЛЬКИ з локальної машини (127.0.0.1)."""
    client_ip = request.client.host
    if client_ip not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(f"🚨 Блоковано несанкціонований доступ до MLOps з IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Ця операція вимагає локального доступу (Localhost Only)."
        )


@app.post("/training/start", dependencies=[Depends(verify_local_access)])
@limiter.limit("2/minute")
async def start_training(request: Request, background_tasks: BackgroundTasks, pages: int = Form(1)):
    # Захист від некоректних або від'ємних значень
    if pages < 1:
        return JSONResponse({"status": "error", "error": "Кількість сторінок має бути більше 0"}, status_code=400)
    # Захист RAM комп'ютера AMD A4
    if pages > 10:
        return JSONResponse(
            {"status": "error", "error": "Захист пам'яті: Максимум 10 сторінок для ручного збору."}, status_code=400
        )
    logger.info(f"Отримано запит на збір {pages} сторінок.")
    from src.scraper.orchestrator import run_full_ingestion

    background_tasks.add_task(run_full_ingestion, pages)
    return JSONResponse({"status": "started", "pages": pages})


@app.get("/training/status")
async def training_status():
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("SELECT COUNT(*) FROM hackathons").fetchone()[0]
        AppState.set_count(count)
        con.close()
    except Exception:
        pass
    return JSONResponse({"hackathons_collected": AppState.get_count()})


# 3. Ендпоінти Панелі Аналізу хакаронів
@app.get("/analyze", response_class=HTMLResponse)
async def analyze_page(request: Request):
    return templates.TemplateResponse(request=request, name="analyze.html", context={})


def is_safe_devpost_url(url: str) -> bool:
    """АНТИКРИХКІСТЬ: Захист від SSRF, IP Spoofing, IDN Homograph та DNS Rebinding."""
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False

        netloc = parsed.netloc.lower().split(":")[0]

        # 1. Блокуємо IP-адреси
        try:
            ipaddress.ip_address(netloc)
            return False
        except ValueError:
            pass

        # 2. IDN Homograph check
        if any(ord(c) > 127 for c in netloc):
            return False

        # 3. Жорстка перевірка домену
        if not (netloc == "devpost.com" or netloc.endswith(".devpost.com")):
            return False

        # 4. DNS Resolution check (Antifragile: захищає від DNS rebinding)
        try:
            resolved_ips = socket.getaddrinfo(netloc, None)
            for _family, _, _, _, sockaddr in resolved_ips:
                ip = sockaddr[0]
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
                    logger.warning(f"🚨 SSRF DNS REBINDING BLOCKED: {netloc} resolves to {ip}")
                    return False
        except socket.gaierror:
            return False

        return True
    except Exception:
        return False


@app.post("/analyze/url")
@limiter.limit("5/minute")
async def analyze_url(request: Request, url: str = Form(...)):
    if not is_safe_devpost_url(url):
        logger.warning(f"🚨 SSRF Спроба заблокована: невалідний URL {url}")
        return JSONResponse(
            {"status": "error", "error": "Дозволені лише безпечні посилання на https://*.devpost.com/"}, status_code=400
        )

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
async def analyze_html(file: UploadFile = File(...)):  # noqa: B008
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
        if "con" in locals():
            con.close()

    if not row:
        return HTMLResponse("Передбачення не знайдено (404)", status_code=404)

    def safe_parse(json_str):
        try:
            return json.loads(json_str) if json_str else {}
        except Exception:
            return {}

    hackathon_url = row[0]
    ideas = [safe_parse(row[1]), safe_parse(row[2]), safe_parse(row[3])]
    valid_ideas = [i for i in ideas if i and "title" in i]

    return templates.TemplateResponse(
        request=request,
        name="ideas.html",
        context={"prediction_id": prediction_id, "ideas": valid_ideas, "hackathon_url": hackathon_url},
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
        if "con" in locals():
            con.close()

    hackathon_url = row[0] if row else ""
    techspec = generate_and_save_techspec(prediction_id, idea_index, hackathon_url)

    if "error" in techspec:
        return JSONResponse({"error": techspec["error"]}, status_code=500)
    return JSONResponse(techspec)


@app.get("/techspec/{prediction_id}", response_class=HTMLResponse)
async def techspec_page(request: Request, prediction_id: str):
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute("SELECT techspec, selected_idea FROM predictions WHERE id = ?", [prediction_id]).fetchone()
    except Exception as e:
        logger.error(f"Помилка доступу до БД для сторінки ТЗ: {e}")
        return HTMLResponse(f"Помилка БД: {e}", status_code=500)
    finally:
        if "con" in locals():
            con.close()

    techspec = json.loads(row[0]) if row and row[0] else {}
    selected_idea = row[1] if row else None

    return templates.TemplateResponse(
        request=request, name="techspec.html", context={"techspec": techspec, "selected_idea": selected_idea}
    )


# 6. Ендпоінт Панелі історії передбачень
@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, page: int = 1, limit: int = 50):

    # АНТИКРИХКІСТЬ: Жорстка валідація математичних меж для уникнення DoS через гігантські limit
    page = max(1, min(page, 100))
    limit = max(10, min(limit, 100))
    offset = (page - 1) * limit

    predictions = []
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        # АНТИКРИХКІСТЬ: Параметризований запит захищає від SQL Injection
        df = con.execute(
            """
            SELECT p.id, p.hackathon_url,
                   strftime(p.generated_at, '%Y-%m-%d %H:%M') as gen_date,
                   p.idea_1_title, p.idea_1_score, p.selected_idea, f.won as feedback_won
            FROM predictions p
            LEFT JOIN feedback f ON p.id = f.prediction_id
            ORDER BY p.generated_at DESC
            LIMIT ? OFFSET ?
        """,
            [limit, offset],
        ).fetchdf()

        records = df.to_dict("records")
        for r in records:
            val = r.get("feedback_won")
            if pd.isna(val):
                r["feedback_won"] = None
            else:
                r["feedback_won"] = bool(val)
        predictions = records
    except Exception as e:
        logger.error(f"Помилка завантаження історії: {e}")
    finally:
        # АНТИКРИХКІСТЬ: Гарантоване закриття бази даних
        if "con" in locals():
            con.close()

    return templates.TemplateResponse(
        request=request, name="history.html", context={"predictions": predictions, "page": page, "limit": limit}
    )


# 7. Ендпоінт системи самодіагностики (Health Check)
@app.get("/health")
@limiter.limit("60/minute")
async def health(request: Request):
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
        if "con" in locals():
            con.close()

    model_path = PROJECT_ROOT / "data" / "models" / "best_model.pkl"
    health_status["model_ready"] = model_path.exists()

    if health_status["status"] == "ok" and not health_status["model_ready"]:
        health_status["status"] = "degraded"

    # АНТИКРИХКІСТЬ: Безкоштовний та надшвидкий пінг Xiaomi API без витрати токенів
    health_status["ai_api"] = "degraded"
    try:
        import httpx

        from config.settings import MIMO_API_KEY, MIMO_BASE_URL

        r = httpx.get(f"{MIMO_BASE_URL}/models", headers={"Authorization": f"Bearer {MIMO_API_KEY}"}, timeout=3.0)
        if r.status_code == 200:
            health_status["ai_api"] = "ok"
        else:
            health_status["ai_api"] = f"error_{r.status_code}"
    except Exception:
        health_status["ai_api"] = "unreachable"

    if health_status["ai_api"] != "ok":
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
        if "con" in locals():
            con.close()

    count_file = PROJECT_ROOT / "data" / "models" / "last_train_count.txt"
    last_count = 0
    if count_file.exists():
        with contextlib.suppress(BaseException):
            last_count = int(count_file.read_text(encoding="utf-8").strip())

    # АНТИКРИХКІСТЬ: Перевіряємо дрейф ТІЛЬКИ якщо з моменту останнього тренування з'явилися нові дані
    has_model = (PROJECT_ROOT / "data" / "models" / "best_model.pkl").exists()

    if not has_model:
        suggest_retrain = True
    elif current_count > last_count:
        delta = current_count - last_count
        # Дрейф перевіряємо тільки якщо з'явилися нові нетреновані дані!
        if delta >= 20 or detect_drift():
            suggest_retrain = True

    return JSONResponse(
        {"hackathons": current_count, "last_train_count": last_count, "suggest_retrain": suggest_retrain}
    )


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


@app.post("/ml/retrain", dependencies=[Depends(verify_local_access)])
@limiter.limit("2/minute")
async def retrain_model(request: Request, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_ml_pipeline)
    return JSONResponse({"status": "retraining started"})


@app.get("/ml/evolution")
async def ml_evolution():
    from src.analyzer.evolution_engine import analyze_system_performance

    result = analyze_system_performance()
    return JSONResponse(result)


# --- НОВИЙ ЕНДПОІНТ ФІДБЕКУ (Етап 63) ---
@app.post("/feedback/{prediction_id}", dependencies=[Depends(verify_local_access)])
async def submit_feedback(
    prediction_id: str, background_tasks: BackgroundTasks, won: bool = Form(...), actual_place: int = Form(0)
):
    try:
        con = duckdb.connect(DB_PATH)

        # АНТИКРИХКІСТЬ: Захист від IDOR та отруєння даних (Referential Integrity Check)
        exists = con.execute("SELECT id FROM predictions WHERE id = ?", [prediction_id]).fetchone()
        if not exists:
            logger.warning(f"🚨 IDOR БЛОКОВАНО: Спроба додати фідбек для неіснуючого ID {prediction_id}")
            return JSONResponse({"status": "error", "error": "Prediction not found"}, status_code=404)

        con.execute("INSERT INTO feedback VALUES (?, ?, ?, current_timestamp)", [prediction_id, won, actual_place])
        con.commit()

        from src.analyzer.evolution_engine import trigger_auto_evolution_check

        background_tasks.add_task(trigger_auto_evolution_check)

    except Exception as e:
        logger.error(f"Помилка збереження фідбеку: {e}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
    finally:
        if "con" in locals():
            con.close()

    return JSONResponse({"status": "success"})


# --- ЕНДПОЇНТ ГЕНЕРАЦІЇ АКТИВІВ (Етап 17-18) ---
@app.post("/generate_assets/{prediction_id}")
async def generate_assets(prediction_id: str):
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        row = con.execute("SELECT techspec FROM predictions WHERE id = ?", [prediction_id]).fetchone()
    except Exception as e:
        logger.error(f"Помилка БД при отриманні ТЗ для активів: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if "con" in locals():
            con.close()

    if not row or not row[0]:
        return JSONResponse({"error": "TechSpec not found. Будь ласка, спочатку згенеруйте ТЗ."}, status_code=404)

    try:
        techspec = json.loads(row[0])
        from src.analyzer.assets_generator import generate_project_assets

        assets = generate_project_assets(techspec)
        return JSONResponse(assets)
    except Exception as e:
        logger.error(f"Помилка генерації активів: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


if __name__ == "__main__":
    import os

    import uvicorn

    is_dev = os.getenv("ENV", "production") == "development"
    mode_text = "DEVELOPMENT (з авто-перезавантаженням)" if is_dev else "PRODUCTION (стабільний режим)"
    logger.info(f"Запуск локального сервера FastAPI... [{mode_text}]")
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=is_dev)
