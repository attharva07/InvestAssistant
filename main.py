from fastapi import FastAPI, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from core.database import init_db
from domains.finance.router import router as finance_router
import os
from dotenv import load_dotenv
from fastapi.openapi.utils import get_openapi

load_dotenv()
API_KEY = os.getenv("API_KEY", "changeme")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

app = FastAPI(
    title="InvestAssistant",
    version="1.0.0",
    description="Personal finance and investment intelligence system"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        return JSONResponse(status_code=403, content={"detail": "Invalid or missing API key"})
    return await call_next(request)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "online", "system": "InvestAssistant v1.0"}

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="InvestAssistant",
        version="1.0.0",
        description="Personal finance and investment intelligence system",
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "APIKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key"
        }
    }
    openapi_schema["security"] = [{"APIKeyHeader": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.include_router(finance_router)
app.openapi = custom_openapi
