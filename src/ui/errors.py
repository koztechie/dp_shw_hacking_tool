"""
DP_SHW Error Taxonomy — Кожна помилка має тип, текст і наступну дію
"""
from enum import Enum
from dataclasses import dataclass
from src.ui.i18n.system import t

class ErrorType(Enum):
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    API_DOWN = "api_down"
    CIRCUIT_OPEN = "circuit_open"
    DB_LOCKED = "db_locked"
    FILE_TOO_LARGE = "file_too_large"
    INVALID_FILE = "invalid_file"
    SSRF_BLOCKED = "ssrf_blocked"
    CSRF_FAILED = "csrf_failed"
    VALIDATION = "validation"
    GENERIC = "generic"

@dataclass
class UserError:
    type: ErrorType
    technical_details: str = ""
    context: dict = None
    
    def __post_init__(self):
        self.context = self.context or {}
    
    @property
    def title(self) -> str:
        return t(f"error.{self.type.value}.title")
    
    @property
    def body(self) -> str:
        return t(f"error.{self.type.value}.body", **self.context)
    
    @property
    def suggested_action(self) -> str:
        """Що робити далі — залежить від типу помилки"""
        actions = {
            ErrorType.NETWORK: "check_connection",
            ErrorType.RATE_LIMIT: "wait",
            ErrorType.API_DOWN: "use_fallback",
            ErrorType.CIRCUIT_OPEN: "wait_or_offline",
            ErrorType.DB_LOCKED: "wait_or_stop_other",
            ErrorType.FILE_TOO_LARGE: "try_url_instead",
            ErrorType.INVALID_FILE: "check_format",
            ErrorType.SSRF_BLOCKED: "use_valid_url",
            ErrorType.CSRF_FAILED: "refresh_page",
            ErrorType.VALIDATION: "fix_input",
            ErrorType.GENERIC: "retry_or_home",
        }
        return actions.get(self.type, "retry")

# Фабрика помилок — єдина точка створення
def make_error(exception: Exception, context: dict = None) -> UserError:
    """Перетворює технічний exception на зрозумілу UserError"""
    context = context or {}
    
    try:
        import httpx
        has_httpx = True
    except ImportError:
        has_httpx = False
        
    try:
        from duckdb import IOException
        has_duckdb = True
    except ImportError:
        has_duckdb = False
    
    if has_httpx and isinstance(exception, (httpx.ConnectError, httpx.NetworkError)):
        return UserError(ErrorType.NETWORK, str(exception), context)
    if has_httpx and isinstance(exception, httpx.TimeoutException):
        return UserError(ErrorType.API_DOWN, str(exception), context)
    
    if has_duckdb and isinstance(exception, IOException):
        return UserError(ErrorType.DB_LOCKED, str(exception), context)
        
    exc_str = str(exception).lower()
    
    if "rate limit" in exc_str:
        wait = context.get("retry_after", 60)
        return UserError(ErrorType.RATE_LIMIT, str(exception), {"seconds": wait})
    if "circuit breaker" in exc_str:
        return UserError(ErrorType.CIRCUIT_OPEN, str(exception), {"minutes": 5})
    if "database is locked" in exc_str:
        return UserError(ErrorType.DB_LOCKED, str(exception), context)
    if "too large" in exc_str:
        return UserError(ErrorType.FILE_TOO_LARGE, str(exception), context)
    if "mime" in exc_str:
        return UserError(ErrorType.INVALID_FILE, str(exception), context)
        
    return UserError(ErrorType.GENERIC, str(exception), context)
