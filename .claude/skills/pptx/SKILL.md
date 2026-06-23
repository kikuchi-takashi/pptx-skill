---
name: pptx
description: Trigger whenever the user wants to create, generate, build, design, or update a PowerPoint / slide deck / presentation / .pptx file on ANY topic — and also when they ask to add, append, or insert slides into an existing deck in ./output/. Use this skill for both new decks and incremental edits, even if the user doesn't say the word "PowerPoint" (e.g. "make slides about X", "資料を作って", "登壇用のスライド", "この内容をプレゼンにして"). Produces polished 16:9 .pptx files via python-pptx with a built-in visual review loop.
---

# PowerPoint 生成スキル

`scripts/deck.py`（テーマ＋レイアウト＋日本語フォント処理を畳み込んだ設計ライブラリ）で
スライドを組み、`scripts/render.py` で画像化して**自分の目で見て直す**。この「視覚レビュー
ループ」がこのスキルの品質の核心。コードを読むだけでは、はみ出し・重なり・余白の崩れ・
コントラスト不足は分からない。必ず描画結果を見て直す。

新規作成と既存への追記の両方をこの1スキルで扱う。

---

## なぜこの作り方なのか（守るべき原則）

ルールの暗記ではなく、理由を理解して判断する。

- **値とレイアウトは `deck.py` に集約する。** スライド間の視覚的一貫性が品質の大半を決める。
  毎回テキストボックスを手で置くと必ずブレる。高レベルAPI（`d.bullets(...)` 等）を使えば、
  色・余白・タイポ・日本語フォントが自動で揃う。生成スクリプトは「何を載せるか」だけ書く。
- **退屈な「白背景に箇条書き」だけのデッキにしない。** 内容に紐づいた配色を選び、各スライドに
  何らかの視覚要素（アイコン・図形・画像・大きな数字・カード）を入れる。詳細は次の
  「デザインの考え方」章。
- **生成したら必ず画像化して見る。** これが最大の品質レバー。1回で完璧は出ない前提で、
  描画 → 目視 → 修正のループを最低1周回す（詳細は QA 章）。
- **1スライド1メッセージ。箇条書きは5項目まで。** 聴衆が一度に処理できる情報量には上限がある。
  超えるならスライドを分けるか `columns` / `compare` / `grid` に切り替える。
- **文字を詰め込まない。** スライドは原稿ではない。各 bullet は1行で収まる長さに。長文は
  話し言葉に回す。

---

## セットアップ確認

```bash
python3 -c "import pptx, PIL; print('py-deps OK')"
ls /Applications/LibreOffice.app/Contents/MacOS/soffice && which pdftoppm
```

`render.py` には LibreOffice と poppler が必要。無ければ:
`brew install --cask libreoffice && brew install poppler`

---

## デザインの考え方（各スライドを作る前に）

このライブラリは「汎用的に綺麗」を超えて「この内容のために作られた」と感じさせるための
仕掛けを持っている。手早く作るときも、以下を意識するだけで仕上がりが大きく変わる。

### 配色はトピックに紐づける

`tech` / `minimal` / `dark` の3テーマは確認・社内資料・急ぎの叩き台に十分な既定値。
だが「このトピック専用」と感じさせたいデッキ（登壇・対外発表・ピッチ）では
`derive_theme()` で content に紐づいた専用パレットを作る。

```python
from deck import Deck, derive_theme, PALETTES

primary, secondary, accent = PALETTES["オーシャンディープ"]  # 着想用。値は自由に変えてよい
theme = derive_theme(primary, secondary, accent, dark=False, header="bar")
d = Deck(theme=theme)
```

`PALETTES`（`deck.py` 内）には8種類の3色セットが入っている。これをそのまま使うのではなく、
「自分が別のトピックに使い回しても違和感がないか？」を自問し、違和感がなければ
もっとトピックに特化した色を選ぶ。1色（primary）が6〜7割の存在感を持ち、accent は
本当に強調したい数字・語にだけ使う——全色を均等に使わない。

### 視覚的モチーフを1つ決めて全スライドで繰り返す

`deck.py` は既定で「左端・上端の太い単色ボーダー」（`title`/`closing`/`code` の左帯、
`bar` ヘッダの上帯）をモチーフにしている。これを崩さない。新しいモチーフを加えるなら
（例: `icon_rows` の色丸アイコン）デッキ全体で繰り返し使い、1枚だけ装飾して残りを
素のままにしない。

**タイトルの下に細い線を引かない。** これは AI 生成スライドの典型的な癖として
指摘される見た目で、`deck.py` の `_header()` は意図的にこれをやらず、余白と背景色
（ヘッダ帯や地色）だけで区切っている。自分でカスタムレイアウトを書き足す時も真似しない。

### 全スライドに視覚要素を

文字だけのスライドは記憶に残らない。`bullets` を使うときも、可能なら `lead` で
主張を一文に要約してから箇条書きに入る。複数のトピックを並べるなら `icon_rows` や
`grid`、数字を見せるなら `stat`、対比なら `compare`、画像があるなら `image` /
`image_split` を優先する。同じレイアウトを3枚以上連続させない——`bullets` ばかりの
デッキになっていないか、Step 1 の構成を組む時点で見直す。

### 避けること

- 同じレイアウトの連続使用（`bullets` だけで6枚作る、等）
- 本文の中央揃え（タイトルや `stat`/`quote` 以外は左揃え）
- タイトルと本文の大小差が小さい（`h1`=40pt と `body`=18pt のコントラストを保つ）
- 汎用色のまま「これは何のトピックでも使える」配色で済ませる
- 余白の使い方をスライドごとに変える（`MX`/`MY` を勝手に上書きしない）
- 1枚だけ装飾を頑張って残りを素のままにする（全部やるか、全部シンプルに統一する）

---

## 実行フロー

### Step 1: 構成を設計する
トピックを 6〜12 枚に分解する。型:
- 1枚目 = `title`
- 章の頭 = `section`（または冒頭に `agenda`）
- 本文 = `bullets` / `columns` / `compare` / `stat` / `code` / `quote` / `image` /
  `image_split` / `icon_rows` / `grid` / `table` / `chart` / `process` — **同じものを
  連続させず、内容に応じて変える**。実データの数値があるなら `stat` で要約しつつ
  `table`/`chart` で裏付けると説得力が増す。手順・流れを見せるなら `process`
  （`agenda` は縦の目次、`process` は横並びのステップ＋矢印で役割が違う）。
- 最後 = `closing`

技術トピックで事実の正確性が要るときは WebSearch で裏取りしてから書く。
テーマは内容に合わせて選ぶ: 既定の `tech`/`minimal`/`dark` か、専用パレットが要るなら
前章の `derive_theme()`。

### Step 2: 生成スクリプトを書く
`build.py` をプロジェクトルートに置く。`deck.py` を import して高レベルAPIで組む。
APIの全シグネチャと例は `references/API.md`、レイアウトの見た目は `references/DESIGN_SYSTEM.md`。

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                ".claude/skills/pptx/scripts"))
from deck import Deck

d = Deck(theme="tech")
d.title("タイトル", "サブタイトル", "発表者 / 2026")
d.agenda("本日の内容", ["背景", "提案手法", "評価", "まとめ"])
d.section("提案手法", kicker="第1章")
d.bullets("3つの工夫", ["軽量化で推論を高速化", "誤り訂正で精度を担保",
                        ("ネストで補足", 1)], lead="要点はこの3つ")
d.icon_rows("改善の要点", [
    ("check", "非同期化", "I/Oブロッキングを排除"),
    ("bolt", "分散処理", "複数GPUへ動的に振り分け"),
])
d.code("最小実装", "def add(a, b):\n    return a + b", lang="python")
d.compare("Before / After", "従来", ["手動設定", "再現性低"],
          "提案", ["自動最適化", "完全再現"])
d.stat("成果", "92%", caption="エラー削減率", items=["A比 +30pt", "B比 +12pt"])
d.closing("ありがとうございました", "質疑応答へ")

d.save("./output/topic.pptx")
print("saved")
```

### Step 3: 生成する
```bash
python3 build.py
```

### Step 4: QA（省略禁止）— 問題はある前提で探す

最初の生成が完璧なことはまずない。「確認」ではなく「バグ探し」のつもりで臨む。
1回見て何も見つからなければ、見方が甘い。

**コンテンツQA** — テキストの抜け・誤字・プレースホルダー残留・順序ミスを機械的に確認:
```bash
python3 .claude/skills/pptx/scripts/extract_text.py ./output/topic.pptx
python3 .claude/skills/pptx/scripts/extract_text.py ./output/topic.pptx | grep -iE "xxxx|lorem|ipsum|todo|プレースホルダ"
```
grep に何か引っかかったら、成功報告の前に直す。

**視覚QA** — 画像化して目で見る:
```bash
python3 .claude/skills/pptx/scripts/render.py ./output/topic.pptx
```
出力された `./output/topic_preview.png` を **Read ツールで開いて視認する**。チェック項目:
- テキストがボックスからはみ出していないか / 枠外に出ていないか
- 要素同士が重なっていないか（タイトルが2行に折れて下の要素と詰まっていないか）
- コードが右端で切れていないか（切れるなら行を短く or 行数を減らす）
- コントラストは十分か（明るい背景に薄い文字、暗い背景に暗い文字になっていないか。
  アイコンも同様——色丸の中の記号がはっきり見えるか）
- 要素間の余白が0.3"未満になっていないか、スライド端からの余白が0.5"未満になっていないか
- 余白の取り方が場所によって不均衡でないか（片側だけ詰まっている等）
- `columns`/`grid` の列が揃っているか
- 1枚に詰め込みすぎていないか（5項目超なら分割）
- `table` の行数が多すぎて窮屈になっていないか / `chart` の凡例やラベルが重なっていないか

**4〜5枚を超えるデッキ、または自分でコードを書いた直後で「期待通りに見える」と
思い込みやすい時は、Agent ツールで fresh-eyes のレビューを依頼する。** 自分でコードを
書いた直後は「あるはず」のものを見てしまい、実際の崩れを見落とす。例:
```
general-purpose agent に依頼: "./output/topic_preview.png を見て、要素の重なり・
テキストのはみ出し・コントラスト不足・余白の不均衡・配置のズレを指摘して。
軽微なものも含めて全部報告して。"
```

### Step 5: 直して再検証する（最低1周は必須）
問題が見つかったら `build.py` を修正 → Step 3〜4 を繰り返す。**「修正→再検証」を
最低1サイクル終えるまで完了を報告しない。** 1つの修正が別の崩れを生むことがあるので、
直したスライドは必ず再度画像化して確認する。1枚を細かく見たいときは `--slide N` で
等倍出力できる。全体を通して新たな問題が出なくなったら完了。

### Step 6: 後片付けと報告
```bash
open ./output/topic.pptx && rm build.py ./output/topic_preview.png
```
報告内容: 生成パス / 枚数と各スライドのレイアウト種別 / 使用テーマ・配色 /
QAで見つけて直した点（無ければ「何を確認したか」を明示する）。

---

## 既存デッキへの追記

新規との違いは「開いて追記」だけ。フローは同じ（書く → 生成 → **QAする** → 直す）。

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                ".claude/skills/pptx/scripts"))
from deck import open_deck

path = "./output/対象.pptx"
d = open_deck(path, theme="tech")   # 既存と同じテーマを指定して一貫性を保つ
d.bullets("追加トピック", ["新しい論点1", "新しい論点2"])
d.save(path)
```
対象が複数あるときは `ls -t ./output/*.pptx | head` で最新を確認。
追記後も `render.py` でデッキ全体を見て、既存スライドとトーンが揃っているか確認する。
カスタムテーマ（`derive_theme()` で作ったもの）で追記する場合は、そのテーマ dict を
保存しておく（生成スクリプトに残しておく等）か、同じ3色から再度 `derive_theme()` を
呼んで渡す。

---

## レイアウト早見表（詳細は references/API.md）

| メソッド | 用途 |
|---|---|
| `title(title, subtitle, byline)` | 表紙 |
| `agenda(title, items)` | 番号付き目次 |
| `section(title, kicker)` | 章区切り（全面アクセント色） |
| `bullets(title, items, kicker, lead)` | 箇条書き（`items` は文字列か `(文, レベル)`） |
| `columns(title, lt, litems, rt, ritems)` | 2カラム並列 |
| `compare(title, lh, litems, rh, ritems)` | 2パネル対比（Before/After 等） |
| `icon_rows(title, rows)` | アイコン色丸＋見出し＋説明を縦に並べる |
| `grid(title, cells, cols)` | 2x2/2x3 のカードグリッド |
| `image_split(title, items, image_path, side)` | 画像を半面ブリード＋反対側に本文 |
| `table(title, headers, rows, col_widths)` | テーマ色の表（実データ） |
| `chart(title, categories, series, kind)` | 棒/線/円グラフ（実データ、編集可能） |
| `process(title, steps)` | 横並びの番号ステップ＋矢印（手順・流れ） |
| `code(title, code, lang, caption)` | コードブロック |
| `stat(title, value, caption, items)` | 大きな数字を主役に |
| `quote(text, attribution)` | 引用 |
| `image(title, image_path, caption)` | 画像（アスペクト比保持・枠内に収める） |
| `closing(title, subtitle)` | 結び |
| `notes(slide, text)` | スピーカーノートを付ける（`d.notes(d.bullets(...), "メモ")`） |

テーマ3種の色とトークン、`derive_theme()`/`PALETTES`/`ICONS` の使い方一覧は
`references/DESIGN_SYSTEM.md` と `references/API.md`。
