from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

st.set_page_config(page_title="InvestAssistant", layout="wide")
st.title("InvestAssistant (Local Prototype)")

page = st.sidebar.radio("Page", ["Import", "Portfolio", "Daily Brief", "Log Event", "Reminders"])


def call_api(method: str, path: str, **kwargs):
    try:
        resp = requests.request(method, f"{API_BASE}{path}", timeout=60, **kwargs)
        if not resp.ok:
            st.error(f"API error {resp.status_code}: {resp.text}")
            return None
        return resp.json()
    except requests.RequestException as e:
        st.error(f"Could not reach backend: {e}")
        return None


if page == "Import":
    st.subheader("Import Robinhood activity CSV")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    files = sorted([p.name for p in DATA_DIR.glob("*.csv")])
    selected = st.selectbox("Or select file from ./data", [""] + files)

    if st.button("Import now"):
        if uploaded is not None:
            data = call_api("POST", "/import/robinhood", files={"file": (uploaded.name, uploaded.getvalue(), "text/csv")})
        elif selected:
            data = call_api("POST", "/import/robinhood", json={"filename": selected})
        else:
            st.warning("Please upload or select a CSV file.")
            data = None

        if data:
            imported_count = data.get("imported_count", data.get("imported_events", 0))
            skipped_count = data.get("skipped_count", 0)
            st.success(f"Imported: {imported_count}")
            st.info(f"Skipped: {skipped_count}")
            st.caption(f"Holdings rebuilt: {data['holdings_count']} tickers")
            if data.get("errors_sample"):
                with st.expander("Skipped row examples"):
                    st.json(data["errors_sample"])
            st.json({"detected_columns": data.get("detected_columns", {})})

elif page == "Portfolio":
    st.subheader("Shadow Portfolio")
    data = call_api("GET", "/portfolio")
    if data:
        st.metric("Total Value (USD)", f"${data['total_value_usd']:,.2f}")
        if data.get("data_delayed"):
            st.warning("Some market data is delayed (cached fallback used).")
        st.dataframe(pd.DataFrame(data["holdings"]))

elif page == "Daily Brief":
    st.subheader("Daily Brief")
    if st.button("Refresh brief"):
        st.session_state["brief"] = call_api("GET", "/report/daily")
    brief = st.session_state.get("brief") or call_api("GET", "/report/daily")
    if brief:
        if brief.get("warnings"):
            for w in brief["warnings"]:
                st.warning(w)
        df = pd.DataFrame(brief["rows"])
        st.dataframe(df)
        if not df.empty:
            ticker = st.selectbox("Ticker drilldown", df["ticker"].tolist())
            st.json(df[df["ticker"] == ticker].iloc[0].to_dict())

elif page == "Log Event":
    st.subheader("Manual Event")
    with st.form("log_event"):
        event_type = st.selectbox("Event Type", ["BUY", "SELL", "DIVIDEND", "DEPOSIT", "WITHDRAW", "FEE", "NOTE"])
        ticker = st.text_input("Ticker")
        qty = st.number_input("Quantity", value=0.0)
        price = st.number_input("Price", value=0.0)
        amount = st.number_input("Amount", value=0.0)
        desc = st.text_input("Description")
        ts = st.text_input("Timestamp ISO8601", value=datetime.utcnow().isoformat() + "Z")
        submit = st.form_submit_button("Save")
    if submit:
        payload = {
            "event_type": event_type,
            "ticker": ticker or None,
            "quantity": qty if qty else None,
            "price": price if price else None,
            "amount": amount if amount else None,
            "event_ts": ts,
            "description": desc or None,
            "source": "manual",
        }
        data = call_api("POST", "/events", json=payload)
        if data:
            st.success("Event logged.")

elif page == "Reminders":
    st.subheader("Due Reminders")
    if st.button("Generate recommendations now"):
        out = call_api("POST", "/recommendations/generate")
        if out:
            st.success(f"Generated {out['count']} recommendations")

    data = call_api("GET", "/reminders")
    if data:
        for r in data["items"]:
            col1, col2 = st.columns([4, 1])
            col1.write(f"#{r['id']} due {r['due_at']} — {r['message']}")
            if col2.button("Mark Acted", key=f"done-{r['id']}"):
                call_api("POST", f"/reminders/{r['id']}/resolve", json={"status": "done"})
                st.rerun()
            if st.button("Ignore", key=f"ignore-{r['id']}"):
                call_api("POST", f"/reminders/{r['id']}/resolve", json={"status": "ignored"})
                st.rerun()
