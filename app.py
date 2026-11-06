import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="SPYERN FOREX SCALPER", page_icon="📈", layout="wide")

# -------------------- Indicators and strategy --------------------
def add_indicators(df):
    out = df.copy()
    out["ema9"] = out["close"].ewm(span=9, adjust=False).mean()
    out["ema21"] = out["close"].ewm(span=21, adjust=False).mean()
    delta = out["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out["rsi"] = 100 - (100 / (1 + rs))
    out["rsi"] = out["rsi"].fillna(50)
    return out

def signal_at(df, i):
    # Signal uses only completed candles through index i.
    if i < 22:
        return None
    prev = df.iloc[i-1]
    cur = df.iloc[i]
    crossed_up = prev.ema9 <= prev.ema21 and cur.ema9 > cur.ema21
    crossed_down = prev.ema9 >= prev.ema21 and cur.ema9 < cur.ema21
    if crossed_up and 50 <= cur.rsi <= 70:
        return "BUY"
    if crossed_down and 30 <= cur.rsi <= 50:
        return "SELL"
    return None

def make_demo_data(n=600, start=1.0800, seed=7):
    # Synthetic prices for software testing only; NOT live or historical market data.
    rng = np.random.default_rng(seed)
    steps = rng.normal(0, 0.00012, n)
    drift = 0.000002 * np.sin(np.arange(n) / 35)
    close = start + np.cumsum(steps + drift)
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0.00001, 0.00008, n)
    low = np.minimum(open_, close) - rng.uniform(0.00001, 0.00008, n)
    times = [datetime(2025, 1, 1) + timedelta(minutes=i) for i in range(n)]
    return pd.DataFrame({"time": times, "open": open_, "high": high, "low": low, "close": close})

def normalize_data(df):
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("CSV must contain columns: open, high, low, close. Missing: " + ", ".join(missing))
    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=required).reset_index(drop=True)
    if "time" not in df.columns:
        df["time"] = np.arange(len(df))
    if len(df) < 30:
        raise ValueError("Please provide at least 30 valid candles.")
    if (df["high"] < df["low"]).any():
        raise ValueError("Some rows have high lower than low.")
    return df

def run_backtest(df, starting_balance, risk_pct, sl_pips, tp_pips, spread_pips,
                 commission_per_lot, pip_size, max_trades, daily_loss_pct):
    data = add_indicators(df).reset_index(drop=True)
    balance = float(starting_balance)
    peak = balance
    trades, equity_rows = [], []
    position = None
    trades_today = 0
    current_day = None
    halted_day = None
    # Approximate pip value for a standard lot; user can adjust pip size.
    pip_value_per_lot = 10.0
    for i in range(1, len(data)):
        row = data.iloc[i]
        day = str(row["time"])[:10]
        if day != current_day:
            current_day, trades_today, halted_day = day, 0, None

        # Exit check uses this candle's high/low; conservative if both SL and TP hit.
        if position is not None:
            exit_price, reason = None, None
            if position["side"] == "BUY":
                hit_sl = row["low"] <= position["sl"]
                hit_tp = row["high"] >= position["tp"]
                if hit_sl:
                    exit_price, reason = position["sl"], "STOP LOSS"
                elif hit_tp:
                    exit_price, reason = position["tp"], "TAKE PROFIT"
            else:
                hit_sl = row["high"] >= position["sl"]
                hit_tp = row["low"] <= position["tp"]
                if hit_sl:
                    exit_price, reason = position["sl"], "STOP LOSS"
                elif hit_tp:
                    exit_price, reason = position["tp"], "TAKE PROFIT"
            if exit_price is not None:
                direction = 1 if position["side"] == "BUY" else -1
                gross_pips = direction * (exit_price - position["entry"]) / pip_size
                gross = gross_pips * pip_value_per_lot * position["lots"]
                net = gross - position["cost"]
                balance += net
                trades.append({**position, "exit": exit_price, "exit_time": row["time"],
                               "reason": reason, "gross_pips": gross_pips, "net_pnl": net,
                               "balance_after": balance})
                position = None

        # Daily stop uses realized P/L from this day.
        if balance <= 0:
            break
        day_start = next((x["day_start_balance"] for x in trades[::-1] if x["day"] == day), balance)
        if day_start > 0 and (day_start - balance) / day_start >= daily_loss_pct / 100:
            halted_day = day

        if position is None and halted_day != day and trades_today < max_trades:
            sig = signal_at(data, i)
            if sig:
                entry = float(row["close"])
                # Spread and commission are modeled as a cost, not hidden in displayed entry.
                risk_cash = balance * risk_pct / 100
                stop_distance = sl_pips * pip_size
                lots = risk_cash / (sl_pips * pip_value_per_lot)
                lots = max(0.01, min(lots, 5.0))
                cost = spread_pips * pip_value_per_lot * lots + commission_per_lot * lots
                if sig == "BUY":
                    sl, tp = entry - stop_distance, entry + tp_pips * pip_size
                else:
                    sl, tp = entry + stop_distance, entry - tp_pips * pip_size
                position = {"side": sig, "entry": entry, "entry_time": row["time"],
                            "sl": sl, "tp": tp, "lots": lots, "cost": cost,
                            "day": day, "day_start_balance": balance}
                trades_today += 1

        unrealized = 0.0
        if position:
            direction = 1 if position["side"] == "BUY" else -1
            unrealized = direction * (float(row["close"]) - position["entry"]) / pip_size * pip_value_per_lot * position["lots"] - position["cost"]
        equity_rows.append({"time": row["time"], "balance": balance, "equity": balance + unrealized})
    # Close remaining position at final close for a completed backtest.
    if position is not None:
        last = data.iloc[-1]
        direction = 1 if position["side"] == "BUY" else -1
        gross_pips = direction * (float(last["close"]) - position["entry"]) / pip_size
        net = gross_pips * pip_value_per_lot * position["lots"] - position["cost"]
        balance += net
        trades.append({**position, "exit": float(last["close"]), "exit_time": last["time"],
                       "reason": "END OF DATA", "gross_pips": gross_pips,
                       "net_pnl": net, "balance_after": balance})
    return data, pd.DataFrame(trades), pd.DataFrame(equity_rows), balance

# -------------------- Interface --------------------
st.title("📈 SPYERN FOREX SCALPER")
st.caption("Educational software • PAPER TRADING ONLY • No broker connection • No real orders")

with st.sidebar:
    st.header("⚙️ Settings")
    source = st.radio("Price data", ["Synthetic demo data", "Upload my own CSV"])
    uploaded = st.file_uploader("Upload candle CSV", type=["csv"]) if source == "Upload my own CSV" else None
    pair = st.selectbox("Display pair", ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "Other"])
    start_balance = st.number_input("Starting virtual balance ($)", min_value=100.0, value=10000.0, step=500.0)
    risk_pct = st.slider("Risk per trade (%)", 0.1, 2.0, 0.5, 0.1)
    sl_pips = st.number_input("Stop Loss (pips)", min_value=2.0, max_value=100.0, value=10.0, step=1.0)
    tp_pips = st.number_input("Take Profit (pips)", min_value=2.0, max_value=200.0, value=12.0, step=1.0)
    spread_pips = st.number_input("Estimated spread (pips)", min_value=0.0, max_value=10.0, value=1.2, step=0.1)
    commission = st.number_input("Commission per lot ($, round trip)", min_value=0.0, max_value=30.0, value=0.0, step=0.5)
    max_trades = st.number_input("Maximum trades per day", min_value=1, max_value=100, value=10)
    daily_loss = st.slider("Daily loss stop (%)", 0.5, 10.0, 2.0, 0.5)
    pip_size = 0.01 if pair == "USD/JPY" else 0.0001

if source == "Synthetic demo data":
    raw = make_demo_data()
    st.info("Synthetic demo prices are generated for software testing only. They are NOT live forex prices and cannot establish real-world profitability.")
elif uploaded is not None:
    try:
        raw = normalize_data(pd.read_csv(uploaded))
    except Exception as e:
        st.error(str(e))
        st.stop()
else:
    st.warning("Upload a CSV with open, high, low and close columns to continue.")
    st.stop()

try:
    raw = normalize_data(raw)
except Exception as e:
    st.error(str(e))
    st.stop()

st.subheader("1. Market data")
st.write(f"Selected display pair: **{pair}** · Candles loaded: **{len(raw):,}**")
st.caption("CSV timestamps are used if supplied. Data must be chronological and represent completed candles.")
chart_data = add_indicators(raw)
st.line_chart(chart_data.set_index("time")[["close", "ema9", "ema21"]].tail(250), height=280)

st.subheader("2. Strategy")
st.write("BUY: EMA 9 crosses above EMA 21 and RSI is between 50 and 70. SELL: EMA 9 crosses below EMA 21 and RSI is between 30 and 50. Signals are evaluated on completed candles.")
latest = chart_data.iloc[-1]
c1, c2, c3 = st.columns(3)
c1.metric("Latest close", f"{latest.close:.5f}")
c2.metric("EMA 9 / EMA 21", f"{latest.ema9:.5f} / {latest.ema21:.5f}")
c3.metric("RSI 14", f"{latest.rsi:.1f}")

st.subheader("3. Run a backtest")
st.warning("This is a simplified educational backtest. It assumes one open position at a time, estimates pip value as $10 per pip per standard lot, and uses conservative stop-first handling when both SL and TP fall inside one candle. It is not suitable for live trading or proof of future returns.")
if st.button("▶ Run backtest", type="primary"):
    _, trades, equity, ending = run_backtest(
        raw, start_balance, risk_pct, sl_pips, tp_pips, spread_pips,
        commission, pip_size, int(max_trades), daily_loss
    )
    st.session_state["trades"] = trades
    st.session_state["equity"] = equity
    st.session_state["ending"] = ending
    st.session_state["start"] = start_balance

if "trades" in st.session_state:
    trades = st.session_state["trades"]
    equity = st.session_state["equity"]
    ending = st.session_state["ending"]
    pnl = ending - st.session_state["start"]
    wins = int((trades["net_pnl"] > 0).sum()) if not trades.empty else 0
    total = len(trades)
    win_rate = wins / total * 100 if total else 0
    a, b, c, d = st.columns(4)
    a.metric("Ending virtual balance", f"${ending:,.2f}")
    b.metric("Net P/L", f"${pnl:,.2f}", delta=f"{pnl:,.2f}")
    c.metric("Closed trades", str(total))
    d.metric("Win rate", f"{win_rate:.1f}%")
    if not equity.empty:
        st.write("Equity curve")
        st.line_chart(equity.set_index("time")[["equity"]], height=220)
    st.write("Trade history")
    if trades.empty:
        st.info("No trades were generated by this strategy on this dataset.")
    else:
        display_cols = ["side", "entry_time", "entry", "exit_time", "exit", "sl", "tp", "lots", "reason", "gross_pips", "net_pnl"]
        st.dataframe(trades[display_cols], use_container_width=True)
        st.download_button("⬇ Download trade history CSV", trades.to_csv(index=False), "spyern_trade_history.csv", "text/csv")
else:
    st.info("Change settings in the sidebar, then click Run backtest. Results appear here.")

st.subheader("4. What the controls do")
st.markdown("""
- **Price data:** choose clearly labelled synthetic test prices or upload your own historical candle CSV.
- **Risk per trade:** percentage of current virtual balance used to calculate position size.
- **Stop Loss / Take Profit:** exit distances measured in pips.
- **Estimated spread / Commission:** approximate trading costs deducted from results.
- **Maximum trades per day:** limits new entries.
- **Daily loss stop:** prevents new entries after the configured realized daily loss threshold.
- **Run backtest:** evaluates the strategy across the selected dataset; it does not run continuously or connect to a broker.
""")
st.caption("SPYERN FOREX SCALPER • Version 1.0 • PAPER TESTING ONLY")
