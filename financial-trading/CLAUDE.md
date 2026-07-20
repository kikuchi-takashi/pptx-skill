# Financial Trading Skillset

個人トレーダーが自分のPC上で使う、市場データ分析・ポートフォリオリスク評価・
発注下書き作成のための Claude Code スキル群。`agent-driven-development_v2`
（仕様駆動開発）や `pptx`（資料生成）とは完全に独立したスキル群であり、それらの
フェーズゲート方式や承認フローは踏襲していない。各スキルはユーザーのリクエストに
応じて都度独立に発火する、対話駆動の構成。

## 免責事項（必読）

本スキル群が生成する分析・レポート・リスク指標・注文チケットは、**すべて情報提供の
みを目的としたものであり、投資助言ではない**。投資判断・発注の実行は必ず自己責任で
行うこと。過去の指標・データは将来の値動きを保証しない。

## 安全方針（最重要）— 実発注は常にドライラン

`order-ticket-draft` スキルは**注文内容の整理・検証・注文チケット（テキスト/CSV）の
生成までしか行わない**。証券会社・取引所への実際の発注送信、自動売買の常駐実行は
**スキル自身が行うことは絶対にない**。生成される注文チケットは、人間が内容を確認し、
証券会社の取引画面から自分の手で発注するための下書きに過ぎない。この制約は
`order-ticket-draft/SKILL.md` と `order-ticket-draft/references/SAFETY.md` に明記して
あり、`scripts/build_ticket.py` も発注APIやブラウザ自動操作を一切含まない設計になって
いる。このスキルを拡張・修正する際は必ず `SAFETY.md` を読み、この制約を破らないこと。

## スキル一覧

| スキル | 役割 |
|---|---|
| `market-data-report` | 株価・指数・為替・暗号資産の市場データ取得、テクニカル指標算出、チャート生成、Markdownサマリーレポート作成 |
| `portfolio-risk` | 保有ポジションの時価評価、ボラティリティ・VaR・シャープレシオ・集中度・相関などのリスク指標算出、リバランス案の提示 |
| `order-ticket-draft` | 発注内容の整理・妥当性検証・注文チケット（テキスト/CSV）生成（常にドライラン。実発注は行わない） |
| `market-scan` | ウォッチリスト・保有ポートフォリオを対象に、移動平均クロス・RSI過熱・ボリンジャーバンド、出来高急増・ボラティリティ急上昇、PER・決算発表日を横断的にチェックし、候補銘柄を優先度付きで提示する取引候補スキャン（ユーザーが都度呼び出したときのみ発火。定期・無人実行の仕組みは持たない。候補提示までで発注は行わない） |

**明示的にスコープ外**: バックテスト・売買戦略の勝率検証。上記4スキルはいずれも
過去データを「見る・分析する」ためのものであり、「このルールで運用したら儲かったか」
を検証する機能は持たない。`market-scan` についても、定期実行・無人実行（cron的な
スケジュール実行）の仕組みは今回のスコープ外であり、実装していない。

## 想定するワークフロー（強制ではない）

フェーズゲートのような承認プロセスは設けていない。各スキルは単体で呼び出せるが、
自然な流れとしては次のようになる:

```
market-scan（候補を探す） ─┐
market-data-report（相場を見る） ─┴→ portfolio-risk（保有の健全性を見る）
    → order-ticket-draft（発注案の下書きを作る、最終実行は人間）
```

`market-scan` はウォッチリストと `portfolio-risk` 用の保有ポジションCSVの両方を
対象にできるため、`market-data-report`／`portfolio-risk` のどちらの前段としても
使える（「今日のスキャンして」で候補を洗い出し、気になった銘柄を
`market-data-report` で深掘りする、あるいは候補をそのまま `order-ticket-draft`
で下書き化する、など）。

「〇〇の株価を見て」だけなら `market-data-report` のみ、「ポートフォリオのリスクを
見て」だけなら `portfolio-risk` のみ、「今日のスキャンして」だけなら `market-scan`
のみ、というように必要なスキルだけを都度呼べばよい。

## セットアップ

```bash
pip3 install yfinance pandas numpy matplotlib tabulate
python3 -c "import yfinance, pandas, numpy, matplotlib, tabulate; print('deps OK')"
```

- 市場データ取得は既定で [yfinance](https://github.com/ranaroussi/yfinance)
  （Yahoo Finance の非公式ラッパー、APIキー不要・無料）を使用する。個人トレーダーが
  自分のPCで手軽に始められることを優先した選択。有料データベンダーや証券会社の
  相場配信APIに差し替えたい場合は、各スキルの `scripts/` 内のデータ取得関数
  （`fetch_prices()` 等）だけを差し替えれば、指標計算・レポート生成のロジックは
  そのまま使い回せる。
- `order-ticket-draft` はネットワークアクセスを行わない（発注APIは一切呼び出さない
  設計のため、外部通信ライブラリへの依存もない）。

## ディレクトリ構成

```
financial-trading/
├── CLAUDE.md                        ← 本ファイル
├── output/                          ← 生成されたレポート・チャート・注文チケット
└── .claude/skills/
    ├── market-data-report/
    │   ├── SKILL.md
    │   ├── scripts/fetch_data.py    ← 価格データ取得（yfinance）
    │   ├── scripts/make_report.py   ← 指標計算・チャート・Markdownレポート生成
    │   └── references/INDICATORS.md
    ├── portfolio-risk/
    │   ├── SKILL.md
    │   ├── scripts/risk_metrics.py  ← 時価評価・リスク指標・相関算出
    │   └── references/METRICS.md
    ├── order-ticket-draft/
    │   ├── SKILL.md
    │   ├── scripts/build_ticket.py  ← 注文チケット生成（発注APIは呼ばない）
    │   └── references/SAFETY.md     ← 拡張・修正時に必ず守る安全制約
    └── market-scan/
        ├── SKILL.md
        ├── scripts/scan.py          ← ウォッチリスト・保有ポジションの候補スキャン
        └── references/
            ├── SIGNALS.md            ← シグナル判定基準・閾値の定義
            └── watchlist_template.csv ← ウォッチリストCSVのサンプル
```
