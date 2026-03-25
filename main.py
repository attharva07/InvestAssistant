from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from core.database import init_db
from domains.finance.router import router as finance_router

app = FastAPI(
    title="InvestAssistant",
    description="Personal finance and investment intelligence system",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "online", "system": "InvestAssistant v1.0"}

app.include_router(finance_router)
