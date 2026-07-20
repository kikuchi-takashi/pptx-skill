#!/usr/bin/env python3
"""注文チケット（下書き）生成スクリプト。

*** このスクリプトは発注APIを一切呼び出さない。ネットワーク通信を行わない。 ***
*** 生成物は人間が証券会社の取引画面で手動発注するための下書き（テキスト/CSV）である。 ***
*** 「送信」「発注実行」に相当する処理は意図的に実装しない。追加してはならない。 ***

例:
    python3 build_ticket.py --ticker 7203.T --side buy --quantity 100 \
        --order-type limit --price 2150 --tif day --portfolio-value 3000000 \
        --out ./output/order_ticket.txt
"""
import argparse
import csv
import datetime
import os
import sys

DRY_RUN_BANNER = (
    "⚠️  DRY RUN — これは下書きの注文チケットです。実際の発注は行われていません。\n"
    "このスキルは証券会社・取引所への発注APIを一切呼び出しません。\n"
    "内容をご自身で確認し、証券会社の取引画面から手動で発注してください。\n"
)

MAX_POSITION_PCT_DEFAULT = 0.20  # 1銘柄あたりのポートフォリオ比率の既定上限（警告用）


def validate_hard_errors(args):
    """入力として意味を成さない値を検出する。

    これらはユーザーの投資判断（ポジションサイズ、価格乖離など）に関する警告とは
    異なり、そもそも注文チケットとして成立しない入力（数量が0以下、指値/逆指値なのに
    価格未指定）である。誤って「下書き」として出力すると、人間がそのまま証券会社の
    画面に転記してしまう恐れがあるため、警告に留めず生成自体を中止する。
    """
    errors = []
    if args.quantity <= 0:
        errors.append("数量が0以下です。正の数量を指定してください。")
    if args.order_type in ("limit", "stop") and args.price is None:
        errors.append(f"{args.order_type}注文には価格の指定が必須です（--price）。")
    return errors


def validate(args):
    warnings = []
    if args.order_type == "market" and args.price is not None:
        warnings.append("成行注文に価格が指定されています（無視されます。証券会社の画面でも成行を選択してください）。")

    notional = None
    if args.price is not None:
        notional = args.price * args.quantity
    elif args.reference_price is not None:
        notional = args.reference_price * args.quantity

    if notional is not None and args.portfolio_value:
        pct = notional / args.portfolio_value
        limit_pct = args.max_position_pct if args.max_position_pct is not None else MAX_POSITION_PCT_DEFAULT
        if pct > limit_pct:
            warnings.append(
                f"この注文の想定金額（約{notional:,.0f}）はポートフォリオ総額の"
                f"{pct*100:.1f}%に相当し、既定上限（{limit_pct*100:.0f}%）を超えています。"
                "サイズが意図通りか再確認してください。"
            )

    if args.reference_price is not None and args.reference_price <= 0:
        warnings.append("参考価格（--reference-price）が0以下です。乖離チェックはスキップします。")
    elif args.reference_price is not None and args.price is not None:
        deviation = abs(args.price - args.reference_price) / args.reference_price
        if deviation > 0.05:
            warnings.append(
                f"指値価格（{args.price}）が直近参考価格（{args.reference_price}）から"
                f"{deviation*100:.1f}%乖離しています。入力ミスがないか確認してください。"
            )

    if args.side == "sell" and args.holding_quantity is not None:
        if args.quantity > args.holding_quantity:
            warnings.append(
                f"売り注文の数量（{args.quantity:g}）が申告された保有数量"
                f"（{args.holding_quantity:g}）を超えています。誤入力でないか確認してください。"
            )

    return warnings, notional


def render_text(args, warnings, notional):
    lines = [DRY_RUN_BANNER, ""]
    lines.append(f"作成日時: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    lines.append("")
    lines.append("--- 注文内容（下書き） ---")
    lines.append(f"銘柄: {args.ticker}")
    lines.append(f"売買区分: {args.side}")
    lines.append(f"数量: {args.quantity}")
    lines.append(f"注文種別: {args.order_type}")
    if args.price is not None:
        lines.append(f"価格: {args.price}")
    lines.append(f"執行条件（有効期限）: {args.tif}")
    if args.account_type:
        lines.append(f"口座種別: {args.account_type}")
    if notional is not None:
        lines.append(f"想定約定金額: {notional:,.0f}")
    lines.append("")

    if warnings:
        lines.append("--- 確認事項（警告） ---")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("--- 次のアクション ---")
    lines.append("この内容を証券会社の取引画面でご自身が入力し、内容を確認した上で発注してください。")
    lines.append("本スキル・本スクリプトは発注の送信を代行しません。")
    return "\n".join(lines)


def write_csv(path, args, notional):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["dry_run", "ticker", "side", "quantity", "order_type", "price", "tif", "account_type", "notional"])
        writer.writerow(["TRUE", args.ticker, args.side, args.quantity, args.order_type,
                          args.price if args.price is not None else "", args.tif,
                          args.account_type or "", f"{notional:.2f}" if notional is not None else ""])


def main():
    parser = argparse.ArgumentParser(description="注文チケット（下書き）を生成する。発注は行わない。")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--side", required=True, choices=["buy", "sell"])
    parser.add_argument("--quantity", required=True, type=float)
    parser.add_argument("--order-type", required=True, choices=["market", "limit", "stop"])
    parser.add_argument("--price", type=float, default=None, help="指値/逆指値の価格")
    parser.add_argument("--reference-price", type=float, default=None, help="直近参考価格（乖離チェック用、任意）")
    parser.add_argument("--tif", default="day", help="執行条件・有効期限（例: day, gtc）")
    parser.add_argument("--account-type", default=None, help="口座種別（例: 現物, 信用）")
    parser.add_argument("--portfolio-value", type=float, default=None, help="ポートフォリオ総額（サイズチェック用、任意）")
    parser.add_argument("--max-position-pct", type=float, default=None, help="1銘柄あたりの許容比率（既定0.20）")
    parser.add_argument("--holding-quantity", type=float, default=None,
                         help="現在の保有数量（売り注文の超過チェック用、申告があれば指定。任意）")
    parser.add_argument("--out", required=True, help="出力パス（.txt または .csv。両方欲しい場合は2回実行するか拡張子違いを2つ指定）")
    args = parser.parse_args()

    hard_errors = validate_hard_errors(args)
    if hard_errors:
        for e in hard_errors:
            print(f"[エラー] {e}", file=sys.stderr)
        raise SystemExit(
            "入力内容が注文チケットとして成立しないため、生成を中止しました。"
            "上記のエラーを修正して再実行してください。"
        )

    warnings, notional = validate(args)
    text = render_text(args, warnings, notional)

    root, ext = os.path.splitext(args.out)
    if ext.lower() == ".csv":
        write_csv(args.out, args, notional)
        # 人間が読む注意書きも隣に残す
        with open(root + "_readme.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print(f"saved: {args.out} (CSV, dry-run)")
        print(f"saved: {root + '_readme.txt'} (人が読む下書き注意書き)")
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"saved: {args.out} (dry-run)")

    if warnings:
        print("\n[警告あり — 内容を必ず確認してください]")
        for w in warnings:
            print(f"- {w}")


if __name__ == "__main__":
    main()
