#!/usr/bin/env python3
"""取引候補スキャン・スクリプト。

ウォッチリストCSV（ticker列）と/または保有ポジションCSV（`portfolio-risk` と同じ
ticker,quantity,cost_basis 形式）を受け取り、銘柄ごとにテクニカル・出来高/ボラティリティ・
ファンダメンタルの3種のシグナルを判定して、Markdownの候補レポートを出力する。

本スキルはユーザーが都度呼び出したときにだけ動く。定期実行・自動発注の仕組みは一切
含まない。発注・自動売買は一切行わない（候補提示のみ）。

例:
    python3 scan.py --watchlist ./watchlist.csv --positions ./positions.csv \
        --period 6mo --out ./output/market_scan_report.md
"""
import argparse
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# --- 閾値の既定値（レポート冒頭にも明記する） -------------------------------
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
MA_CROSS_LOOKBACK_DAYS = 3       # 直近何日以内のゴールデン/デッドクロスを検知するか
VOLUME_SPIKE_RATIO = 2.0         # 直近出来高が20日平均の何倍で「急増」とみなすか
VOLUME_BASELINE_WINDOW = 20
VOL_SPIKE_RATIO = 1.5            # 短期ボラティリティが長期の何倍で「急上昇」とみなすか
VOL_SHORT_WINDOW = 5
VOL_LONG_WINDOW = 60
EARNINGS_SOON_DAYS = 14          # 決算発表まで何日以内を「近い」とみなすか


def _read_ticker_csv(path, label):
    """CSVを読み込んで DataFrame を返す。ファイル不在・空ファイル・パース不能などの
    入力エラーはここで捕まえ、生のスタックトレースではなく分かりやすいメッセージで
    処理を中止する。
    """
    try:
        return pd.read_csv(path)
    except FileNotFoundError:
        print(f"[エラー] {label}CSVが見つかりません: {path}", file=sys.stderr)
        raise SystemExit("入力ファイルが存在しないため、処理を中止しました。")
    except pd.errors.EmptyDataError:
        print(f"[エラー] {label}CSVが空です（ヘッダー行もありません）: {path}", file=sys.stderr)
        raise SystemExit("入力内容がスキャン対象として成立しないため、処理を中止しました。")
    except pd.errors.ParserError as e:
        print(f"[エラー] {label}CSVの形式を読み取れませんでした: {path}（{e}）", file=sys.stderr)
        raise SystemExit("入力内容がスキャン対象として成立しないため、処理を中止しました。")


def read_watchlist(path):
    """ウォッチリストCSV（ticker列必須）を読み込み、ティッカーのリストを返す。

    yfinanceのティッカー表記は大文字が慣例（`AAPL`, `7203.T`, `BTC-USD` 等）のため、
    大文字小文字だけが異なる表記（`aapl` と `AAPL` 等）を同一銘柄として扱えるよう
    大文字に正規化する（正規化しないと同一銘柄が別ティッカーとして二重に取得・
    二重にレポートへ表示されてしまう）。
    """
    df = _read_ticker_csv(path, "ウォッチリスト")
    if "ticker" not in df.columns:
        print(f"[エラー] ウォッチリストCSVに ticker 列がありません: {path}", file=sys.stderr)
        raise SystemExit("入力内容がスキャン対象として成立しないため、処理を中止しました。")
    tickers = [str(t).strip().upper() for t in df["ticker"] if str(t).strip() and str(t).strip().lower() != "nan"]
    return tickers


def read_portfolio_tickers(path):
    """保有ポジションCSV（`portfolio-risk` と同じ ticker,quantity,cost_basis 形式）から
    ティッカーのリストを取り出す。本スキルはこのCSVの数量・取得単価は使わず、対象
    銘柄の抽出だけに用いる（詳細なリスク評価は `portfolio-risk` スキールの領分）。

    ウォッチリストと同様、大文字小文字の表記ゆれを同一銘柄として扱うため大文字に
    正規化する（`read_watchlist` と同じ理由）。
    """
    df = _read_ticker_csv(path, "保有ポジション")
    if "ticker" not in df.columns:
        print(f"[エラー] 保有ポジションCSVに ticker 列がありません: {path}", file=sys.stderr)
        raise SystemExit("入力内容がスキャン対象として成立しないため、処理を中止しました。")
    tickers = [str(t).strip().upper() for t in df["ticker"] if str(t).strip() and str(t).strip().lower() != "nan"]
    return tickers


def build_universe(watchlist_path, positions_path):
    """ウォッチリスト・保有ポジションの両方からスキャン対象ティッカーを集約する。

    戻り値は {ticker: {"watchlist", "portfolio"} のいずれかまたは両方を含む set} の辞書
    （順序はウォッチリスト→保有の順で初出順を保つ）。
    """
    universe = {}
    if watchlist_path:
        for t in read_watchlist(watchlist_path):
            universe.setdefault(t, set()).add("watchlist")
    if positions_path:
        for t in read_portfolio_tickers(positions_path):
            universe.setdefault(t, set()).add("portfolio")
    return universe


def fetch_history(ticker, period):
    """yfinance からOHLCV履歴を取得する。

    market-data-report/portfolio-risk と同様、本スキル独自にこの取得関数を持つ。
    3スキルとも同じ yfinance の考え方に沿っているが、必要とするデータの形
    （出来高込みの単一銘柄OHLCVをそのまま扱いたい）が微妙に異なるため、無理な
    共通化はせず独立実装にしている（`portfolio-risk/SKILL.md` が明記している方針と同じ）。
    """
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
    if hist.empty:
        raise ValueError("データが空でした（ティッカー誤りの可能性）")
    hist = hist.reset_index()
    date_col = "Date" if "Date" in hist.columns else hist.columns[0]
    df = pd.DataFrame({
        "date": hist[date_col],
        "close": hist["Close"],
        "high": hist["High"],
        "low": hist["Low"],
        "volume": hist["Volume"],
    }).sort_values("date").reset_index(drop=True)
    return df


def compute_technical_signals(df):
    """移動平均クロス・RSI過熱・ボリンジャーブレイクを判定する。

    RSI・ボリンジャーバンドの計算式は `make_report.py` の `compute_indicators()` と
    同じ考え方（SMA20±2σ、14日RSI）。実装方針の詳細・非共通化の理由は
    `references/SIGNALS.md` を参照。
    """
    signals = []
    d = df.copy()
    d["sma25"] = d["close"].rolling(25).mean()
    d["sma75"] = d["close"].rolling(75).mean()
    d["sma20"] = d["close"].rolling(20).mean()
    std20 = d["close"].rolling(20).std()
    d["bb_upper"] = d["sma20"] + 2 * std20
    d["bb_lower"] = d["sma20"] - 2 * std20

    delta = d["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    d["rsi14"] = 100 - (100 / (1 + rs))
    zero_loss_with_gain = (loss == 0) & (gain > 0) & d["close"].rolling(14).count().ge(14)
    d.loc[zero_loss_with_gain, "rsi14"] = 100.0

    last = d.iloc[-1]

    # --- 移動平均クロス（直近 MA_CROSS_LOOKBACK_DAYS 日以内のサインの反転を検知） ---
    diff = (d["sma25"] - d["sma75"]).dropna()
    if len(diff) >= 2:
        recent = diff.iloc[-(MA_CROSS_LOOKBACK_DAYS + 1):]
        signs = np.sign(recent)
        if len(signs) >= 2 and signs.iloc[0] != 0 and (signs != signs.iloc[0]).any():
            if signs.iloc[-1] > 0:
                signals.append(("MA25/75 ゴールデンクロス", f"直近{MA_CROSS_LOOKBACK_DAYS}日以内にSMA25がSMA75を上抜けた（上昇トレンド転換の兆候）"))
            elif signs.iloc[-1] < 0:
                signals.append(("MA25/75 デッドクロス", f"直近{MA_CROSS_LOOKBACK_DAYS}日以内にSMA25がSMA75を下抜けた（下降トレンド転換の兆候）"))

    # --- RSI過熱 ---
    if pd.notna(last["rsi14"]):
        if last["rsi14"] >= RSI_OVERBOUGHT:
            signals.append(("RSI過熱（買われすぎ）", f"RSI(14)={last['rsi14']:.1f}（{RSI_OVERBOUGHT:.0f}以上は買われすぎの目安）"))
        elif last["rsi14"] <= RSI_OVERSOLD:
            signals.append(("RSI過熱（売られすぎ）", f"RSI(14)={last['rsi14']:.1f}（{RSI_OVERSOLD:.0f}以下は売られすぎの目安）"))

    # --- ボリンジャーバンド・ブレイク ---
    if pd.notna(last["bb_upper"]) and last["close"] > last["bb_upper"]:
        signals.append(("ボリンジャーバンド上抜け", f"終値{last['close']:.2f}が上限バンド{last['bb_upper']:.2f}を上回っている"))
    elif pd.notna(last["bb_lower"]) and last["close"] < last["bb_lower"]:
        signals.append(("ボリンジャーバンド下抜け", f"終値{last['close']:.2f}が下限バンド{last['bb_lower']:.2f}を下回っている"))

    return signals, d


def compute_activity_signals(df):
    """出来高急増・ボラティリティ急上昇（情報の新鮮度シグナル）を判定する。"""
    signals = []
    d = df.copy()
    if len(d) < VOLUME_BASELINE_WINDOW + 1:
        return signals

    last_volume = d["volume"].iloc[-1]
    baseline_volume = d["volume"].iloc[-(VOLUME_BASELINE_WINDOW + 1):-1].mean()
    if baseline_volume and baseline_volume > 0:
        ratio = last_volume / baseline_volume
        if ratio >= VOLUME_SPIKE_RATIO:
            signals.append((
                "出来高急増",
                f"直近出来高が過去{VOLUME_BASELINE_WINDOW}日平均の{ratio:.1f}倍（急増の目安{VOLUME_SPIKE_RATIO:.1f}倍以上）",
            ))

    daily_ret = d["close"].pct_change()
    if len(daily_ret.dropna()) >= VOL_LONG_WINDOW:
        short_vol = daily_ret.iloc[-VOL_SHORT_WINDOW:].std()
        long_vol = daily_ret.iloc[-VOL_LONG_WINDOW:].std()
        if long_vol and long_vol > 0 and pd.notna(short_vol):
            ratio = short_vol / long_vol
            if ratio >= VOL_SPIKE_RATIO:
                signals.append((
                    "ボラティリティ急上昇",
                    f"直近{VOL_SHORT_WINDOW}日の値動きの荒さが直近{VOL_LONG_WINDOW}日平均の{ratio:.1f}倍"
                    f"（急上昇の目安{VOL_SPIKE_RATIO:.1f}倍以上）",
                ))

    return signals


def fetch_fundamentals(ticker):
    """PER・直近決算発表日を取得する。取得できない項目は握り潰さず「データなし」と
    明記する（外部データの可用性は不安定なため、個別に try/except して部分的な
    欠落を許容する設計にする——1項目の失敗で他の項目や他銘柄の処理を止めない）。
    """
    import yfinance as yf

    result = {"trailing_pe": None, "forward_pe": None, "next_earnings_date": None, "notes": []}
    tk = yf.Ticker(ticker)

    try:
        info = tk.info or {}
        result["trailing_pe"] = info.get("trailingPE")
        result["forward_pe"] = info.get("forwardPE")
        if result["trailing_pe"] is None and result["forward_pe"] is None:
            result["notes"].append("PER: データなし（取得元から値を得られませんでした）")
    except Exception as e:
        result["notes"].append(f"PER: データなし（取得失敗: {e}）")

    try:
        dates_df = tk.get_earnings_dates(limit=8)
        if dates_df is None or dates_df.empty:
            result["notes"].append("直近決算発表日: データなし")
        else:
            idx = dates_df.index
            if idx.tz is not None:
                idx = idx.tz_localize(None)
            now = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
            upcoming = idx[idx >= now]
            if len(upcoming) > 0:
                result["next_earnings_date"] = upcoming.min()
            else:
                result["notes"].append("直近決算発表日: 今後の予定日を取得できませんでした（データなし）")
    except AttributeError:
        result["notes"].append("直近決算発表日: データなし（インストール済みyfinanceのバージョンが未対応の可能性）")
    except Exception as e:
        result["notes"].append(f"直近決算発表日: データなし（取得失敗: {e}）")

    return result


def compute_fundamental_signals(fundamentals):
    signals = []
    if fundamentals["next_earnings_date"] is not None:
        days_until = (fundamentals["next_earnings_date"].normalize() - pd.Timestamp.now().normalize()).days
        if 0 <= days_until <= EARNINGS_SOON_DAYS:
            signals.append((
                "決算発表が近い",
                f"次回決算発表予定: {fundamentals['next_earnings_date']:%Y-%m-%d}（あと{days_until}日、"
                f"情報の新鮮度・イベントリスクとして留意）",
            ))
    return signals


def format_fundamental_line(fundamentals):
    parts = []
    if fundamentals["trailing_pe"] is not None:
        parts.append(f"PER(実績): {fundamentals['trailing_pe']:.1f}")
    if fundamentals["forward_pe"] is not None:
        parts.append(f"PER(予想): {fundamentals['forward_pe']:.1f}")
    if fundamentals["next_earnings_date"] is not None:
        parts.append(f"次回決算発表予定: {fundamentals['next_earnings_date']:%Y-%m-%d}")
    if not parts:
        parts.append("ファンダメンタルデータ: 取得できませんでした")
    return " / ".join(parts)


def render_report(results, universe_errors):
    lines = [
        "# 取引候補スキャン・レポート",
        "",
        "> 本レポートは情報提供のみを目的とした分析結果であり、投資助言ではありません。"
        "「〜の兆候が見られる」という記述はあくまで参考情報であり、断定的な売買推奨では"
        "ありません。投資判断・発注の実行は必ず自己責任で行ってください。",
        "",
        f"生成日時: {datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        "候補として提示するのはシグナル検知の結果までです。実際に発注したい場合は"
        "`order-ticket-draft` スキルで下書きを作成できます（本スキルが自動で"
        "発注や下書き生成を行うことはありません）。",
        "",
    ]

    scored = [r for r in results if r["signals"]]
    no_signal = [r for r in results if not r["signals"]]
    scored.sort(key=lambda r: len(r["signals"]), reverse=True)

    if scored:
        lines.append("## 候補銘柄")
        lines.append("")
        for r in scored:
            src = "・".join(sorted(r["sources"]))
            lines.append(f"### {r['ticker']}（対象: {src}／シグナル数: {len(r['signals'])}）")
            lines.append("")
            for name, reason in r["signals"]:
                lines.append(f"- **{name}**: {reason}")
            lines.append(f"- ファンダメンタル: {format_fundamental_line(r['fundamentals'])}")
            if r["fundamentals"]["notes"]:
                for n in r["fundamentals"]["notes"]:
                    lines.append(f"  - ({n})")
            lines.append("")
    else:
        lines.append("## 候補銘柄")
        lines.append("")
        lines.append("本日基準を満たす銘柄はありませんでした。")
        lines.append("")

    if no_signal:
        lines.append("## シグナルなし（参考）")
        lines.append("")
        for r in no_signal:
            src = "・".join(sorted(r["sources"]))
            lines.append(f"- {r['ticker']}（対象: {src}） / {format_fundamental_line(r['fundamentals'])}")
        lines.append("")

    if universe_errors:
        lines.append("## データ取得上の注意")
        lines.extend(f"- {e}" for e in universe_errors)
        lines.append("")

    lines.append("## 判定基準（既定値）")
    lines.append("")
    lines.append(f"- RSI(14): {RSI_OVERBOUGHT:.0f}以上を買われすぎ、{RSI_OVERSOLD:.0f}以下を売られすぎとする")
    lines.append(f"- 移動平均クロス: 直近{MA_CROSS_LOOKBACK_DAYS}日以内のSMA25/SMA75のゴールデン/デッドクロスを検知")
    lines.append("- ボリンジャーバンド: SMA20±2σを終値が上抜け/下抜けした場合に検知")
    lines.append(f"- 出来高急増: 直近出来高が過去{VOLUME_BASELINE_WINDOW}日平均の{VOLUME_SPIKE_RATIO:.1f}倍以上")
    lines.append(f"- ボラティリティ急上昇: 直近{VOL_SHORT_WINDOW}日の値動きの荒さが直近{VOL_LONG_WINDOW}日平均の{VOL_SPIKE_RATIO:.1f}倍以上")
    lines.append(f"- 決算発表が近い: 次回決算発表予定日まで{EARNINGS_SOON_DAYS}日以内")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="ウォッチリスト・保有ポジションから取引候補をスキャンする（発注は行わない）")
    parser.add_argument("--watchlist", default=None, help="ウォッチリストCSV（ticker列必須）")
    parser.add_argument("--positions", default=None,
                         help="保有ポジションCSV（portfolio-riskと同じ ticker,quantity,cost_basis 形式）")
    parser.add_argument("--period", default="6mo", help="テクニカル指標算出用の価格取得期間（例: 3mo, 6mo, 1y）")
    parser.add_argument("--out", required=True, help="出力するMarkdownレポートのパス")
    args = parser.parse_args()

    if not args.watchlist and not args.positions:
        print("[エラー] --watchlist と --positions のどちらも指定されていません。少なくとも一方を指定してください。", file=sys.stderr)
        raise SystemExit("スキャン対象が1件もないため、処理を中止しました。")

    universe = build_universe(args.watchlist, args.positions)
    if not universe:
        raise SystemExit("スキャン対象のティッカーが1件もありませんでした。入力ファイルを確認してください。")

    results = []
    universe_errors = []

    for ticker, sources in universe.items():
        try:
            df = fetch_history(ticker, args.period)
        except ImportError:
            raise SystemExit(
                "yfinance がインストールされていません。`pip3 install yfinance` を"
                "実行してから再度お試しください。"
            )
        except Exception as e:
            universe_errors.append(f"{ticker}: 価格データ取得失敗のためスキャン対象から除外しました（{e}）")
            continue

        technical_signals, _ = compute_technical_signals(df)
        activity_signals = compute_activity_signals(df)

        try:
            fundamentals = fetch_fundamentals(ticker)
        except ImportError:
            raise SystemExit(
                "yfinance がインストールされていません。`pip3 install yfinance` を"
                "実行してから再度お試しください。"
            )
        except Exception as e:
            # ファンダメンタル取得の予期しない失敗でもスキャン自体は継続する
            # （テクニカル・出来高シグナルは別立てで判定済みのため、ここで
            # 銘柄ごと除外すると情報の取りこぼしが大きい）。
            fundamentals = {"trailing_pe": None, "forward_pe": None, "next_earnings_date": None,
                             "notes": [f"ファンダメンタルデータ: 取得失敗（{e}）"]}
        fundamental_signals = compute_fundamental_signals(fundamentals)

        results.append({
            "ticker": ticker,
            "sources": sources,
            "signals": technical_signals + activity_signals + fundamental_signals,
            "fundamentals": fundamentals,
        })

    if not results:
        raise SystemExit("全銘柄で価格データ取得に失敗し、スキャンを実行できませんでした。")

    report = render_report(results, universe_errors)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"saved: {args.out} ({len(results)} tickers scanned, {len(universe_errors)} errors)")


if __name__ == "__main__":
    main()
