# deck.py API リファレンス

`scripts/deck.py` の全 API。`SKILL.md` の早見表で足りないときに読む。

## 初期化

```python
from deck import Deck, open_deck

d = Deck(theme="tech")          # "tech" | "minimal" | "dark"
d = open_deck("path.pptx", "tech")  # 既存ファイルを開いて追記
```

`Deck.save(path)` は親ディレクトリを自動作成。

---

## レイアウトメソッド

すべて `slide` オブジェクトを返すので、必要なら戻り値に追加描画もできる（通常は不要）。

### `title(title, subtitle="", byline="")`
表紙。テーマの `title_bg` 全面 + 左端アクセント縦帯。
- `byline`: 発表者名・日付・所属など。

### `agenda(title, items)`
番号付き目次。`items` は文字列リスト。各行に `01 02 ...` の連番と区切り線。
行数が多いほど自動で行高を詰める。4〜6項目が見やすい。

### `section(title, kicker="")`
章区切り。アクセント色の全面背景に大見出し。`kicker` は「第1章」「PART 1」等の上付き。

### `bullets(title, items, kicker=None, lead=None)`
箇条書きの主力。
- `items`: 各要素は `"文字列"` か `("文字列", レベル)`。レベル 1 以上でネスト（インデント＋小さめ＋淡色）。
- `lead`: 箇条書きの前に置く導入の一文（任意）。
- `kicker`: minimal/dark テーマで見出しの上に出る小ラベル（任意）。
- 5項目を超えたら分割するか `columns` へ。

```python
d.bullets("設計の柱", [
    "一貫性: 値を一箇所に集約",
    "可読性: 1スライド1メッセージ",
    ("補足: ネストは控えめに", 1),
], kicker="原則", lead="この3点を徹底する")
```

### `columns(title, left_title, left_items, right_title, right_items, kicker=None)`
2カラムに別見出し＋箇条書き。並列の分類・対の概念に。

### `compare(title, left_head, left_items, right_head, right_items, left_accent="muted", right_accent="accent", kicker=None)`
2枚のパネルで対比。Before/After・従来/提案・短所/長所など。
パネル上部に色帯（`left_accent`/`right_accent` はテーマのキー名: `"muted"`,`"accent"`,`"accent2"` 等）。

```python
d.compare("移行効果", "従来", ["手作業", "属人的"],
          "導入後", ["自動化", "再現可能"])
```

### `code(title, code, lang="", caption="")`
暗色コードブロック。左端にアクセント線、左上に言語ラベル。
- `code`: 改行込みの文字列をそのまま渡す。
- 等幅・折り返しなし。**右で切れないよう1行を概ね 70〜80 文字以内**に。長い行は分割する。
- 行数の目安は 18 行以内。超えるなら要点だけ抜粋。

### `icon_rows(title, rows, kicker=None)`
アイコン色丸＋見出し＋説明の行を縦に並べる。テキストのみの `bullets` と違い、
各行に視覚要素（色つき丸の中の記号）が必須で付くので連続使用しても飽きにくい。
- `rows`: `[(icon_key, heading, description), ...]`。`icon_key` は `ICONS` のキー
  (`"check","cross","arrow","star","bolt","diamond","triangle","circle","square",
  "gear","plus","warning","target"`) か、任意の1〜2文字グリフ。
- 3〜4行が見やすい。多すぎると行高が詰まる。

```python
d.icon_rows("改善の要点", [
    ("check", "非同期化", "I/Oブロッキングを排除し並列度を確保"),
    ("bolt", "分散処理", "複数GPUへ動的に振り分け"),
    ("target", "計測駆動", "p50/p99を常時モニタリング"),
])
```

### `process(title, steps, kicker=None)`
横並びの番号ステップを矢印で繋ぐ、プロセス/タイムライン図。
- `steps`: `[(見出し, 説明), ...]`。3〜5ステップが見やすい。
- `agenda` は縦の目次（「今日話す項目」）、`process` は手順・流れ（「導入のステップ」
  「処理の流れ」）を見せる時に使う——役割が違うので使い分ける。
- 各ステップは中央揃え（数字の下に見出し・説明を積む構図のための意図的な例外）。

```python
d.process("導入の流れ", [
    ("要件定義", "課題と目標を整理する"),
    ("設計", "アーキテクチャを決める"),
    ("実装", "段階的にリリースする"),
    ("運用", "計測しながら改善する"),
])
```

### `grid(title, cells, kicker=None, cols=2)`
2x2 / 2x3 のカードグリッド。各カードはパネル背景＋アクセントチップ＋見出し＋本文。
- `cells`: `[(heading, body), ...]`。`cols` で列数（既定2）。
- 並列の項目を「カード」として見せたい時に。`columns`/`compare` より項目数が多い時向き。

### `image_split(title, items, image_path, kicker=None, side="right")`
画像を縦いっぱいに半面ブリードさせ（マージン無視・`cover`相当のクロップで敷く）、
残り半面にタイトル＋箇条書きを置く。`image()` と違い画像が枠内に収まらず全面に敷かれる。
- `side`: `"right"`（既定、画像が右半面）か `"left"`。
- `items`: `bullets()` と同じ形式。

### `table(title, headers, rows, kicker=None, col_widths=None)`
実データを行×列の表で見せる。テーマ色（ヘッダ=`title_bg`、行は`panel`/`bg`の交互）に
自動で揃う。python-pptx 既定の青い縞模様スタイルは使わない（テーマと噛み合わないため）。
- `headers`: 列見出しの文字列リスト。
- `rows`: `[[値, 値, ...], ...]`。各値は `str()` される。
- `col_widths`: 列幅の比率（例 `[2, 1, 1]`）。省略時は等分。
- 行数の目安は7行以内。多いなら抜粋するか複数スライドに分ける。

```python
d.table("四半期実績", ["四半期", "売上", "成長率"],
        [["Q1", "120M", "+5%"], ["Q2", "135M", "+12%"]])
```

### `chart(title, categories, series, kind="column", kicker=None, caption="")`
実データの傾向・比較・割合をネイティブなグラフ（PowerPoint編集可能）で見せる。
静的画像の貼り込みと違い、PowerPoint側で数値を後から修正できる。
- `kind`: `"column"`(縦棒・既定) | `"bar"`(横棒) | `"line"` | `"pie"`。
- `categories`: X軸/カテゴリのラベルリスト。
- `series`: `[(系列名, [値, ...]), ...]`。`pie` は最初の1系列のみ使う。
- 系列色はテーマの `accent`/`accent2` 等から自動で割り当てられる。凡例・軸ラベルは
  `muted` 色・本文フォントに揃える。
- 複数系列を比べたいなら `line`、内訳の割合なら `pie`、それ以外は `column`。

```python
d.chart("四半期売上", ["Q1", "Q2", "Q3", "Q4"],
        [("売上", [120, 135, 142, 160])], kind="column", caption="単位: 百万円")
d.chart("チャネル割合", ["オンライン", "店舗", "その他"],
        [("割合", [55, 35, 10])], kind="pie")
```

### `stat(title, value, caption="", items=None)`
大きな数字を主役に。`value="92%"`, `value="3.2x"` など短い文字列。
- `items` を渡すと左に数字、右に補足箇条書きの2カラム。
- `items` 省略時は中央に大きく数字＋キャプション。

### `quote(text, attribution="")`
引用。大きな引用符＋斜体本文＋出典。短い一文向き。

### `image(title, image_path, caption="")`
画像を主役に。アスペクト比を保って領域内に最大化配置（Pillow でサイズ取得）。
`image_path` は実在するファイルパス。`caption` は下中央に小さく。

### `closing(title, subtitle="")`
結び。表紙と対のデザイン（中央寄せ）。「ありがとうございました」「Q&A」等。

### `notes(slide, text)`
スピーカーノートを付ける。各レイアウトメソッドは `slide` を返すので連結できる。

```python
d.notes(d.bullets("3つの工夫", [...]), "ここで実機デモに切り替える")
```

---

## カスタムテーマ

`THEMES` の dict をコピーして色だけ差し替え、`Deck(theme=自作dict)` で渡せる。
キー: `bg, ink, muted, accent, accent2, panel, panel_ink, panel_edge, code_bg, code_ink,
code_accent, divider, title_bg, title_ink, title_accent, header("bar"|"minimal"),
font_head, font_body, font_code`。色は6桁HEX文字列（`#`なし）。

### `derive_theme(primary, secondary, accent, dark=False, header="bar", font_head=..., font_body=..., font_code=...)`
3色だけから上記17キー全部を含む完全なテーマ dict を組み立てるヘルパ。固定3テーマでは
「内容に紐づいた専用配色」を作れないため、トピック専用デッキを作るときはこちらを使う。

```python
from deck import Deck, derive_theme, PALETTES

primary, secondary, accent = PALETTES["コーラルエナジー"]  # 8種類の着想用パレット
theme = derive_theme(primary, secondary, accent, dark=False, header="minimal")
d = Deck(theme=theme)
```

`dark=True` にすると全面ダーク版（`bg`/`panel`/`code_bg` が暗色側）になる。
`PALETTES` は `deck.py` 内の辞書で、値そのまま使うだけでなく着想・出発点として
自由に変えてよい。

### `ICONS`
`icon_rows()` で使う記号グリフ辞書。`{"check": "✓", "arrow": "→", ...}`。
新しいキーを追加するときは、絵文字提示が既定の文字（例: ⚡ U+26A1）を避ける——
色指定を無視した多色グリフで描画され、色丸の中の単色アイコンというモチーフが崩れる。

---

## よくある修正パターン（視覚レビュー後）

| 症状 | 対処 |
|---|---|
| 箇条書きが下にはみ出す | 項目を減らす / `columns` に分割 / 文を短く |
| コードが右で切れる | 1行を短く / 行数を減らす / 抜粋にする |
| 文字が小さく見える | 情報を削って1スライド1メッセージへ |
| 余白が間延び | `stat` や `quote` など主役が大きい型に変える |
| 既存デッキと色が違う | `open_deck` の `theme` を既存と一致させる |
| 表/グラフの行・系列が多すぎて窮屈 | 行を絞る・列幅を `col_widths` で調整・複数スライドに分割 |
