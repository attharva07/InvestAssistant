# InvestAssistant

Personal finance and investment intelligence system.

## Setup
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set a strong API_KEY
uvicorn main:app --reload

## Auth
All routes require header: X-API-Key: your_key
Swagger UI (/docs) is public for testing.

## Key Routes
POST /finance/upload        — seed portfolio from Robinhood CSV
POST /finance/trades        — log a manual trade
GET  /finance/portfolio     — live portfolio + P&L
GET  /finance/analyze/{tk}  — stock signal analysis
GET  /finance/summary       — full financial picture
GET  /finance/report        — monthly report
