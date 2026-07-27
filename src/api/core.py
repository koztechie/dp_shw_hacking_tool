from src.db import get_connection
import threading
from pathlib import Path
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import HTTPException, status, Request
import hmac

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "src" / "ui" / "templates"
STATIC_DIR = PROJECT_ROOT / "src" / "ui" / "static"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
limiter = Limiter(key_func=get_remote_address)

class AppState:
    _lock = threading.Lock()
    _last_count = 0

    @classmethod
    def get_count(cls):
        with cls._lock: return cls._last_count

    @classmethod
    def set_count(cls, value):
        with cls._lock: cls._last_count = value

def get_workflow_context(current_path: str, prediction_id: str = None) -> list:
    steps = [
        {"number": 1, "label": "Аналіз", "path": "/analyze", "status": "pending"},
        {"number": 2, "label": "Ідеї", "path": "/ideas", "status": "pending"},
        {"number": 3, "label": "TechSpec", "path": "/techspec", "status": "pending"},
    ]
    workflow_paths = ["/analyze", "/ideas", "/techspec"]
    base_path = current_path.split("/")[1] if current_path.startswith("/") else ""
    base_path = f"/{base_path}"
    if base_path not in workflow_paths:
        return None
    current_idx = workflow_paths.index(base_path)
    for i, step in enumerate(steps):
        if i < current_idx: step["status"] = "completed"
        elif i == current_idx: step["status"] = "active"
        if prediction_id and step["path"] != "/analyze":
            step["path"] = f"{step['path']}/{prediction_id}"
    return steps

def verify_local_access(request: Request):
    from src.logger import logger
    client_ip = request.client.host
    allowed_ips = ["127.0.0.1", "localhost", "::1"]
    is_allowed = any(hmac.compare_digest(client_ip.encode(), ip.encode()) for ip in allowed_ips)
    if not is_allowed:
        logger.warning(f"🚨 Блоковано несанкціонований доступ до MLOps з IP: {client_ip}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ця операція вимагає локального доступу (Localhost Only).")
