#!/usr/bin/env python3
"""市場データ取得スクリプト。

yfinance を用いてティッカーの価格データ（OHLCV）を取得し、CSV に保存する。
データ取得のみを行い、発注・送信系の機能は一切持たない。

例:
    python3 fetch_data.py --tickers 7203.T,AAPL --period 6mo --interval 1d \
        --out ./output/market_data.csv
"""
import argparse
import os
import sys

import pandas as pd


def fetch_prices(tickers, period, interval):
    """yfinance からティッカーごとの OHLCV を取得して縦持ちの DataFrame にする。

    別のデータソース（証券会社の相場配信API等）に差し替える場合はこの関数だけを
    書き換えればよい。戻り値の列は最低限 [date, ticker, open, high, low, close, volume]
    を満たすこと（後段の make_report.py がこの形式に依存する）。

    戻り値は (DataFrame, errors) のタプル。errors はティッカー単位の取得失敗
    （データが空・例外）のメッセージ一覧で、CSVには残らないため呼び出し側
    （main）でサイドカーファイルに書き出し、make_report.py に引き継ぐ。
    """
    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit(
            "yfinance がインストールされていません。`pip3 install yfinance` を"
            "実行してから再度お試しください。"
        )

    frames = []
    errors = []
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
            if hist.empty:
                errors.append(f"{ticker}: データが空でした（ティッカー誤りの可能性）")
                continue
            hist = hist.reset_index()
            date_col = "Date" if "Date" in hist.columns else hist.columns[0]
            df = pd.DataFrame({
                "date": hist[date_col],
                "ticker": ticker,
                "open": hist["Open"],
                "high": hist["High"],
                "low": hist["Low"],
                "close": hist["Close"],
                "volume": hist["Volume"],
            })
            frames.append(df)
        except Exception as e:
            errors.append(f"{ticker}: 取得失敗 ({e})")

    for e in errors:
        print(f"[WARN] {e}", file=sys.stderr)

    if not frames:
        raise SystemExit("すべてのティッカーで取得に失敗しました。処理を中断します。")

    return pd.concat(frames, ignore_index=True), errors


def main():
    parser = argparse.ArgumentParser(description="市場データ（OHLCV）を取得してCSVに保存する")
    parser.add_argument("--tickers", required=True, help="カンマ区切りのティッカー一覧（例: 7203.T,AAPL）")
    parser.add_argument("--period", default="6mo", help="取得期間（例: 1mo, 6mo, 1y, 5y）")
    parser.add_argument("--interval", default="1d", help="足種（例: 1d, 1wk, 1mo）")
    parser.add_argument("--out", required=True, help="出力CSVパス")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    df, errors = fetch_prices(tickers, args.period, args.interval)
    df.to_csv(args.out, index=False)
    print(f"saved: {args.out} ({len(df)} rows, {df['ticker'].nunique()} tickers)")

    # ティッカーごとの取得失敗（データが空・例外）はこの時点のCSVには一切残らない
    # （そもそも行が存在しない）ため、握り潰さず後段の make_report.py に引き継げる
    # よう、同名のサイドカーファイルに書き出す。make_report.py はこれを読み込んで
    # レポート本文の「データ取得上の注意」に合流させる（SKILL.md Step4の
    # 「取得エラーがレポート本文に明記されているか」を満たすための橋渡し）。
    errors_path = args.out + ".errors.txt"
    if errors:
        with open(errors_path, "w", encoding="utf-8") as f:
            f.write("\n".join(errors) + "\n")
    elif os.path.exists(errors_path):
        # 前回失敗分の古いエラーファイルが残っていると誤って引き継がれるため削除する
        os.remove(errors_path)


if __name__ == "__main__":
    main()
