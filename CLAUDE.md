# Claude Design

技術発表・プレゼン資料を PowerPoint（.pptx）として生成するプロジェクト。

## ファイル構成

```
design/
├── output/                          ← 生成された .pptx ファイル
└── .claude/skills/pptx/
    ├── SKILL.md                     ← スキル本体（原則・実行フロー・早見表）
    ├── scripts/
    │   ├── deck.py                  ← 設計ライブラリ（テーマ＋全レイアウト＋日本語フォント処理）
    │   ├── render.py                ← .pptx を画像化して目視レビューする（視覚QA）
    │   └── extract_text.py          ← .pptx の全文をテキスト抽出する（コンテンツQA）
    └── references/
        ├── API.md                   ← deck.py の全API・例
        └── DESIGN_SYSTEM.md         ← テーマ/トークン/レイアウト見取り図
```

新規作成も既存への追記も、この1つの `pptx` スキルで扱う。
（旧 `design_tokens.py`（ルート）と旧 `slide` スキルは `deck.py` への統合で役目を終えた。）

## セットアップ

```bash
pip3 install python-pptx Pillow
brew install --cask libreoffice   # render.py の画像化に必要
brew install poppler              # 同上（pdftoppm）
```

## 設計の核

品質の最大のレバーは **視覚フィードバックループ**：生成 → `render.py` で画像化 →
Read で目視 → 崩れを修正 → 再生成。`deck.py` の高レベルAPIでスライド間の一貫性を担保する。

## 使い方

「〇〇についてプレゼンを作って」「既存ファイルにスライドを追加して」のどちらでも
`pptx` スキルが発動する。
