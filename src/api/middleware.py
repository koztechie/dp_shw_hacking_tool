import os
import base64
from fastapi import Request
from fastapi.responses import JSONResponse
from src.logger import logger
from config.settings import DB_PATH

def setup_middlewares(app):
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
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            try:
                from src.db import get_connection
                con = get_connection(read_only=False)
                con.execute(
                    """
                    INSERT INTO audit_log (user_ip, endpoint, method, status_code, details)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        request.client.host,
                        request.url.path,
                        request.method,
                        response.status_code,
                        f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}",
                    ],
                )
                con.close()  # No-op under the hood
            except Exception as e:
                logger.error(f"Failed to write audit log: {e}")
        return response

    @app.middleware("http")
    async def csrf_protection_middleware(request: Request, call_next):
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            origin = request.headers.get("Origin")
            referer = request.headers.get("Referer")
            csrf_token = request.headers.get("X-CSRF-Token")

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
                expected_token = os.getenv("CSRF_SECRET", "default_csrf_secret_change_me")
                if csrf_token != expected_token:
                    logger.critical("🚨 CSRF БЛОКОВАНО: Невалідний CSRF Token")
                    return JSONResponse({"status": "error", "error": "CSRF Protection: Invalid CSRF Token."}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def api_key_auth_middleware(request: Request, call_next):
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            path = request.url.path
            if path.startswith("/training/") or path.startswith("/ml/") or path.startswith("/feedback/") or path.startswith("/onboarding/") or path.startswith("/history/"):
                return await call_next(request)
            if request.client.host in ("127.0.0.1", "localhost", "::1"):
                return await call_next(request)
            api_key = request.headers.get("X-API-Key")
            expected_key = os.getenv("API_SECRET_KEY")
            if not expected_key:
                logger.warning(f"🚨 Блоковано несанкціонований доступ з IP: {request.client.host}")
                return JSONResponse({"status": "error", "error": "API Key authentication required for remote access."}, status_code=401)
            else:
                if not api_key or api_key != expected_key:
                    logger.warning(f"🚨 Невалідний API Key з IP: {request.client.host}")
                    return JSONResponse({"status": "error", "error": "Invalid API Key."}, status_code=401)
        return await call_next(request)
