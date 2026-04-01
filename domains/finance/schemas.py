from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class HoldingOut(BaseModel):
    id: int
    ticker: str
    shares: float
    avg_cost: float
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    gain_loss: Optional[float] = None
    gain_loss_pct: Optional[float] = None
    class Config:
        from_attributes = True

class PortfolioSummary(BaseModel):
    total_invested: float
    current_value: float
    total_gain_loss: float
    total_gain_loss_pct: float
    holdings: List[HoldingOut]

class TradeCreate(BaseModel):
    ticker: str
    action: str
    shares: float
    price: float
    date: Optional[datetime] = None

class TransactionOut(BaseModel):
    id: int
    ticker: str
    action: str
    shares: float
    price: float
    amount: float
    date: datetime
    class Config:
        from_attributes = True

class AccountCreate(BaseModel):
    name: str
    account_type: str
    balance: float = 0.0
    interest_rate: float = 0.0

class AccountOut(BaseModel):
    id: int
    name: str
    account_type: str
    balance: float
    interest_rate: float
    class Config:
        from_attributes = True

class AccountTransactionCreate(BaseModel):
    account_id: int
    action: str
    amount: float
    note: Optional[str] = None

class AccountTransactionOut(BaseModel):
    id: int
    account_id: int
    action: str
    amount: float
    note: Optional[str] = None
    date: datetime
    class Config:
        from_attributes = True

class CreditCardCreate(BaseModel):
    name: str
    balance: float = 0.0
    credit_limit: float
    due_date: Optional[datetime] = None
    interest_rate: float = 0.0

class CreditCardOut(BaseModel):
    id: int
    name: str
    balance: float
    credit_limit: float
    due_date: Optional[datetime] = None
    interest_rate: float
    class Config:
        from_attributes = True

class CardTransactionCreate(BaseModel):
    card_id: int
    amount: float
    category: Optional[str] = None
    note: Optional[str] = None

class CardTransactionOut(BaseModel):
    id: int
    card_id: int
    amount: float
    category: Optional[str] = None
    note: Optional[str] = None
    date: datetime
    class Config:
        from_attributes = True

class BudgetCreate(BaseModel):
    category: str
    monthly_limit: float

class BudgetOut(BaseModel):
    id: int
    category: str
    monthly_limit: float
    spent: float = 0.0
    remaining: float = 0.0
    class Config:
        from_attributes = True

class SavingsGoalCreate(BaseModel):
    name: str
    target_amount: float
    current_amount: float = 0.0
    target_date: Optional[datetime] = None

class SavingsGoalOut(BaseModel):
    id: int
    name: str
    target_amount: float
    current_amount: float
    target_date: Optional[datetime] = None
    completed: bool
    progress_pct: float = 0.0
    class Config:
        from_attributes = True

class AlertCreate(BaseModel):
    alert_type: str
    ticker: Optional[str] = None
    condition: Optional[str] = None
    threshold: Optional[float] = None
    note: Optional[str] = None

class AlertOut(BaseModel):
    id: int
    alert_type: str
    ticker: Optional[str] = None
    condition: Optional[str] = None
    threshold: Optional[float] = None
    triggered: bool
    triggered_at: Optional[datetime] = None
    note: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

class StockAnalysis(BaseModel):
    ticker: str
    price: float
    score: int
    outlook: str
    rsi: float
    ma50: float
    ma200: float
    volume_change_pct: float
    sentiment_score: float
    reasoning: str

class NetWorthSummary(BaseModel):
    investment_value: float
    savings_total: float
    checking_total: float
    credit_card_debt: float
    total_assets: float
    total_liabilities: float
    net_worth: float

class FinancialSummary(BaseModel):
    net_worth: NetWorthSummary
    monthly_cashflow: float
    budget_status: List[BudgetOut]
    active_alerts: int
    savings_goals: List[SavingsGoalOut]

class MonthlyReport(BaseModel):
    month: str
    total_income: float
    total_spending: float
    spending_by_category: dict
    portfolio_gain_loss: float
    net_worth_change: float
    savings_progress: List[SavingsGoalOut]

class TransferCreate(BaseModel):
    transfer_type: str  # "account_to_account" or "account_to_card"
    from_account_id: int
    to_account_id: Optional[int] = None
    to_card_id: Optional[int] = None
    amount: float
    note: Optional[str] = None

class TransferOut(BaseModel):
    id: int
    transfer_type: str
    from_account_id: int
    to_account_id: Optional[int] = None
    to_card_id: Optional[int] = None
    amount: float
    note: Optional[str] = None
    date: datetime
    class Config:
        from_attributes = True