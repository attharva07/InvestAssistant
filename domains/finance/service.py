import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from domains.finance.models import (
    Holding, Transaction, PriceCache, Account, AccountTransaction,
    CreditCard, CardTransaction, Budget, SavingsGoal, Alert, NetWorthLog
)
from domains.finance.schemas import (
    HoldingOut, PortfolioSummary, StockAnalysis, NetWorthSummary,
    FinancialSummary, BudgetOut, SavingsGoalOut, MonthlyReport
)

def parse_and_store_csv(file_bytes: bytes, db: Session, reconcile: bool = False) -> dict:
    from io import BytesIO
    df = pd.read_csv(BytesIO(file_bytes))
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    required = {"symbol", "quantity", "average_cost"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"CSV missing columns. Found: {list(df.columns)}")
    imported = 0
    mismatches = []
    for _, row in df.iterrows():
        ticker = str(row["symbol"]).strip().upper()
        shares = float(row["quantity"])
        avg_cost = float(row["average_cost"])
        if shares <= 0:
            continue
        existing = db.query(Holding).filter(Holding.ticker == ticker).first()
        if reconcile and existing:
            if abs(existing.shares - shares) > 0.01:
                mismatches.append({"ticker": ticker, "local": existing.shares, "csv": shares})
        if existing:
            existing.shares = shares
            existing.avg_cost = avg_cost
            existing.updated_at = datetime.utcnow()
        else:
            db.add(Holding(ticker=ticker, shares=shares, avg_cost=avg_cost))
        imported += 1
    db.commit()
    return {"imported": imported, "mismatches": mismatches}

def log_trade(data, db: Session):
    ticker = data.ticker.upper()
    shares = data.shares
    price = data.price
    amount = round(shares * price, 2)
    date = data.date or datetime.utcnow()
    txn = Transaction(ticker=ticker, action=data.action, shares=shares,
                      price=price, amount=amount, date=date)
    db.add(txn)
    existing = db.query(Holding).filter(Holding.ticker == ticker).first()
    if data.action == "buy":
        if existing:
            total_shares = existing.shares + shares
            total_cost = (existing.shares * existing.avg_cost) + (shares * price)
            existing.avg_cost = round(total_cost / total_shares, 2)
            existing.shares = round(total_shares, 4)
            existing.updated_at = datetime.utcnow()
        else:
            db.add(Holding(ticker=ticker, shares=shares, avg_cost=price))
    elif data.action == "sell" and existing:
        existing.shares = round(existing.shares - shares, 4)
        existing.updated_at = datetime.utcnow()
        if existing.shares <= 0:
            db.delete(existing)
    db.commit()
    db.refresh(txn)
    return txn

def get_transactions(db: Session, ticker: Optional[str] = None):
    q = db.query(Transaction)
    if ticker:
        q = q.filter(Transaction.ticker == ticker.upper())
    return q.order_by(Transaction.date.desc()).all()

def fetch_and_cache_prices(tickers: List[str], db: Session) -> dict:
    updated = 0
    for ticker in tickers:
        try:
            data = yf.Ticker(ticker)
            price = data.fast_info["last_price"]
            if not price:
                continue
            cached = db.query(PriceCache).filter(PriceCache.ticker == ticker).first()
            if cached:
                cached.price = round(price, 2)
                cached.fetched_at = datetime.utcnow()
            else:
                db.add(PriceCache(ticker=ticker, price=round(price, 2)))
            updated += 1
        except Exception:
            continue
    db.commit()
    return {"prices_updated": updated}

def get_portfolio_summary(db: Session) -> PortfolioSummary:
    holdings = db.query(Holding).all()
    tickers = [h.ticker for h in holdings]
    fetch_and_cache_prices(tickers, db)
    holding_outs = []
    total_invested = 0.0
    current_value = 0.0
    for h in holdings:
        invested = h.shares * h.avg_cost
        total_invested += invested
        price_row = db.query(PriceCache).filter(PriceCache.ticker == h.ticker).first()
        current_price = price_row.price if price_row else None
        curr_val = round(h.shares * current_price, 2) if current_price else None
        gain_loss = round(curr_val - invested, 2) if curr_val is not None else None
        gain_loss_pct = round((gain_loss / invested) * 100, 2) if gain_loss is not None and invested > 0 else None
        if curr_val:
            current_value += curr_val
        holding_outs.append(HoldingOut(
            id=h.id, ticker=h.ticker, shares=h.shares, avg_cost=h.avg_cost,
            current_price=current_price, current_value=curr_val,
            gain_loss=gain_loss, gain_loss_pct=gain_loss_pct
        ))
    total_gain_loss = round(current_value - total_invested, 2)
    total_gain_loss_pct = round((total_gain_loss / total_invested) * 100, 2) if total_invested > 0 else 0.0
    return PortfolioSummary(
        total_invested=round(total_invested, 2), current_value=round(current_value, 2),
        total_gain_loss=total_gain_loss, total_gain_loss_pct=total_gain_loss_pct,
        holdings=holding_outs
    )

def analyze_stock(ticker: str, db: Session) -> StockAnalysis:
    ticker = ticker.upper()
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        if hist.empty:
            raise ValueError(f"No data found for {ticker}")
        price = round(float(hist["Close"].iloc[-1]), 2)
        delta = hist["Close"].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)
        ma50 = round(float(hist["Close"].rolling(50).mean().iloc[-1]), 2)
        ma200 = round(float(hist["Close"].rolling(200).mean().iloc[-1]), 2)
        avg_vol = float(hist["Volume"].rolling(20).mean().iloc[-2])
        curr_vol = float(hist["Volume"].iloc[-1])
        vol_change = round(((curr_vol - avg_vol) / avg_vol) * 100, 1) if avg_vol > 0 else 0.0
        sentiment_score = 50.0
        try:
            news = stock.news or []
            if news:
                sentiment_score = min(100, max(0, 50 + (len(news) * 2)))
        except Exception:
            pass
        score = 50
        if rsi < 30: score += 15
        elif rsi > 70: score -= 15
        elif rsi < 45: score += 7
        if ma50 > ma200: score += 15
        else: score -= 10
        if vol_change > 20: score += 10
        if sentiment_score > 60: score += 10
        elif sentiment_score < 40: score -= 10
        score = max(0, min(100, score))
        outlook = "Bullish" if score >= 65 else "Bearish" if score < 45 else "Neutral"
        rsi_text = "oversold — historically a buying opportunity" if rsi < 30 else "overbought — potential pullback ahead" if rsi > 70 else "in neutral territory"
        ma_text = "bullish golden cross — upward momentum" if ma50 > ma200 else "bearish death cross — downward pressure"
        vol_text = f"elevated at +{vol_change}%, suggesting strong market interest" if vol_change > 20 else "within normal range"
        reasoning = (
            f"{ticker} scores {score}/100. RSI at {rsi} is {rsi_text}. "
            f"The 50-day MA (${ma50}) is {'above' if ma50 > ma200 else 'below'} the 200-day MA (${ma200}), "
            f"indicating a {ma_text}. Volume is {vol_text}. "
            f"This is signal-based analysis — not a price prediction. Always do your own research."
        )
        return StockAnalysis(
            ticker=ticker, price=price, score=score, outlook=outlook,
            rsi=rsi, ma50=ma50, ma200=ma200,
            volume_change_pct=vol_change, sentiment_score=sentiment_score,
            reasoning=reasoning
        )
    except Exception as e:
        raise ValueError(f"Analysis failed for {ticker}: {str(e)}")

def create_account(data, db: Session):
    acc = Account(name=data.name, account_type=data.account_type,
                  balance=data.balance, interest_rate=data.interest_rate)
    db.add(acc); db.commit(); db.refresh(acc)
    return acc

def get_accounts(db: Session):
    return db.query(Account).all()

def add_account_transaction(data, db: Session):
    acc = db.query(Account).filter(Account.id == data.account_id).first()
    if not acc:
        raise ValueError("Account not found")
    if data.action == "deposit":
        acc.balance = round(acc.balance + data.amount, 2)
    elif data.action == "withdrawal":
        acc.balance = round(acc.balance - data.amount, 2)
    txn = AccountTransaction(account_id=data.account_id, action=data.action,
                              amount=data.amount, note=data.note)
    db.add(txn); db.commit(); db.refresh(txn)
    return txn

def get_account_transactions(account_id: int, db: Session):
    return db.query(AccountTransaction).filter(
        AccountTransaction.account_id == account_id).order_by(
        AccountTransaction.date.desc()).all()

def create_credit_card(data, db: Session):
    card = CreditCard(name=data.name, balance=data.balance,
                      credit_limit=data.credit_limit, due_date=data.due_date,
                      interest_rate=data.interest_rate)
    db.add(card); db.commit(); db.refresh(card)
    return card

def get_credit_cards(db: Session):
    return db.query(CreditCard).all()

def add_card_transaction(data, db: Session):
    card = db.query(CreditCard).filter(CreditCard.id == data.card_id).first()
    if not card:
        raise ValueError("Card not found")
    card.balance = round(card.balance + data.amount, 2)
    txn = CardTransaction(card_id=data.card_id, amount=data.amount,
                          category=data.category, note=data.note)
    db.add(txn); db.commit(); db.refresh(txn)
    return txn

def get_card_transactions(card_id: int, db: Session):
    return db.query(CardTransaction).filter(
        CardTransaction.card_id == card_id).order_by(
        CardTransaction.date.desc()).all()

def create_budget(data, db: Session):
    existing = db.query(Budget).filter(Budget.category == data.category).first()
    if existing:
        existing.monthly_limit = data.monthly_limit
        db.commit(); db.refresh(existing)
        return existing
    b = Budget(category=data.category, monthly_limit=data.monthly_limit)
    db.add(b); db.commit(); db.refresh(b)
    return b

def get_budgets_with_spending(db: Session) -> List[BudgetOut]:
    budgets = db.query(Budget).all()
    result = []
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for b in budgets:
        spent = sum(
            t.amount for t in db.query(CardTransaction)
            .filter(CardTransaction.category == b.category,
                    CardTransaction.date >= month_start).all()
        )
        spent = round(spent, 2)
        result.append(BudgetOut(
            id=b.id, category=b.category, monthly_limit=b.monthly_limit,
            spent=spent, remaining=round(b.monthly_limit - spent, 2)
        ))
    return result

def create_savings_goal(data, db: Session):
    g = SavingsGoal(name=data.name, target_amount=data.target_amount,
                    current_amount=data.current_amount, target_date=data.target_date)
    db.add(g); db.commit(); db.refresh(g)
    return g

def get_savings_goals(db: Session) -> List[SavingsGoalOut]:
    goals = db.query(SavingsGoal).all()
    return [SavingsGoalOut(
        id=g.id, name=g.name, target_amount=g.target_amount,
        current_amount=g.current_amount, target_date=g.target_date,
        completed=g.completed,
        progress_pct=round((g.current_amount / g.target_amount) * 100, 1) if g.target_amount > 0 else 0.0
    ) for g in goals]

def update_savings_goal_progress(goal_id: int, amount: float, db: Session):
    g = db.query(SavingsGoal).filter(SavingsGoal.id == goal_id).first()
    if not g:
        raise ValueError("Goal not found")
    g.current_amount = round(g.current_amount + amount, 2)
    if g.current_amount >= g.target_amount:
        g.completed = True
    db.commit(); db.refresh(g)
    return g

def create_alert(data, db: Session):
    a = Alert(alert_type=data.alert_type,
              ticker=data.ticker.upper() if data.ticker else None,
              condition=data.condition, threshold=data.threshold, note=data.note)
    db.add(a); db.commit(); db.refresh(a)
    return a

def get_alerts(db: Session):
    return db.query(Alert).order_by(Alert.created_at.desc()).all()

def check_and_trigger_alerts(db: Session) -> dict:
    alerts = db.query(Alert).filter(Alert.triggered == False).all()
    triggered_count = 0
    now = datetime.utcnow()
    for alert in alerts:
        if alert.alert_type == "price" and alert.ticker:
            price_row = db.query(PriceCache).filter(PriceCache.ticker == alert.ticker).first()
            if price_row:
                hit = ((alert.condition == "above" and price_row.price >= alert.threshold) or
                       (alert.condition == "below" and price_row.price <= alert.threshold))
                if hit:
                    alert.triggered = True; alert.triggered_at = now; triggered_count += 1
        elif alert.alert_type == "due_date":
            cards = db.query(CreditCard).filter(CreditCard.due_date != None).all()
            for card in cards:
                if card.due_date and (card.due_date - now).days <= 3:
                    alert.triggered = True; alert.triggered_at = now; triggered_count += 1; break
        elif alert.alert_type == "budget":
            budgets = get_budgets_with_spending(db)
            for b in budgets:
                if b.spent > b.monthly_limit:
                    alert.triggered = True; alert.triggered_at = now; triggered_count += 1; break
    db.commit()
    return {"triggered": triggered_count}

def get_net_worth(db: Session) -> NetWorthSummary:
    portfolio = get_portfolio_summary(db)
    investment_value = portfolio.current_value
    accounts = db.query(Account).all()
    savings_total = round(sum(a.balance for a in accounts if a.account_type == "savings"), 2)
    checking_total = round(sum(a.balance for a in accounts if a.account_type == "checking"), 2)
    cards = db.query(CreditCard).all()
    credit_card_debt = round(sum(c.balance for c in cards), 2)
    total_assets = round(investment_value + savings_total + checking_total, 2)
    total_liabilities = credit_card_debt
    net_worth = round(total_assets - total_liabilities, 2)
    log = NetWorthLog(total_assets=total_assets, total_liabilities=total_liabilities, net_worth=net_worth)
    db.add(log); db.commit()
    return NetWorthSummary(
        investment_value=investment_value, savings_total=savings_total,
        checking_total=checking_total, credit_card_debt=credit_card_debt,
        total_assets=total_assets, total_liabilities=total_liabilities, net_worth=net_worth
    )

def get_financial_summary(db: Session) -> FinancialSummary:
    net_worth = get_net_worth(db)
    budgets = get_budgets_with_spending(db)
    goals = get_savings_goals(db)
    active_alerts = db.query(Alert).filter(Alert.triggered == False).count()
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    deposits = sum(t.amount for t in db.query(AccountTransaction)
                   .filter(AccountTransaction.action == "deposit",
                           AccountTransaction.date >= month_start).all())
    withdrawals = sum(t.amount for t in db.query(AccountTransaction)
                      .filter(AccountTransaction.action == "withdrawal",
                              AccountTransaction.date >= month_start).all())
    monthly_cashflow = round(deposits - withdrawals, 2)
    return FinancialSummary(
        net_worth=net_worth, monthly_cashflow=monthly_cashflow,
        budget_status=budgets, active_alerts=active_alerts, savings_goals=goals
    )

def get_monthly_report(db: Session, month: Optional[int] = None, year: Optional[int] = None) -> MonthlyReport:
    now = datetime.utcnow()
    month = month or now.month
    year = year or now.year
    month_start = datetime(year, month, 1)
    month_end = datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)
    income = sum(t.amount for t in db.query(AccountTransaction)
                 .filter(AccountTransaction.action == "deposit",
                         AccountTransaction.date >= month_start,
                         AccountTransaction.date < month_end).all())
    spending = sum(t.amount for t in db.query(CardTransaction)
                   .filter(CardTransaction.date >= month_start,
                           CardTransaction.date < month_end).all())
    cat_txns = db.query(CardTransaction).filter(
        CardTransaction.date >= month_start, CardTransaction.date < month_end).all()
    by_category = {}
    for t in cat_txns:
        cat = t.category or "Uncategorized"
        by_category[cat] = round(by_category.get(cat, 0) + t.amount, 2)
    nw_logs = db.query(NetWorthLog).filter(
        NetWorthLog.logged_at >= month_start,
        NetWorthLog.logged_at < month_end).order_by(NetWorthLog.logged_at).all()
    nw_change = round(nw_logs[-1].net_worth - nw_logs[0].net_worth, 2) if len(nw_logs) >= 2 else 0.0
    portfolio = get_portfolio_summary(db)
    goals = get_savings_goals(db)
    return MonthlyReport(
        month=f"{year}-{month:02d}",
        total_income=round(income, 2),
        total_spending=round(spending, 2),
        spending_by_category=by_category,
        portfolio_gain_loss=portfolio.total_gain_loss,
        net_worth_change=nw_change,
        savings_progress=goals
    )
