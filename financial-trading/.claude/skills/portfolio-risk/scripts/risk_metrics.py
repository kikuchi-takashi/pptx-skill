#!/usr/bin/env python3
"""ポートフォリオリスク評価スクリプト。

保有ポジションCSV（ticker, quantity, cost_basis）を受け取り、yfinance で価格履歴を
取得して、時価評価・リスク指標・相関行列を算出し、Markdownレポートを出力する。
発注・送信系の機能は一切持たない。あくまで分析・提示のみ。

例:
    python3 risk_metrics.py --positions ./positions.csv --period 1y \
        --out ./output/portfolio_risk_report.md
"""
import argparse
import sys

import numpy as np
import pandas as pd


def fetch_price_history(tickers, period):
    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit(
            "yfinance がインストールされていません。`pip3 install yfinance` を"
            "実行してから再度お試しください。"
        )

    closes = {}
    errors = []
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
            if hist.empty:
                errors.append(f"{ticker}: データが空でした")
                continue
            close = hist["Close"]
            # yfinance は各ティッカーの取引所ローカルタイムゾーンでタイムゾーン付き
            # インデックスを返す（例: 7203.T は Asia/Tokyo、AAPL は America/New_York）。
            # 複数ティッカーを異なるタイムゾーンのまま pd.DataFrame(dict) で結合すると、
            # pandas は「同じ暦日」ではなく「同じUTC時刻」で行を揃えてしまい、日本株と
            # 米国株が別々の行に分かれて時価評価がすべてNaNになる（=直近価格取得失敗の
            # 誤判定で保有銘柄が丸ごと除外される）。タイムゾーン情報を落として現地の
            # 暦日をそのままインデックスにすることで、各市場の「その日の終値」同士を
            # 正しく同じ行に揃える。
            if close.index.tz is not None:
                close.index = close.index.tz_localize(None)
            close.index = close.index.normalize()
            closes[ticker] = close
        except Exception as e:
            errors.append(f"{ticker}: 取得失敗 ({e})")
    return pd.DataFrame(closes), errors


def compute_metrics(positions, price_df):
    last_prices = price_df.iloc[-1]
    positions = positions.copy()
    positions["last_price"] = positions["ticker"].map(last_prices)

    # 価格取得に失敗した銘柄（price_df に列が存在しない、または直近値がNaN）は
    # 時価評価・リスク計算から除外し、その旨をエラーとして報告する。除外せず
    # NaNのまま計算すると、レポート上に「時価評価額: nan」のような数値が
    # 紛れ込み、桁違いチェック等が事実上不可能になる。
    missing_price_mask = positions["last_price"].isna()
    dropped_tickers = positions.loc[missing_price_mask, "ticker"].tolist()
    positions = positions.loc[~missing_price_mask].copy()
    if positions.empty:
        raise SystemExit(
            "保有銘柄すべてで直近価格を取得できず、リスク指標を算出できませんでした。"
            f"（対象: {dropped_tickers}）"
        )

    positions["market_value"] = positions["quantity"] * positions["last_price"]
    positions["unrealized_pl"] = (positions["last_price"] - positions["cost_basis"]) * positions["quantity"]

    total_value = positions["market_value"].sum()
    positions["weight"] = positions["market_value"] / total_value if total_value else 0

    hhi = (positions["weight"] ** 2).sum()

    daily_ret = price_df.pct_change(fill_method=None).dropna(how="all")
    weights = positions.set_index("ticker")["weight"].reindex(price_df.columns).fillna(0)
    port_ret = (daily_ret * weights).sum(axis=1)

    ann_vol = port_ret.std() * np.sqrt(252)
    var95 = port_ret.quantile(0.05) * total_value
    cum = (1 + port_ret).cumprod()
    max_dd = (cum / cum.cummax() - 1).min()
    ann_ret = port_ret.mean() * 252
    sharpe = ann_ret / ann_vol if ann_vol else float("nan")
    corr = daily_ret.corr()

    return {
        "positions": positions,
        "dropped_tickers": dropped_tickers,
        "total_value": total_value,
        "hhi": hhi,
        "ann_vol": ann_vol,
        "var95": var95,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "corr": corr,
    }


def render_report(metrics, errors):
    p = metrics["positions"]
    lines = [
        "# ポートフォリオリスク評価レポート",
        "",
        "> 本レポートの指標・リバランス案は情報提供のみを目的とした分析結果であり、"
        "投資助言ではありません。投資判断は自己責任で行ってください。",
        "",
        "## 保有ポジション",
        "",
        "| 銘柄 | 数量 | 取得単価 | 直近単価 | 時価評価額 | 含み損益 | 構成比 |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, r in p.iterrows():
        lines.append(
            f"| {r['ticker']} | {r['quantity']:g} | {r['cost_basis']:.2f} | "
            f"{r['last_price']:.2f} | {r['market_value']:.0f} | {r['unrealized_pl']:+.0f} | "
            f"{r['weight']*100:.1f}% |"
        )
    lines += [
        "",
        f"合計時価評価額: {metrics['total_value']:.0f}",
        "",
        "## リスク指標",
        "",
        f"- HHI（銘柄集中度）: {metrics['hhi']:.3f}"
        + ("（集中度が高め。上位銘柄への依存が大きい）" if metrics["hhi"] > 0.25 else "（分散は取れている）"),
        f"- 年率ボラティリティ: {metrics['ann_vol']*100:.1f}%",
        f"- 歴史的VaR(95%, 1日): {metrics['var95']:.0f}"
        "（マイナスは評価損方向。過去データ上、悪い方から5%の日に想定される評価損の目安）",
        f"- 最大ドローダウン: {metrics['max_dd']*100:.1f}%",
        f"- シャープレシオ（簡易, 無リスク金利0%仮定）: {metrics['sharpe']:.2f}",
        "",
        "## 銘柄間相関",
        "",
        metrics["corr"].round(2).to_markdown(),
        "",
    ]
    all_notes = list(errors)
    if metrics.get("dropped_tickers"):
        all_notes.append(
            "以下の銘柄は直近価格を取得できなかったため、時価評価・リスク指標の"
            f"計算から除外しました: {', '.join(metrics['dropped_tickers'])}"
        )
    if all_notes:
        lines.append("## データ取得上の注意")
        lines.extend(f"- {e}" for e in all_notes)
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="保有ポジションのリスク指標を算出する")
    parser.add_argument("--positions", required=True, help="ticker,quantity,cost_basis のCSV")
    parser.add_argument("--period", default="1y", help="価格履歴の取得期間")
    parser.add_argument("--out", required=True, help="出力Markdownレポートのパス")
    args = parser.parse_args()

    positions = pd.read_csv(args.positions)
    required_cols = {"ticker", "quantity", "cost_basis"}
    if not required_cols.issubset(positions.columns):
        print(f"[エラー] CSVに必須列が不足しています: {required_cols - set(positions.columns)}", file=sys.stderr)
        raise SystemExit("入力内容がリスク評価として成立しないため、処理を中止しました。")
    if positions.empty:
        print("[エラー] 保有ポジションCSVに行がありません（ヘッダーのみ）。", file=sys.stderr)
        raise SystemExit("入力内容がリスク評価として成立しないため、処理を中止しました。")

    positions["quantity"] = pd.to_numeric(positions["quantity"], errors="coerce")
    positions["cost_basis"] = pd.to_numeric(positions["cost_basis"], errors="coerce")
    invalid = positions[
        positions["quantity"].isna() | positions["cost_basis"].isna() | (positions["quantity"] <= 0)
    ]
    if not invalid.empty:
        print(
            "[エラー] quantity/cost_basis が数値でない、またはquantityが0以下の行があります: "
            f"{invalid['ticker'].tolist()}",
            file=sys.stderr,
        )
        raise SystemExit(
            "入力内容がリスク評価として成立しないため、処理を中止しました。"
            "上記のエラーを修正して再実行してください。"
        )
    dup_tickers = positions["ticker"][positions["ticker"].duplicated()].unique().tolist()
    if dup_tickers:
        print(
            f"[エラー] 同一銘柄が複数行にわたって重複しています（合算してから再実行してください）: {dup_tickers}",
            file=sys.stderr,
        )
        raise SystemExit(
            "入力内容がリスク評価として成立しないため、処理を中止しました。"
            "上記のエラーを修正して再実行してください。"
        )

    price_df, errors = fetch_price_history(positions["ticker"].tolist(), args.period)
    if price_df.empty:
        raise SystemExit("価格データを取得できませんでした。処理を中断します。")

    metrics = compute_metrics(positions, price_df)
    report = render_report(metrics, errors)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"saved: {args.out}")


if __name__ == "__main__":
    main()
