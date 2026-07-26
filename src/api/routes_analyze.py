import re
from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from src.api.core import templates, limiter, get_workflow_context
from src.ui.i18n.system import t
from src.logger import logger

router = APIRouter()

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_MIME_TYPES = ["text/html", "application/xhtml+xml"]

def is_safe_devpost_url(url: str) -> bool:
    try:
        import ipaddress
        import re
        import socket
        from urllib.parse import urlparse

        if len(url) > 2048:
            return False

        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False

        netloc = parsed.netloc.lower().split(":")[0]
        try:
            ipaddress.ip_address(netloc)
            return False
        except ValueError:
            pass

        if any(ord(c) > 127 for c in netloc):
            return False

        if not (netloc == "devpost.com" or netloc.endswith(".devpost.com")):
            return False

        if ".." in parsed.path or "//" in parsed.path:
            return False

        dangerous_chars = r'[<>"{}|\\^`\x00-\x1F\x7F]'
        if re.search(dangerous_chars, url):
            return False

        if parsed.query and len(parsed.query) > 1024:
            return False

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

@router.get("/analyze", response_class=HTMLResponse)
async def analyze_page(request: Request):
    workflow = get_workflow_context("/analyze")
    return templates.TemplateResponse(request=request, name="analyze.html", context={"workflow": workflow, "t": t})

@router.post("/analyze/url")
@limiter.limit("3/minute")
async def analyze_url(request: Request, url: str = Form(...)):
    if not is_safe_devpost_url(url):
        logger.warning(f"🚨 SSRF Спроба заблокована: невалідний URL {url}")
        from src.ui.errors import UserError, ErrorType
        user_error = UserError(ErrorType.SSRF_BLOCKED, context={"url": url})
        return JSONResponse({"status": "error", "error_type": user_error.type.value, "title": user_error.title, "body": user_error.body, "action": user_error.suggested_action, "technical": f"Invalid URL: {url}"}, status_code=400)

    try:
        from src.analyzer.pipeline import analyze_hackathon
        result = analyze_hackathon(url)
        if "error" in result:
            return JSONResponse({"status": "error", "error": result["error"]}, status_code=400)
        return JSONResponse({"status": "success", "prediction_id": result["prediction_id"]})
    except Exception as e:
        from src.ui.errors import make_error
        user_error = make_error(e, context={"url": url})
        logger.exception(f"Analysis failed: {e}")
        return JSONResponse({"status": "error", "error_type": user_error.type.value, "title": user_error.title, "body": user_error.body, "action": user_error.suggested_action, "technical": user_error.technical_details}, status_code=400)

@router.post("/analyze/html")
@limiter.limit("2/minute")
async def analyze_html(request: Request, file: UploadFile = File(...)):
    try:
        content_type = file.content_type
        if content_type not in ["text/html", "text/plain", "application/octet-stream"]:
            from src.ui.errors import UserError, ErrorType
            user_error = UserError(ErrorType.INVALID_FILE)
            return JSONResponse({"status": "error", "error_type": user_error.type.value, "title": user_error.title, "body": user_error.body, "action": user_error.suggested_action, "technical": f"Invalid content type: {content_type}"}, status_code=415)

        chunks = []
        total_size = 0
        while chunk := await file.read(8192):
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                logger.warning(f"🚨 Занадто великий файл: перевищено {MAX_FILE_SIZE} bytes")
                from src.ui.errors import UserError, ErrorType
                user_error = UserError(ErrorType.FILE_TOO_LARGE)
                return JSONResponse({"status": "error", "error_type": user_error.type.value, "title": user_error.title, "body": user_error.body, "action": user_error.suggested_action, "technical": f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB"}, status_code=413)
            chunks.append(chunk)

        content = b"".join(chunks)
        
        import magic
        mime_type = magic.from_buffer(content, mime=True)
        if mime_type not in ALLOWED_MIME_TYPES:
            logger.warning(f"🚨 Невалідний MIME тип: {mime_type}")
            from src.ui.errors import UserError, ErrorType
            user_error = UserError(ErrorType.INVALID_FILE)
            return JSONResponse({"status": "error", "error_type": user_error.type.value, "title": user_error.title, "body": user_error.body, "action": user_error.suggested_action, "technical": f"Invalid file type. Allowed: {ALLOWED_MIME_TYPES}"}, status_code=415)

        html_str = content.decode("utf-8", errors="ignore")
        import re
        html_str = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", "", html_str, flags=re.IGNORECASE)
        html_str = re.sub(r'\bon\w+\s*=\s*["\'][^"\']*["\']', "", html_str, flags=re.IGNORECASE)

        from src.analyzer.pipeline import analyze_hackathon_offline
        result = analyze_hackathon_offline(html_str)
        if "error" in result:
            return JSONResponse({"status": "error", "error": result["error"]}, status_code=400)
        return JSONResponse({"status": "success", "prediction_id": result["prediction_id"]})
    except Exception as e:
        from src.ui.errors import make_error
        user_error = make_error(e, context={"filename": file.filename})
        logger.exception(f"HTML Analysis failed: {e}")
        return JSONResponse({"status": "error", "error_type": user_error.type.value, "title": user_error.title, "body": user_error.body, "action": user_error.suggested_action, "technical": user_error.technical_details}, status_code=500)
