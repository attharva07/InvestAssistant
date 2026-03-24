import os

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(_API_KEY_HEADER)) -> None:
    """Dependency that enforces X-API-Key header on every protected route."""
    expected = os.getenv("API_KEY", "")
    if not expected:
        # Dev mode: no key configured → allow all
        return
    if not api_key or api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
