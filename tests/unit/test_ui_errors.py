import pytest
import httpx
from src.ui.errors import UserError, ErrorType, make_error

def test_make_error_network():
    err = make_error(httpx.ConnectError("Connection refused"))
    assert err.type == ErrorType.NETWORK

def test_make_error_timeout():
    err = make_error(httpx.TimeoutException("Timeout"))
    assert err.type == ErrorType.API_DOWN

def test_make_error_duckdb(monkeypatch):
    class MockIOException(Exception):
        pass
    import sys
    # We mock duckdb IOException if duckdb is not installed, but it usually is.
    try:
        from duckdb import IOException
        err = make_error(IOException("database is locked"))
        assert err.type == ErrorType.DB_LOCKED
    except ImportError:
        pass

def test_make_error_rate_limit():
    err = make_error(Exception("rate limit exceeded"), {"retry_after": 30})
    assert err.type == ErrorType.RATE_LIMIT
    assert err.context["seconds"] == 30

def test_make_error_circuit_breaker():
    err = make_error(Exception("circuit breaker is open"))
    assert err.type == ErrorType.CIRCUIT_OPEN

def test_make_error_db_locked():
    err = make_error(Exception("database is locked"))
    assert err.type == ErrorType.DB_LOCKED

def test_make_error_too_large():
    err = make_error(Exception("file is too large"))
    assert err.type == ErrorType.FILE_TOO_LARGE

def test_make_error_mime():
    err = make_error(Exception("invalid mime type"))
    assert err.type == ErrorType.INVALID_FILE

def test_make_error_generic():
    err = make_error(Exception("some unknown error"))
    assert err.type == ErrorType.GENERIC
    assert err.suggested_action == "retry_or_home"

def test_user_error_properties():
    err = UserError(ErrorType.NETWORK)
    # The title and body properties will call t(). We just check if they don't crash.
    assert isinstance(err.title, str)
    assert isinstance(err.body, str)
    assert err.suggested_action == "check_connection"
