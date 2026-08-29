"""
米国市場モーニングレポート: データ取得スクリプト（ステップ2）

仕様書 4章のうち「指数」「マクロ」「日本関連」「セクターETF」を取得する。
個別30銘柄・ニュース・経済指標カレンダーは対象外（次のステップで追加）。

出力:
  data/latest.json       ... 常に最新を上書き
  data/YYYY-MM-DD.json   ... 取得した営業日ごとの履歴（上書きしない）

方針（厳守事項に基づく）:
  - 取得に失敗したティッカーは黙って除外せず、status: "failed" として記録する
  - 前日値・推定値での穴埋めは行わない（仕様書8章で禁止されている）
  - 出来高の概念がない銘柄（VIX/SOX/TNX/ドル指数/ドル円）は
    volume系フィールドをnullにする（出来高0という虚偽の値にしない）
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yfinance as yf

JST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TICKERS = {
    "indices": [
        {"symbol": "^GSPC", "name": "S&P500"},
        {"symbol": "^IXIC", "name": "NASDAQ総合"},
        {"symbol": "^DJI", "name": "NYダウ"},
        {"symbol": "^RUT", "name": "ラッセル2000"},
        {"symbol": "^VIX", "name": "VIX"},
        {"symbol": "^SOX", "name": "SOX指数(半導体)"},
        {"symbol": "RSP", "name": "S&P500等ウェイトETF"},
    ],
    "macro": [
        {"symbol": "^TNX", "name": "米10年債利回り"},
        {"symbol": "DX-Y.NYB", "name": "ドル指数"},
        {"symbol": "USDJPY=X", "name": "ドル円"},
        {"symbol": "CL=F", "name": "WTI原油"},
        {"symbol": "GC=F", "name": "金"},
    ],
    "japan": [
        {"symbol": "NKD=F", "name": "シカゴ日経平均先物"},
        {"symbol": "^N225", "name": "日経平均(前営業日終値)"},
    ],
    "sector_etf": [
        {"symbol": "XLK", "name": "情報技術"},
        {"symbol": "XLF", "name": "金融"},
        {"symbol": "XLE", "name": "エネルギー"},
        {"symbol": "XLV", "name": "ヘルスケア"},
        {"symbol": "XLY", "name": "一般消費財"},
        {"symbol": "XLP", "name": "生活必需品"},
        {"symbol": "XLI", "name": "資本財"},
        {"symbol": "XLB", "name": "素材"},
        {"symbol": "XLRE", "name": "不動産"},
        {"symbol": "XLU", "name": "公益"},
        {"symbol": "XLC", "name": "通信サービス"},
    ],
}

# 出来高の概念がない(=Yahoo上で常に0が返る)銘柄。volume系フィールドはnullにする。
# ^RUT はYahoo上で^GSPCの出来高をそのまま返す不具合(検証済み: 直近64営業日中63日が完全一致)が
# あるため、実際の出来高データを持たない銘柄として同グループに含める。
NO_VOLUME_SYMBOLS = {"^VIX", "^SOX", "^TNX", "DX-Y.NYB", "USDJPY=X", "^RUT"}


def fetch_one(symbol: str, name: str) -> dict:
    try:
        hist = yf.Ticker(symbol).history(period="2mo")
    except Exception as e:
        return {
            "symbol": symbol,
            "name": name,
            "status": "failed",
            "error": f"{type(e).__name__}: {e}",
        }

    if hist.empty or len(hist) < 2:
        return {
            "symbol": symbol,
            "name": name,
            "status": "failed",
            "error": "取得結果が空、または前日比計算に必要な行数がない",
        }

    last = hist.iloc[-1]
    prev = hist.iloc[-2]
    close = float(last["Close"])
    prev_close = float(prev["Close"])
    change = close - prev_close
    change_pct = (change / prev_close * 100) if prev_close else None
    date = hist.index[-1].strftime("%Y-%m-%d")

    if symbol in NO_VOLUME_SYMBOLS:
        volume = None
        volume_20d_avg = None
        volume_vs_20d_avg_pct = None
    else:
        volume = int(last["Volume"])
        window = hist["Volume"].tail(20)
        volume_20d_avg = float(window.mean()) if len(window) > 0 else None
        volume_vs_20d_avg_pct = (
            (volume / volume_20d_avg * 100) if volume_20d_avg else None
        )

    return {
        "symbol": symbol,
        "name": name,
        "status": "ok",
        "date": date,
        "close": round(close, 4),
        "prev_close": round(prev_close, 4),
        "change": round(change, 4),
        "change_pct": round(change_pct, 4) if change_pct is not None else None,
        "volume": volume,
        "volume_20d_avg": round(volume_20d_avg, 2) if volume_20d_avg is not None else None,
        "volume_vs_20d_avg_pct": (
            round(volume_vs_20d_avg_pct, 2) if volume_vs_20d_avg_pct is not None else None
        ),
    }


def main() -> None:
    now_utc = datetime.now(timezone.utc)
    now_jst = now_utc.astimezone(JST)

    data = {}
    failed_tickers = []
    ok_count = 0
    total_count = 0

    for category, tickers in TICKERS.items():
        data[category] = []
        for t in tickers:
            result = fetch_one(t["symbol"], t["name"])
            data[category].append(result)
            total_count += 1
            if result["status"] == "ok":
                ok_count += 1
            else:
                failed_tickers.append({"symbol": t["symbol"], "name": t["name"], "error": result.get("error")})

    if ok_count == 0:
        overall_status = "failed"
    elif failed_tickers:
        overall_status = "partial"
    else:
        overall_status = "ok"

    # market_date: ^GSPC (S&P500) の取得日を採用。失敗していれば最初に成功した銘柄の日付、
    # それも無ければ実行日(UTC)を使う。
    market_date = None
    gspc = next((x for x in data["indices"] if x["symbol"] == "^GSPC"), None)
    if gspc and gspc["status"] == "ok":
        market_date = gspc["date"]
    else:
        for cat in data.values():
            for item in cat:
                if item["status"] == "ok":
                    market_date = item["date"]
                    break
            if market_date:
                break
    if market_date is None:
        market_date = now_utc.strftime("%Y-%m-%d")

    output = {
        "generated_at_utc": now_utc.isoformat(),
        "generated_at_jst": now_jst.isoformat(),
        "market_date": market_date,
        "overall_status": overall_status,
        "summary": f"{total_count}銘柄中 {ok_count}件取得成功 / {len(failed_tickers)}件失敗",
        "failed_tickers": failed_tickers,
        "data": data,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = DATA_DIR / "latest.json"
    dated_path = DATA_DIR / f"{market_date}.json"

    json_text = json.dumps(output, ensure_ascii=False, indent=2)
    latest_path.write_text(json_text, encoding="utf-8")
    dated_path.write_text(json_text, encoding="utf-8")

    print(f"overall_status = {overall_status}")
    print(output["summary"])
    if failed_tickers:
        print("失敗ティッカー:")
        for f in failed_tickers:
            print(f"  - {f['symbol']} ({f['name']}): {f['error']}")
    print(f"書き出し先: {latest_path}")
    print(f"書き出し先: {dated_path}")


if __name__ == "__main__":
    main()
