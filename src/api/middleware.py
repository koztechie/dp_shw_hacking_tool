import os
import base64
from fastapi import Request
from fastapi.responses import JSONResponse
from src.logger import logger
from config.settings import DB_PATH
import threading
from collections import deque
import duckdb

# In-memory черга для audit log (макс 1000 записів)
_audit_queue: deque = deque(maxlen=1000)
_audit_flush_event = threading.Event()

def _audit_flush_worker():
    """Фоновий потік: записує audit log batch-ами раз на 5 секунд."""
    while True:
        _audit_flush_event.wait(timeout=5.0)
        _audit_flush_event.clear()

        batch = []
        while _audit_queue:
            try:
                batch.append(_audit_queue.popleft())
            except IndexError:
                break

        if not batch:
            continue

        try:
            con = duckdb.connect(str(DB_PATH))
            con.execute("BEGIN")
            for entry in batch:
                con.execute(
                    "INSERT INTO audit_log (user_ip, endpoint, method, status_code, details) "
                    "VALUES (?, ?, ?, ?, ?)",
                    entry,
                )
            con.commit()
            con.close()
        except Exception as e:
            logger.error(f"Audit flush failed: {e}")

# Запускаємо worker при старті
_audit_thread = threading.Thread(target=_audit_flush_worker, daemon=True)
_audit_thread.start()

def setup_middlewares(app):
    MAX_BODY_SIZE = 1 * 1024 * 1024  # 1 MB для Form data (крім file upload)

    @app.middleware("http")
    async def body_size_limit_middleware(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            # Дозволяємо більший розмір лише для file upload
            if "/analyze/html" not in request.url.path:
                return JSONResponse(
                    {"status": "error", "error": "Request body too large."},
                    status_code=413,
                )
        return await call_next(request)

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        nonce = base64.b64encode(os.urandom(16)).decode("utf-8")
        request.state.csp_nonce = nonce
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            f"font-src 'self' data: https://fonts.gstatic.com; "
            f"img-src 'self' data: https:; "
            f"connect-src 'self'; "
            f"frame-ancestors 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self';"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.middleware("http")
    async def audit_log_middleware(request: Request, call_next):
        response = await call_next(request)
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            _audit_queue.append((
                request.client.host if request.client else "unknown",
                request.url.path,
                request.method,
                response.status_code,
                f"User-Agent: {request.headers.get('User-Agent', 'Unknown')[:200]}"
            ))
            _audit_flush_event.set()
        return response

    @app.middleware("http")
    async def csrf_protection_middleware(request: Request, call_next):
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            env = os.getenv("ENV", "production").lower()
            is_testing = env in ("testing", "test", "ci")

            csrf_secret = os.getenv("CSRF_SECRET")
            if not csrf_secret or csrf_secret == "your_random_secret_min_32_chars":
                if is_testing:
                    csrf_secret = "ci-test-csrf-secret-not-for-prod-use"
                else:
                    logger.critical("🚨 CSRF_SECRET не налаштований! POST-запити заблоковані.")
                    return JSONResponse(
                        {"status": "error", "error": "Server misconfiguration: CSRF_SECRET not set."},
                        status_code=503,
                    )

            origin = request.headers.get("Origin") or request.headers.get("origin")
            referer = request.headers.get("Referer") or request.headers.get("referer")
            csrf_token = request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token")

            # Testing: TestClient не надсилає Origin -> пропускаємо.
            # Явний Origin (security-тести, напр. evil.com) -> валідуємо нижче.
            if is_testing and not origin and not referer:
                return await call_next(request)

            allowed_hosts = ["127.0.0.1:8000", "localhost:8000", "localhost:5173", "localhost:3000"]
            host = request.headers.get("Host")
            if host and host not in allowed_hosts:
                allowed_hosts.append(host)

            from urllib.parse import urlparse
            if origin or referer:
                if origin:
                    parsed = urlparse(origin)
                    if parsed.netloc and parsed.netloc not in allowed_hosts:
                        logger.critical(f"🚨 CSRF БЛОКОВАНО: Спроба запиту з підозрілого Origin: {origin}")
                        return JSONResponse({"status": "error", "error": "CSRF Protection: Request blocked due to untrusted Origin."}, status_code=403)
                elif referer:
                    parsed = urlparse(referer)
                    if parsed.netloc and parsed.netloc not in allowed_hosts:
                        logger.critical(f"🚨 CSRF БЛОКОВАНО: Спроба запиту з підозрілого Referer: {referer}")
                        return JSONResponse({"status": "error", "error": "CSRF Protection: Request blocked due to untrusted Referer."}, status_code=403)
            else:
                if not csrf_token:
                    logger.critical("🚨 CSRF БЛОКОВАНО: Відсутні Origin/Referer та CSRF Token")
                    return JSONResponse({"status": "error", "error": "CSRF Protection: Missing Origin/Referer and CSRF Token."}, status_code=403)
                expected_token = csrf_secret
                if csrf_token != expected_token:
                    logger.critical("🚨 CSRF БЛОКОВАНО: Невалідний CSRF Token")
                    return JSONResponse({"status": "error", "error": "CSRF Protection: Invalid CSRF Token."}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def api_key_auth_middleware(request: Request, call_next):
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            # ── ENV-AWARE BYPASS: у тестах автентифікація не потрібна ──
            env = os.getenv("ENV", "production").lower()
            if env in ("testing", "test", "ci"):
                return await call_next(request)

            path = request.url.path
            if path.startswith("/training/") or path.startswith("/ml/") or path.startswith("/feedback/") or path.startswith("/onboarding/") or path.startswith("/history/"):
                return await call_next(request)
            if request.client.host in ("127.0.0.1", "localhost", "::1"):
                return await call_next(request)
            api_key = request.headers.get("X-API-Key")
            expected_key = os.getenv("API_SECRET_KEY")
            
            # FAIL-CLOSED if API key is not set or uses the .env.example default
            if not expected_key or expected_key == "your_random_api_key_min_32_chars":
                logger.critical("🚨 API_SECRET_KEY не налаштований або використовує дефолтне значення! Віддалений доступ заблоковано.")
                return JSONResponse(
                    {"status": "error", "error": "Server misconfiguration: API_SECRET_KEY not securely configured."},
                    status_code=503
                )
            else:
                if not api_key or api_key != expected_key:
                    logger.warning(f"🚨 Невалідний API Key з IP: {request.client.host}")
                    return JSONResponse({"status": "error", "error": "Invalid API Key."}, status_code=401)
        return await call_next(request)
