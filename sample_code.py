"""Earnings surprise analysis for US equities.

For each ticker we pull historical earnings dates, compute the EPS surprise
relative to the analyst estimate, then measure the cumulative price reaction in
a window around the announcement.

Two charts are produced:
  * earnings_return_chart.png          - average cumulative return by surprise group
  * earnings_surprise_distribution.png - distribution of surprise % per ticker
"""

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt

# Parameters
TICKERS = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]
WINDOW_BEFORE = 5
WINDOW_AFTER = 10
HISTORY_PERIOD = "5y"
EARNINGS_LIMIT = 40
BEAT_THRESHOLD = 0.05

# yfinance has renamed these columns across releases, so probe for each in turn.
ACTUAL_COLUMNS = ("Reported EPS", "EPS Actual", "EPSActual", "epsActual")
ESTIMATE_COLUMNS = ("EPS Estimate", "EPSEstimate", "epsEstimate")

# Earnings released at or after this hour land on the *next* trading session.
MARKET_CLOSE_HOUR = 16


def pick_column(columns, candidates):
    for name in candidates:
        if name in columns:
            return name
    return None


def drop_timezone(index):
    """Return a tz-naive index keeping the exchange-local wall clock."""
    return index.tz_localize(None) if index.tz is not None else index


def load_earnings(stock, ticker):
    """Earnings history with a `surprise_pct` column, or None if unusable."""
    earnings = stock.get_earnings_dates(limit=EARNINGS_LIMIT)
    if earnings is None or len(earnings) == 0:
        print(f"{ticker}: no earnings data returned, skipping")
        return None

    col_actual = pick_column(earnings.columns, ACTUAL_COLUMNS)
    col_estimate = pick_column(earnings.columns, ESTIMATE_COLUMNS)
    if col_actual is None or col_estimate is None:
        print(f"{ticker}: unexpected columns {list(earnings.columns)}, skipping")
        return None

    earnings = earnings.dropna(subset=[col_actual, col_estimate]).copy()
    earnings.index = drop_timezone(earnings.index)

    # A zero estimate makes the surprise ratio meaningless (division by zero).
    estimate = earnings[col_estimate]
    earnings = earnings[estimate != 0]
    if len(earnings) == 0:
        print(f"{ticker}: no reported earnings with a usable estimate, skipping")
        return None

    # Dividing by the absolute estimate keeps the sign meaningful when analysts
    # forecast a loss: beating -0.10 with -0.05 has to read as a positive surprise.
    earnings["surprise_pct"] = (
        earnings[col_actual] - earnings[col_estimate]
    ) / earnings[col_estimate].abs()
    earnings["ticker"] = ticker
    return earnings


def load_close_prices(ticker):
    """Adjusted close as a tz-naive Series, or None if unavailable."""
    prices = yf.download(
        ticker, period=HISTORY_PERIOD, auto_adjust=True, progress=False
    )
    if prices is None or len(prices) == 0:
        print(f"{ticker}: no price data returned, skipping")
        return None

    close = prices["Close"]
    # yf.download returns MultiIndex columns (Price, Ticker), so ["Close"] is a
    # one-column frame rather than a Series.
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    close.index = drop_timezone(close.index)
    return close.dropna()


def first_reacting_session(sessions, announced_at):
    """Index of the first session whose close reflects the announcement."""
    announced_day = announced_at.normalize()
    pos = sessions.searchsorted(announced_day, side="left")
    after_close = announced_at.hour >= MARKET_CLOSE_HOUR
    if pos < len(sessions) and sessions[pos] == announced_day and after_close:
        pos += 1
    return pos


def group_surprise(x):
    if x > BEAT_THRESHOLD:
        return "beat"
    if x < -BEAT_THRESHOLD:
        return "miss"
    return "in_line"


def collect_events():
    records = []
    surprises = []

    for ticker in TICKERS:
        print(f"\n===== {ticker} =====")
        stock = yf.Ticker(ticker)

        earnings = load_earnings(stock, ticker)
        if earnings is None:
            continue
        surprises.append(earnings[["ticker", "surprise_pct"]])

        close = load_close_prices(ticker)
        if close is None:
            continue

        sessions = close.index
        matched = 0
        for announced_at, row in earnings.iterrows():
            pos = first_reacting_session(sessions, announced_at)
            if pos - WINDOW_BEFORE < 0 or pos + WINDOW_AFTER >= len(sessions):
                continue

            window = close.iloc[pos - WINDOW_BEFORE : pos + WINDOW_AFTER + 1]
            base_price = window.iloc[0]
            if not np.isfinite(base_price) or base_price == 0:
                continue

            records.append(
                {
                    "ticker": ticker,
                    "surprise_pct": row["surprise_pct"],
                    "ret_series": (window / base_price - 1).to_numpy(),
                }
            )
            matched += 1

        print(f"{ticker}: {matched} of {len(earnings)} earnings events inside the price window")

    return records, surprises


def plot_event_study(df_records):
    offsets = np.arange(-WINDOW_BEFORE, WINDOW_AFTER + 1)

    plt.figure(figsize=(10, 6))
    for group in ["beat", "miss", "in_line"]:
        subset = df_records[df_records["group"] == group]
        if len(subset) == 0:
            continue
        avg = np.vstack(subset["ret_series"].to_numpy()).mean(axis=0)
        plt.plot(offsets, avg, label=f"{group} (n={len(subset)})")

    plt.axvline(0, color="grey", linewidth=0.8, linestyle="--")
    plt.axhline(0, color="grey", linewidth=0.8)
    plt.legend()
    plt.title("Cumulative return around earnings announcement")
    plt.xlabel("Trading days relative to first session after earnings")
    plt.ylabel(f"Cumulative return vs day {-WINDOW_BEFORE}")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig("earnings_return_chart.png", dpi=150)
    print("\nSaved earnings_return_chart.png")


def plot_surprise_distribution(surprise_df):
    values = surprise_df["surprise_pct"]

    # Quarters where analysts forecast near-zero EPS produce surprises of several
    # hundred percent. Clipping to the central mass keeps the bulk readable, and
    # shared bins make the per-ticker histograms comparable.
    low, high = values.quantile([0.02, 0.98])
    limit = max(abs(low), abs(high))
    bins = np.linspace(-limit, limit, 31)
    clipped_count = int((values.abs() > limit).sum())

    plt.figure(figsize=(10, 6))
    for ticker in TICKERS:
        sub = surprise_df[surprise_df["ticker"] == ticker]
        if len(sub) == 0:
            continue
        plt.hist(
            sub["surprise_pct"].clip(-limit, limit),
            bins=bins,
            histtype="step",
            linewidth=1.8,
            label=f"{ticker} (n={len(sub)})",
        )

    plt.axvline(0, color="grey", linewidth=0.8, linestyle="--")
    plt.title("Earnings Surprise Percentage Distribution")
    plt.xlabel(
        "Surprise ((actual - estimate) / |estimate|)"
        f"  -  {clipped_count} outliers clipped to +/-{limit:.0%}"
    )
    plt.ylabel("Count")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig("earnings_surprise_distribution.png", dpi=150)
    print("Saved earnings_surprise_distribution.png")


def main():
    records, surprises = collect_events()

    if not records:
        print("\nNo usable earnings events found.")
        return

    df_records = pd.DataFrame(records)
    df_records["group"] = df_records["surprise_pct"].apply(group_surprise)

    print("\n=== Events per group ===")
    print(df_records["group"].value_counts())

    plot_event_study(df_records)
    plot_surprise_distribution(pd.concat(surprises))

    plt.show()


if __name__ == "__main__":
    main()

