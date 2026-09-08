import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# 設定要分析的股票清單，可自行增減
ticker_list = ["AAPL", "MSFT", "AMZN", "GOOGL"]
all_earnings_data = []

for ticker in ticker_list:
    print(f"\n===== 正在處理 {ticker} =====")
    stock = yf.Ticker(ticker)

    # 取得財報日期與EPS數據
    earnings = stock.get_earnings_dates()
    if earnings is None or len(earnings) == 0:
        print(f"{ticker} 無法取得財報數據，跳過該股票")
        continue

    # 印出當前欄位名，方便除錯
    print(f"{ticker} 資料欄位：{earnings.columns.tolist()}")

    # ✅ 相容新舊版 yfinance 欄位名稱
    col_eps_actual = "EPSActual" if "EPSActual" in earnings.columns else "EPS Actual"
    col_eps_estimate = "EPSEstimate" if "EPSEstimate" in earnings.columns else "EPS Estimate"

    # 移除空值列
    earnings = earnings.dropna(subset=[col_eps_actual, col_eps_estimate])

    # 取得股價資料，時間範圍對應財報時間
    start_date = earnings.index.min()
    end_date = earnings.index.max()
    price_df = stock.history(start=start_date, end=end_date)

    if len(price_df) == 0:
        print(f"{ticker} 無法取得股價數據，跳過")
        continue

    # 計算盈餘驚喜率 (實際EPS - 預期EPS) / 預期EPS
    earnings["surprise_pct"] = (earnings[col_eps_actual] - earnings[col_eps_estimate]) / earnings[col_eps_estimate]

    earnings["ticker"] = ticker
    all_earnings_data.append(earnings)

# 合併全部股票數據
if len(all_earnings_data) > 0:
    total_df = pd.concat(all_earnings_data)
    print("\n=== 合併完成，前5筆數據 ===")
    print(total_df.head())

    # 畫圖：盈餘驚喜率分布
    plt.figure(figsize=(10, 6))
    for tick in ticker_list:
        sub = total_df[total_df["ticker"] == tick]
        plt.hist(sub["surprise_pct"], alpha=0.5, label=tick, bins=15)

    plt.title("Earnings Surprise Percentage Distribution")
    plt.xlabel("Surprise % (盈餘驚喜率)")
    plt.ylabel("Count")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()

else:
    print("沒有拿到任何有效財報數據")
