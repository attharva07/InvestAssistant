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
from domains.finance.models import (
    Holding, Transaction, PriceCache, Account, AccountTransaction,
    CreditCard, CardTransaction, Budget, SavingsGoal, Alert, NetWorthLog, Transfer
)

# ── CSV Import ────────────────────────────────────────────────────────────────

def parse_and_store_csv(file_bytes: bytes, db: Session, reconcile: bool = False) -> dict:
    from io import BytesIO
    try:
        df = pd.read_csv(BytesIO(file_bytes), on_bad_lines='skip')
    except Exception:
        df = pd.read_csv(BytesIO(file_bytes))
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    is_transaction_format = "instrument" in df.columns and "trans_code" in df.columns
    is_holdings_format = "symbol" in df.columns and "average_cost" in df.columns
    if is_transaction_format:
        return _parse_transaction_csv(df, db, reconcile)
    elif is_holdings_format:
        return _parse_holdings_csv(df, db, reconcile)
    else:
        raise ValueError(f"Unrecognized CSV format. Columns found: {list(df.columns)}")


def _parse_holdings_csv(df, db: Session, reconcile: bool) -> dict:
    imported = 0
    mismatches = []
    for _, row in df.iterrows():
        try:
            ticker = str(row["symbol"]).strip().upper()
            if not ticker or ticker == "NAN":
                continue
            shares = float(row["quantity"])
            avg_cost = float(row["average_cost"])
            if shares <= 0:
                continue
            existing = db.query(Holding).filter(Holding.ticker == ticker).first()
            if reconcile and existing:
                if abs(existing.shares - shares) > 0.01:
                    mismatches.append({"ticker": ticker, "local": round(existing.shares, 4), "csv": round(shares, 4)})
            if existing:
                existing.shares = shares
                existing.avg_cost = avg_cost
                existing.updated_at = datetime.utcnow()
            else:
                db.add(Holding(ticker=ticker, shares=shares, avg_cost=avg_cost))
            imported += 1
        except (ValueError, TypeError):
            continue
    db.commit()
    return {"imported": imported, "mismatches": mismatches}


def _parse_transaction_csv(df, db: Session, reconcile: bool) -> dict:
    buy_codes = {"buy", "bto", "bought", "Buy"}
    sell_codes = {"sell", "sll", "sto", "sold", "Sell"}
    holdings_map = {}
    transactions_to_log = []

    for _, row in df.iterrows():
        try:
            ticker = str(row.get("instrument", "")).strip().upper()
            if not ticker or ticker == "NAN" or ticker == "":
                continue

            trans_code = str(row.get("trans_code", "")).strip().lower()

            raw_qty = row.get("quantity", 0)
            raw_price = row.get("price", 0)

            if pd.isna(raw_qty) or pd.isna(raw_price):
                continue

            # Remove commas and dollar signs if present
            quantity = abs(float(str(raw_qty).replace(",", "").replace("$", "")))
            price = abs(float(str(raw_price).replace(",", "").replace("$", "")))

            if quantity <= 0 or price <= 0:
                continue

            date_str = str(row.get("activity_date", "")).strip()
            try:
                txn_date = datetime.strptime(date_str, "%m/%d/%Y")
            except Exception:
                txn_date = datetime.utcnow()

            is_buy = any(code in trans_code for code in buy_codes)
            is_sell = any(code in trans_code for code in sell_codes)

            if not is_buy and not is_sell:
                continue

            action = "buy" if is_buy else "sell"

            if ticker not in holdings_map:
                holdings_map[ticker] = {"shares": 0.0, "total_cost": 0.0}

            if is_buy:
                holdings_map[ticker]["shares"] += quantity
                holdings_map[ticker]["total_cost"] += quantity * price
            else:
                holdings_map[ticker]["shares"] -= quantity
                holdings_map[ticker]["total_cost"] -= quantity * price

            transactions_to_log.append({
                "ticker": ticker, "action": action, "shares": quantity,
                "price": price, "amount": round(quantity * price, 2), "date": txn_date
            })

        except (ValueError, TypeError):
            continue

    logged = 0
    for t in transactions_to_log:
        existing_txn = db.query(Transaction).filter(
            Transaction.ticker == t["ticker"], Transaction.date == t["date"],
            Transaction.action == t["action"], Transaction.shares == t["shares"]
        ).first()
        if not existing_txn:
            db.add(Transaction(**t))
            logged += 1

    imported = 0
    mismatches = []
    for ticker, data in holdings_map.items():
        shares = round(data["shares"], 4)
        if shares <= 0:
            continue
        avg_cost = round(data["total_cost"] / shares, 2) if shares > 0 else 0
        existing = db.query(Holding).filter(Holding.ticker == ticker).first()
        if reconcile and existing:
            if abs(existing.shares - shares) > 0.01:
                mismatches.append({"ticker": ticker, "local": round(existing.shares, 4), "csv": round(shares, 4)})
        if existing:
            existing.shares = shares
            existing.avg_cost = avg_cost
            existing.updated_at = datetime.utcnow()
        else:
            db.add(Holding(ticker=ticker, shares=shares, avg_cost=avg_cost))
        imported += 1

    db.commit()
    return {"imported": imported, "transactions_logged": logged, "mismatches": mismatches, "format": "robinhood_transactions"}


# ── Investments ───────────────────────────────────────────────────────────────

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


# ── Intelligence ──────────────────────────────────────────────────────────────

def analyze_stock(ticker: str, db: Session) -> StockAnalysis:
    ticker = ticker.upper()
    try:
        stock = yf.Ticker(ticker)

        # Rate limit protection — add small delay
        import time
        time.sleep(0.5)

        hist = stock.history(period="1y")
        if hist.empty:
            raise ValueError(f"No data found for {ticker}")

        # Use fast_info for basic price to avoid extra requests
        try:
            info = stock.info
        except Exception:
            info = {}

        info = stock.info
        hist = stock.history(period="1y")
        if hist.empty:
            raise ValueError(f"No price data found for {ticker}")

        price = round(float(hist["Close"].iloc[-1]), 2)

        pe_ratio = info.get("trailingPE") or info.get("forwardPE")
        sector = info.get("sector", "Unknown")
        industry = info.get("industry", "Unknown")
        sector_pe = {
            "Technology": 28, "Healthcare": 22, "Financial Services": 14,
            "Consumer Cyclical": 20, "Consumer Defensive": 20,
            "Industrials": 18, "Energy": 12, "Utilities": 16,
            "Real Estate": 30, "Communication Services": 22,
            "Basic Materials": 15, "Unknown": 20
        }
        avg_pe = sector_pe.get(sector, 20)
        pe_score = 0
        pe_signal = "No PE data available"
        if pe_ratio:
            pe_ratio = round(pe_ratio, 1)
            if pe_ratio < avg_pe * 0.8:
                pe_score = 25
                pe_signal = f"Undervalued — PE {pe_ratio} well below sector avg {avg_pe}"
            elif pe_ratio < avg_pe:
                pe_score = 15
                pe_signal = f"Fairly valued — PE {pe_ratio} below sector avg {avg_pe}"
            elif pe_ratio < avg_pe * 1.3:
                pe_score = 5
                pe_signal = f"Slightly overvalued — PE {pe_ratio} above sector avg {avg_pe}"
            else:
                pe_score = -10
                pe_signal = f"Overvalued — PE {pe_ratio} significantly above sector avg {avg_pe}"

        revenue_growth = info.get("revenueGrowth")
        rev_score = 0
        rev_signal = "No revenue growth data"
        if revenue_growth is not None:
            revenue_growth_pct = round(revenue_growth * 100, 1)
            if revenue_growth_pct > 20:
                rev_score = 20
                rev_signal = f"Strong revenue growth at +{revenue_growth_pct}% YoY"
            elif revenue_growth_pct > 10:
                rev_score = 15
                rev_signal = f"Solid revenue growth at +{revenue_growth_pct}% YoY"
            elif revenue_growth_pct > 0:
                rev_score = 8
                rev_signal = f"Modest revenue growth at +{revenue_growth_pct}% YoY"
            else:
                rev_score = -10
                rev_signal = f"Revenue declining at {revenue_growth_pct}% YoY — red flag"

        profit_margin = info.get("profitMargins")
        margin_score = 0
        margin_signal = "No profit margin data"
        if profit_margin is not None:
            margin_pct = round(profit_margin * 100, 1)
            if margin_pct > 20:
                margin_score = 20
                margin_signal = f"Excellent profit margin at {margin_pct}%"
            elif margin_pct > 10:
                margin_score = 15
                margin_signal = f"Healthy profit margin at {margin_pct}%"
            elif margin_pct > 0:
                margin_score = 5
                margin_signal = f"Thin profit margin at {margin_pct}% — watch closely"
            else:
                margin_score = -15
                margin_signal = f"Company is unprofitable — margin at {margin_pct}%"

        debt_to_equity = info.get("debtToEquity")
        debt_score = 0
        debt_signal = "No debt data"
        if debt_to_equity is not None:
            dte = round(debt_to_equity, 1)
            if dte < 30:
                debt_score = 15
                debt_signal = f"Very low debt — D/E ratio {dte}% (financially strong)"
            elif dte < 80:
                debt_score = 10
                debt_signal = f"Manageable debt — D/E ratio {dte}%"
            elif dte < 150:
                debt_score = 0
                debt_signal = f"Moderate debt — D/E ratio {dte}% (monitor)"
            else:
                debt_score = -10
                debt_signal = f"High debt — D/E ratio {dte}% (risky for long term)"

        fcf = info.get("freeCashflow")
        fcf_score = 0
        fcf_signal = "No free cash flow data"
        if fcf is not None:
            fcf_b = round(fcf / 1e9, 2)
            if fcf > 0:
                fcf_score = 15
                fcf_signal = f"Positive free cash flow at ${fcf_b}B — company generates real cash"
            else:
                fcf_score = -10
                fcf_signal = f"Negative free cash flow at ${fcf_b}B — burning cash"

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

        tech_score = 0
        tech_signal = ""
        if ma50 > ma200:
            tech_score += 5
            tech_signal = "Price trend is upward (50-day MA above 200-day MA)"
        else:
            tech_score -= 5
            tech_signal = "Price trend is downward (50-day MA below 200-day MA)"
        if rsi < 40:
            tech_score += 5
            tech_signal += f", RSI {rsi} suggests a potential buying opportunity"
        elif rsi > 70:
            tech_score -= 5
            tech_signal += f", RSI {rsi} suggests stock may be overbought short-term"

        beta = info.get("beta")
        macro_signal = ""
        if beta is not None:
            beta = round(beta, 2)
            if beta > 1.5:
                macro_signal = f"High beta ({beta}) — moves aggressively with market. Volatile in downturns."
            elif beta > 1.0:
                macro_signal = f"Beta {beta} — moderately sensitive to market swings."
            else:
                macro_signal = f"Low beta ({beta}) — relatively stable, less affected by market volatility."

        raw_score = 50 + pe_score + rev_score + margin_score + debt_score + fcf_score + tech_score
        score = max(0, min(100, raw_score))
        if score >= 70:
            outlook = "Strong Buy"
        elif score >= 55:
            outlook = "Buy"
        elif score >= 45:
            outlook = "Hold"
        elif score >= 35:
            outlook = "Caution"
        else:
            outlook = "Avoid"

        company_name = info.get("longName", ticker)
        reasoning = (
            f"{company_name} ({ticker}) scores {score}/100 for long-term investing. "
            f"Valuation: {pe_signal}. "
            f"Growth: {rev_signal}. "
            f"Profitability: {margin_signal}. "
            f"Financial health: {debt_signal}. "
            f"Cash generation: {fcf_signal}. "
            f"Entry timing: {tech_signal}. "
        )
        if macro_signal:
            reasoning += f"Market sensitivity: {macro_signal} "
        reasoning += (
            f"Sector: {sector} ({industry}). "
            f"This is a long-term fundamental analysis. "
            f"Always do your own research before investing."
        )

        return StockAnalysis(
            ticker=ticker, price=price, score=score, outlook=outlook,
            rsi=rsi, ma50=ma50, ma200=ma200,
            volume_change_pct=vol_change, sentiment_score=50.0,
            reasoning=reasoning
        )
    except Exception as e:
        raise ValueError(f"Analysis failed for {ticker}: {str(e)}")


# ── Accounts ──────────────────────────────────────────────────────────────────

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


# ── Credit Cards ──────────────────────────────────────────────────────────────

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


# ── Budget ────────────────────────────────────────────────────────────────────

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


# ── Savings Goals ─────────────────────────────────────────────────────────────

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


# ── Alerts ────────────────────────────────────────────────────────────────────

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


def create_transfer(data, db: Session):
    from_acc = db.query(Account).filter(Account.id == data.from_account_id).first()
    if not from_acc:
        raise ValueError("Source account not found")
    if from_acc.balance < data.amount:
        raise ValueError(f"Insufficient balance — account has {round(from_acc.balance, 2)}, transfer needs {data.amount}")

    if data.transfer_type == "account_to_account":
        to_acc = db.query(Account).filter(Account.id == data.to_account_id).first()
        if not to_acc:
            raise ValueError("Destination account not found")

        # Debit source
        from_acc.balance = round(from_acc.balance - data.amount, 2)
        db.add(AccountTransaction(
            account_id=from_acc.id, action="withdrawal",
            amount=data.amount, note=f"Transfer to {to_acc.name}: {data.note or ''}"
        ))

        # Credit destination
        to_acc.balance = round(to_acc.balance + data.amount, 2)
        db.add(AccountTransaction(
            account_id=to_acc.id, action="deposit",
            amount=data.amount, note=f"Transfer from {from_acc.name}: {data.note or ''}"
        ))

    elif data.transfer_type == "account_to_card":
        card = db.query(CreditCard).filter(CreditCard.id == data.to_card_id).first()
        if not card:
            raise ValueError("Card not found")

        # Debit source account
        from_acc.balance = round(from_acc.balance - data.amount, 2)
        db.add(AccountTransaction(
            account_id=from_acc.id, action="withdrawal",
            amount=data.amount, note=f"Card payment to {card.name}: {data.note or ''}"
        ))

        # Reduce card balance (payment reduces what you owe)
        card.balance = round(max(0, card.balance - data.amount), 2)

    else:
        raise ValueError("Invalid transfer type")

    # Log the transfer record
    transfer = Transfer(
        transfer_type=data.transfer_type,
        from_account_id=data.from_account_id,
        to_account_id=data.to_account_id,
        to_card_id=data.to_card_id,
        amount=data.amount,
        note=data.note
    )
    db.add(transfer)
    db.commit()
    db.refresh(transfer)
    return transfer


def get_transfers(db: Session):
    return db.query(Transfer).order_by(Transfer.date.desc()).all()
# ── Net Worth & Summary ───────────────────────────────────────────────────────

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