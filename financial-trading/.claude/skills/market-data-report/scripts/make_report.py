#!/usr/bin/env python3
"""市場データレポート生成スクリプト。

fetch_data.py が出力した CSV（date, ticker, open, high, low, close, volume の縦持ち）
から指標を計算し、銘柄ごとのチャート画像と Markdown サマリーレポートを生成する。
発注・送信系の機能は一切持たない。

例:
    python3 make_report.py --data ./output/market_data.csv \
        --out ./output/market_report.md --charts-dir ./output/charts
"""
import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pandas as pd

# matplotlib既定のDejaVu SansはCJKグリフを持たないため、チャートの日本語タイトル・
# 凡例・軸ラベル（例:「価格・移動平均・ボリンジャーバンド」「出来高」）が文字化け/欠落
# する。日本語銘柄名を扱う可能性がある以上、環境にある日本語対応フォントを探して
# 明示的に設定する（見つからない場合はデフォルトのまま、文字化けの可能性を許容）。
_JP_FONT_CANDIDATES = [
    "Hiragino Sans", "Hiragino Kaku Gothic Pro", "Yu Gothic", "YuGothic",
    "Meiryo", "Noto Sans CJK JP", "Noto Sans JP", "IPAexGothic", "IPAGothic",
    "TakaoGothic", "MS Gothic",
]


def _configure_japanese_font():
    available = {f.name for f in fm.fontManager.ttflist}
    for name in _JP_FONT_CANDIDATES:
        if name in available:
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return name
    return None


_configure_japanese_font()


def compute_indicators(df):
    df = df.sort_values("date").copy()
    df["sma25"] = df["close"].rolling(25).mean()
    df["sma75"] = df["close"].rolling(75).mean()
    df["sma20"] = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    df["bb_upper"] = df["sma20"] + 2 * std20
    df["bb_lower"] = df["sma20"] - 2 * std20

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    df["rsi14"] = 100 - (100 / (1 + rs))
    # 平均損失が0（直近14日が一方的な上昇）の場合、上のNaN回避のせいでRSIがNaNに
    # なってしまう。これは「データ不足で算出不可」ではなく、定義上RSI=100（データが
    # 十分にある場合）なので明示的に補正する。gainも0（横ばい）の場合はRSI不定のため
    # NaNのままにする。
    zero_loss_with_gain = (loss == 0) & (gain > 0) & df["close"].rolling(14).count().ge(14)
    df.loc[zero_loss_with_gain, "rsi14"] = 100.0

    daily_ret = df["close"].pct_change()
    df["ann_vol"] = daily_ret.rolling(20).std() * (252 ** 0.5)
    return df


def make_chart(df, ticker, charts_dir):
    os.makedirs(charts_dir, exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 1]})
    ax1.plot(df["date"], df["close"], label="close", color="#1f77b4")
    ax1.plot(df["date"], df["sma25"], label="SMA25", color="#ff7f0e", linewidth=1)
    ax1.plot(df["date"], df["sma75"], label="SMA75", color="#2ca02c", linewidth=1)
    ax1.fill_between(df["date"], df["bb_lower"], df["bb_upper"], color="#1f77b4", alpha=0.1,
                      label="Bollinger(2σ)")
    ax1.set_title(f"{ticker} 価格・移動平均・ボリンジャーバンド")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(alpha=0.3)

    ax2.bar(df["date"], df["volume"], color="#7f7f7f", width=1.0)
    ax2.set_title("出来高", fontsize=9)
    ax2.grid(alpha=0.3)

    fig.autofmt_xdate()
    path = os.path.join(charts_dir, f"{ticker.replace('/', '_')}.png")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def summarize(df, ticker):
    last = df.iloc[-1]
    first = df.iloc[0]
    change_pct = (last["close"] / first["close"] - 1) * 100
    lines = [
        f"### {ticker}",
        "",
        f"- 期間: {first['date']:%Y-%m-%d} 〜 {last['date']:%Y-%m-%d}",
        f"- 終値: {last['close']:.2f}（期間騰落率 {change_pct:+.1f}%）",
        f"- SMA25/SMA75: {last['sma25']:.2f} / {last['sma75']:.2f}"
        + ("（ゴールデンクロス方向）" if pd.notna(last["sma25"]) and pd.notna(last["sma75"])
           and last["sma25"] > last["sma75"] else ""),
        f"- RSI(14): {last['rsi14']:.1f}"
        + ("（70超で過熱の目安）" if pd.notna(last["rsi14"]) and last["rsi14"] > 70
           else "（30未満で売られ過ぎの目安）" if pd.notna(last["rsi14"]) and last["rsi14"] < 30 else ""),
        f"- 年率ボラティリティ(直近20日): {last['ann_vol'] * 100:.1f}%" if pd.notna(last["ann_vol"]) else "- 年率ボラティリティ: 算出不可（データ不足）",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="市場データから指標・チャート・レポートを生成する")
    parser.add_argument("--data", required=True, help="fetch_data.py が出力したCSV")
    parser.add_argument("--out", required=True, help="出力するMarkdownレポートのパス")
    parser.add_argument("--charts-dir", required=True, help="チャート画像の出力先ディレクトリ")
    args = parser.parse_args()

    raw = pd.read_csv(args.data, parse_dates=["date"])

    # fetch_data.py が書き出した「ティッカー単位で取得自体に失敗した」エラー一覧
    # （CSVには行として残らないため、サイドカーファイル経由で引き継ぐ）
    fetch_errors = []
    errors_path = args.data + ".errors.txt"
    if os.path.exists(errors_path):
        with open(errors_path, encoding="utf-8") as f:
            fetch_errors = [line.strip() for line in f if line.strip()]

    report_lines = [
        "# 市場データレポート",
        "",
        "> 本レポートは情報提供のみを目的とした分析結果であり、投資助言ではありません。"
        "投資判断は自己責任で行ってください。",
        "",
    ]

    missing_notes = []
    for ticker, group in raw.groupby("ticker"):
        df = compute_indicators(group)
        if df["close"].isna().all():
            missing_notes.append(f"- {ticker}: 有効な価格データがありませんでした")
            continue
        chart_path = make_chart(df, ticker, args.charts_dir)
        report_lines.append(summarize(df, ticker))
        report_lines.append(f"![{ticker}]({os.path.relpath(chart_path, os.path.dirname(args.out) or '.')})")
        report_lines.append("")

    all_notes = fetch_errors + missing_notes
    if all_notes:
        report_lines.append("## データ取得上の注意")
        report_lines.extend(n if n.startswith("- ") else f"- {n}" for n in all_notes)
        report_lines.append("")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"saved report: {args.out}")
    print(f"saved charts to: {args.charts_dir}")


if __name__ == "__main__":
    main()
