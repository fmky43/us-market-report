"""
検証専用スクリプト（本実装ではない）
仕様書4章の「指数」「マクロ」「日本関連」「セクターETF」「個別30銘柄」について、
yfinanceで実際に取得できるかを確認する。

特に NKD=F（シカゴ日経平均先物）と BRK-B（yfinance表記のゆれの可能性）は
詳しめに結果を出力する。
"""

import yfinance as yf

TICKERS = {
    "指数": ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX", "^SOX", "RSP"],
    "マクロ": ["^TNX", "DX-Y.NYB", "USDJPY=X", "CL=F", "GC=F"],
    "日本関連": ["NKD=F", "^N225"],
    "セクターETF": [
        "XLK", "XLF", "XLE", "XLV", "XLY",
        "XLP", "XLI", "XLB", "XLRE", "XLU", "XLC",
    ],
    "個別30銘柄": [
        # メガキャップ
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "NFLX", "ORCL", "CRM",
        # 半導体
        "AVGO", "AMD", "MU", "INTC", "QCOM", "TXN", "ADI", "LRCX", "AMAT", "KLAC",
        "ASML", "TSM", "ARM", "MRVL",
        # その他指標性
        "JPM", "BRK-B", "XOM", "LLY", "WMT", "COST",
    ],
}

# BRK-B は yfinance 上の表記ゆれの可能性が指摘されているため、
# 候補表記を個別に突き合わせて確認する。
BRK_CANDIDATES = ["BRK-B", "BRK.B", "BRK-B.US"]

results = []

for category, tickers in TICKERS.items():
    for symbol in tickers:
        print(f"\n=== [{category}] {symbol} ===")
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="1mo")
            if hist.empty:
                print("  -> 取得結果が空でした（データなし）")
                results.append((category, symbol, "EMPTY"))
                continue

            last_rows = hist.tail(3)[["Close", "Volume"]]
            print(f"  行数: {len(hist)}")
            print(f"  直近3営業日:\n{last_rows}")

            results.append((category, symbol, "OK"))
        except Exception as e:
            print(f"  -> 取得失敗: {type(e).__name__}: {e}")
            results.append((category, symbol, f"FAILED: {e}"))

print("\n\n========== サマリー ==========")
for category, symbol, status in results:
    mark = "OK" if status == "OK" else "NG"
    print(f"[{mark}] {category:10s} {symbol:10s} {status if status != 'OK' else ''}")

ng = [r for r in results if r[2] != "OK"]
print(f"\n合計 {len(results)} 銘柄中、失敗 {len(ng)} 銘柄")

print("\n\n========== BRK-B 表記ゆれの確認 ==========")
for symbol in BRK_CANDIDATES:
    print(f"\n--- {symbol} ---")
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="5d")
        if hist.empty:
            print("  -> 空（この表記では取得不可）")
        else:
            print(f"  -> 取得成功。直近終値: {hist['Close'].tail(1).values}")
    except Exception as e:
        print(f"  -> 取得失敗: {type(e).__name__}: {e}")
