import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# Parameters
tickers = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]
window_before = 5
window_after = 10

all_records = []

for ticker in tickers:
    stock = yf.Ticker(ticker)
    earnings = stock.earnings_dates
    if earnings is None or len(earnings) == 0:
        continue

    price = yf.download(ticker, period="5y")["Close"]
    earnings = earnings.dropna(subset=["EPS Actual", "EPS Estimate"])
    earnings["surprise_pct"] = (earnings["EPS Actual"] - earnings["EPS Estimate"]) / earnings["EPS Estimate"]

    for idx, row in earnings.iterrows():
        earn_date = idx
        start = earn_date - pd.Timedelta(days=window_before + 5)
        end = earn_date + pd.Timedelta(days=window_after + 5)
        sub_price = price.loc[start:end]
        if len(sub_price) < window_before + window_after:
            continue

        sub_price = sub_price.reset_index()
        earn_pos = (sub_price["Date"] - earn_date).abs().idxmin()
        if earn_pos - window_before < 0 or earn_pos + window_after >= len(sub_price):
            continue

        base_price = sub_price.iloc[earn_pos - window_before]["Close"]
        ret_series = sub_price.loc[earn_pos - window_before: earn_pos + window_after]["Close"] / base_price - 1

        record = {
            "ticker": ticker,
            "surprise_pct": row["surprise_pct"],
            "ret_series": ret_series.values
        }
        all_records.append(record)

df_records = pd.DataFrame(all_records)

# 分組 beat / miss / in‑line
def group_surprise(x):
    if x > 0.05:
        return "beat"
    elif x < -0.05:
        return "miss"
    else:
        return "in_line"

df_records["group"] = df_records["surprise_pct"].apply(group_surprise)

# plot graph
plt.figure(figsize=(10, 6))
for g in ["beat", "miss", "in_line"]:
    subset = df_records[df_records["group"] == g]
    if len(subset) == 0:
        continue
    arr = list(subset["ret_series"])
    avg = pd.DataFrame(arr).mean(axis=0)
    plt.plot(avg.values, label=g)

plt.legend()
plt.title("Cumulative return around earnings announcement")
plt.xlabel("trading days relative to earnings date")
plt.ylabel("cumulative return")
plt.tight_layout()
plt.savefig("earnings_return_chart.png")
plt.show()
