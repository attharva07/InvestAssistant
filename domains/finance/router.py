from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from core.database import get_db
from domains.finance import service
from domains.finance.schemas import (
    PortfolioSummary, AlertCreate, AlertOut, AccountCreate, AccountOut,
    AccountTransactionCreate, AccountTransactionOut, CreditCardCreate, CreditCardOut,
    CardTransactionCreate, CardTransactionOut, BudgetCreate, BudgetOut,
    SavingsGoalCreate, SavingsGoalOut, StockAnalysis, FinancialSummary,
    NetWorthSummary, TradeCreate, TransactionOut, MonthlyReport
)

router = APIRouter(prefix="/finance", tags=["Finance"])

@router.post("/upload")
def upload_csv(reconcile: bool = False, file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files accepted")
    try:
        result = service.parse_and_store_csv(file.file.read(), db, reconcile=reconcile)
        return {"message": "Portfolio imported", "imported": result["imported"], "mismatches": result["mismatches"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/trades", response_model=TransactionOut)
def log_trade(data: TradeCreate, db: Session = Depends(get_db)):
    if data.action not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="Action must be 'buy' or 'sell'")
    return service.log_trade(data, db)

@router.get("/trades", response_model=List[TransactionOut])
def get_trades(ticker: Optional[str] = None, db: Session = Depends(get_db)):
    return service.get_transactions(db, ticker)

@router.get("/portfolio", response_model=PortfolioSummary)
def get_portfolio(db: Session = Depends(get_db)):
    return service.get_portfolio_summary(db)

@router.get("/analyze/{ticker}", response_model=StockAnalysis)
def analyze_stock(ticker: str, db: Session = Depends(get_db)):
    try:
        return service.analyze_stock(ticker, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/accounts", response_model=AccountOut)
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    return service.create_account(data, db)

@router.get("/accounts", response_model=List[AccountOut])
def get_accounts(db: Session = Depends(get_db)):
    return service.get_accounts(db)

@router.post("/accounts/transaction", response_model=AccountTransactionOut)
def add_account_transaction(data: AccountTransactionCreate, db: Session = Depends(get_db)):
    try:
        return service.add_account_transaction(data, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/accounts/{account_id}/transactions", response_model=List[AccountTransactionOut])
def get_account_transactions(account_id: int, db: Session = Depends(get_db)):
    return service.get_account_transactions(account_id, db)

@router.post("/cards", response_model=CreditCardOut)
def create_card(data: CreditCardCreate, db: Session = Depends(get_db)):
    return service.create_credit_card(data, db)

@router.get("/cards", response_model=List[CreditCardOut])
def get_cards(db: Session = Depends(get_db)):
    return service.get_credit_cards(db)

@router.post("/cards/transaction", response_model=CardTransactionOut)
def add_card_transaction(data: CardTransactionCreate, db: Session = Depends(get_db)):
    try:
        return service.add_card_transaction(data, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/cards/{card_id}/transactions", response_model=List[CardTransactionOut])
def get_card_transactions(card_id: int, db: Session = Depends(get_db)):
    return service.get_card_transactions(card_id, db)

@router.post("/budget", response_model=BudgetOut)
def create_budget(data: BudgetCreate, db: Session = Depends(get_db)):
    return service.create_budget(data, db)

@router.get("/budget", response_model=List[BudgetOut])
def get_budgets(db: Session = Depends(get_db)):
    return service.get_budgets_with_spending(db)

@router.post("/goals", response_model=SavingsGoalOut)
def create_goal(data: SavingsGoalCreate, db: Session = Depends(get_db)):
    return service.create_savings_goal(data, db)

@router.get("/goals", response_model=List[SavingsGoalOut])
def get_goals(db: Session = Depends(get_db)):
    return service.get_savings_goals(db)

@router.patch("/goals/{goal_id}/progress")
def update_goal(goal_id: int, amount: float, db: Session = Depends(get_db)):
    try:
        return service.update_savings_goal_progress(goal_id, amount, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/alerts", response_model=AlertOut)
def create_alert(data: AlertCreate, db: Session = Depends(get_db)):
    return service.create_alert(data, db)

@router.get("/alerts", response_model=List[AlertOut])
def get_alerts(db: Session = Depends(get_db)):
    return service.get_alerts(db)

@router.post("/alerts/check")
def check_alerts(db: Session = Depends(get_db)):
    return service.check_and_trigger_alerts(db)

@router.get("/net-worth", response_model=NetWorthSummary)
def get_net_worth(db: Session = Depends(get_db)):
    return service.get_net_worth(db)

@router.get("/summary", response_model=FinancialSummary)
def get_summary(db: Session = Depends(get_db)):
    return service.get_financial_summary(db)

@router.get("/report", response_model=MonthlyReport)
def get_report(month: Optional[int] = None, year: Optional[int] = None, db: Session = Depends(get_db)):
    return service.get_monthly_report(db, month, year)
