# SPYERN FOREX SCALPER — Paper Trading Starter

## What this is
A beginner-friendly Streamlit app for testing an EMA 9 / EMA 21 + RSI 14 strategy against synthetic demo candles or a user-uploaded historical OHLC CSV.

**It is not connected to Exness or any broker. It cannot place real orders.**
Synthetic demo prices are not live prices and results on them do not demonstrate profitability.

## Windows setup
1. Install Python 3.11 or 3.12 from https://www.python.org/downloads/ and select "Add Python to PATH".
2. Extract this ZIP to a folder, e.g. `SpyernForexBot`.
3. Open that folder in VS Code.
4. Open Terminal > New Terminal.
5. Run:
   `python -m venv .venv`
6. Activate:
   PowerShell: `.venv\Scripts\Activate.ps1`
   If PowerShell blocks activation, use Command Prompt terminal and run:
   `.venv\Scripts\activate.bat`
7. Install:
   `python -m pip install -r requirements.txt`
8. Start:
   `python -m streamlit run app.py`
9. Open the local address printed by Streamlit, usually http://localhost:8501.

## How to use
- Choose Synthetic demo data to confirm the app works. This is generated test data, not real forex prices.
- For historical testing, choose Upload my own CSV and upload candles with columns `open, high, low, close`. Optional `time` column is supported.
- Set pair, starting virtual balance, risk, stop loss, take profit, spread, commission, max trades/day and daily loss stop.
- Click Run backtest.
- Review ending virtual balance, net P/L, trade history and equity curve.
- Download trade history with the download button.

## Important limitations
- Simplified educational backtest, one position at a time.
- Approximate pip value of $10 per pip per standard lot; this is not correct for every pair/account currency.
- Uses candle high/low and assumes stop loss first if both stop and target are touched in one candle.
- Does not model swap, variable spreads, market gaps, latency, partial fills, margin, leverage, broker rules, or all execution details.
- CSV should be chronological and contain completed candles. Ensure the data is genuine and correctly formatted.
- Do not use these results to decide to risk real money.
