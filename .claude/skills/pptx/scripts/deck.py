"""
deck.py — self-contained presentation design library.

なぜ存在するか:
プレゼンの品質の大半は「スライド間の一貫性」で決まる。色・余白・タイポ・レイアウトを
毎回手で組むと必ずブレる。このライブラリは高レベルAPI（Deck クラス）に一貫性を畳み込み、
生成スクリプト側は「何を載せるか」だけ書けばよいようにする。これにより視覚フィードバック
ループ（render.py で画像化 → 目視 → 修正）の収束が速くなる。

依存: python-pptx のみ。

使い方:
    import sys, os
    sys.path.insert(0, "<このファイルのあるディレクトリ>")
    from deck import Deck

    d = Deck(theme="tech")
    d.title("タイトル", "サブタイトル", "発表者・日付")
    d.section("第1章", "導入")
    d.bullets("ポイント", ["項目A", "項目B", ("ネスト", 1)])
    d.code("実装", "def f():\n    return 1", lang="python", caption="最小例")
    d.save("./output/foo.pptx")

設計レイヤ:
- THEMES        色とタイポの定義（唯一の値の正）
- Deck          スライド生成の高レベルAPI
- 各 layout     title / section / bullets / columns / compare / code /
                stat / quote / agenda / image / closing
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
import os

# ---------------------------------------------------------------------------
# キャンバス (16:9 widescreen)
# ---------------------------------------------------------------------------
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MX = Inches(0.92)          # 左右の安全マージン
MY = Inches(0.85)          # 上下の安全マージン


def _rgb(hexstr):
    return RGBColor(int(hexstr[0:2], 16), int(hexstr[2:4], 16), int(hexstr[4:6], 16))


def _mix(hex_a, hex_b, t):
    """hex_a と hex_b を t (0=a, 1=b) で線形補間した HEX 文字列を返す。"""
    a = [int(hex_a[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(hex_b[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{int(round(a[i] + (b[i] - a[i]) * t)):02X}" for i in range(3))


def _lighten(hexstr, t):
    return _mix(hexstr, "FFFFFF", t)


def _darken(hexstr, t):
    return _mix(hexstr, "000000", t)


def _auto_ink(hexstr):
    """背景色 hexstr の上に乗せる文字色として、白とほぼ黒のどちらが高コントラストか
    を WCAG 相対輝度で判定して返す（RGBColor）。

    なぜ要るか: `accent`/`muted` は固定3テーマでは「白文字が映える濃い色」を選んで
    いるが、`derive_theme()` のカスタムパレットや、テーマによっては明るい accent
    （例: dark テーマの水色 `38BDF8` は白文字とのコントラストが約2.1:1しかなく
    WCAG AA の3:1すら満たさない）もあり得る。文字色を固定せず都度判定することで、
    どの配色でも読める文字色を自動選択する。
    """
    r, g, b = (int(hexstr[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    l = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    white_contrast = 1.05 / (l + 0.05)
    black_contrast = (l + 0.05) / 0.05
    return _rgb("FFFFFF") if white_contrast >= black_contrast else _rgb("111827")


# ---------------------------------------------------------------------------
# テーマ定義
#   header: "bar"     = 濃色のヘッダ帯にタイトル（情報密度が高い技術発表向き）
#           "minimal" = 帯なし。大きな見出し＋アクセントの下線（余白重視）
# ---------------------------------------------------------------------------
THEMES = {
    # 濃紺×青。技術発表のデフォルト。
    "tech": dict(
        bg="F8FAFC", ink="1E293B", muted="64748B", accent="2563EB", accent2="0EA5E9",
        panel="FFFFFF", panel_ink="1E293B", panel_edge="E2E8F0",
        code_bg="0F172A", code_ink="E2E8F0", code_accent="38BDF8",
        divider="CBD5E1", title_bg="1E293B", title_ink="FFFFFF", title_accent="60A5FA",
        header="bar",
        font_head="Hiragino Kaku Gothic ProN", font_body="Hiragino Kaku Gothic ProN",
        font_code="Menlo",
    ),
    # 白基調・大胆な余白・アクセント1色。汎用プレゼン向き。
    "minimal": dict(
        bg="FFFFFF", ink="111827", muted="6B7280", accent="EA580C", accent2="F59E0B",
        panel="F9FAFB", panel_ink="111827", panel_edge="E5E7EB",
        code_bg="1F2937", code_ink="F3F4F6", code_accent="FBBF24",
        divider="E5E7EB", title_bg="FFFFFF", title_ink="111827", title_accent="EA580C",
        header="minimal",
        # 見出し=明朝・本文=ゴシックの異質ペアリング（Georgia×Calibriに相当する日本語版）。
        font_head="Hiragino Mincho ProN", font_body="Hiragino Kaku Gothic ProN",
        font_code="Menlo",
    ),
    # 全面ダーク。発表会場が暗い時・モダンな印象向き。
    "dark": dict(
        bg="0B1120", ink="E5E7EB", muted="94A3B8", accent="38BDF8", accent2="A78BFA",
        panel="111A2E", panel_ink="E5E7EB", panel_edge="22304D",
        code_bg="060B16", code_ink="E2E8F0", code_accent="38BDF8",
        divider="22304D", title_bg="0B1120", title_ink="FFFFFF", title_accent="38BDF8",
        header="minimal",
        font_head="Hiragino Kaku Gothic ProN", font_body="Hiragino Kaku Gothic ProN",
        font_code="Menlo",
    ),
}

# サイズ（pt）
SZ = dict(h1=40, h2=28, lead=22, body=18, small=14, kicker=15, code=15, stat=72)

# ---------------------------------------------------------------------------
# トピック駆動パレット（インスピレーション用）
#   tech/minimal/dark の3テーマは「どの内容にも使い回せる汎用色」。
#   内容に紐づいた専用配色を作りたい時は derive_theme() にこの中の3色
#   (primary, secondary, accent) か、自分で選んだ3色を渡す。
# ---------------------------------------------------------------------------
PALETTES = {
    "ミッドナイトテック": ("0F1729", "38BDF8", "F472B6"),   # 深紺×水色×ピンク、AI/インフラ系
    "フォレストグロース": ("1B4332", "95D5B2", "FFD60A"),   # 深緑×若緑×黄、成長・サステナ系
    "テラコッタウォーム": ("9C4A2B", "F4E3D3", "2A6F77"),   # テラコッタ×砂×青緑、人文・温かみ系
    "コーラルエナジー": ("E8505B", "FFC857", "23395B"),     # コーラル×金×紺、プロダクト/マーケ系
    "チャコールミニマル": ("2B2D2F", "F2F2F2", "E63946"),   # 黒灰×オフ白×赤、経営・意思決定系
    "ベリークリーム": ("6D2E46", "ECE2D0", "A26769"),       # ベリー×クリーム×ローズ、ブランド/デザイン系
    "オーシャンディープ": ("073B4C", "118AB2", "06D6A0"),   # 深海×青×ミント、データ・海洋・気候系
    "セージカーム": ("5B7F73", "DCE5DD", "3D5A50"),         # セージ×ペール×深緑、医療・福祉・落ち着き系
}


def derive_theme(primary, secondary, accent, dark=False, header="bar",
                  font_head="Hiragino Kaku Gothic ProN",
                  font_body="Hiragino Kaku Gothic ProN", font_code="Menlo"):
    """3色 (primary, secondary, accent) から完全なテーマ dict を組み立てる。

    なぜ要るか: 公式デザイン指針は「内容に紐づいた専用パレットを選べ、汎用色に
    逃げるな」と明言している。THEMES の3固定テーマだけでは毎回同じ色になり、
    その指針に反する。derive_theme() があれば3色決めるだけで Deck(theme=...) に
    渡せる完全なテーマ dict（bg/ink/panel/code 等17キー）が作れる。
    """
    if dark:
        bg = _darken(primary, 0.82)
        ink = _lighten(secondary, 0.85)
        muted = _mix(ink, bg, 0.45)
        panel = _darken(primary, 0.68)
        panel_edge = _darken(secondary, 0.45)
        code_bg = _darken(primary, 0.92)
        divider = panel_edge
        title_bg = bg
    else:
        bg = _lighten(secondary, 0.88)
        ink = _darken(primary, 0.55)
        muted = _mix(ink, bg, 0.45)
        panel = "FFFFFF"
        panel_edge = _lighten(secondary, 0.65)
        code_bg = _darken(primary, 0.82)
        divider = _lighten(secondary, 0.7)
        title_bg = _darken(primary, 0.25)
    return dict(
        bg=bg, ink=ink, muted=muted, accent=accent, accent2=secondary,
        panel=panel, panel_ink=ink, panel_edge=panel_edge,
        code_bg=code_bg, code_ink=_lighten(secondary, 0.9), code_accent=accent,
        divider=divider, title_bg=title_bg, title_ink="FFFFFF",
        title_accent=_lighten(accent, 0.15),
        header=header, font_head=font_head, font_body=font_body, font_code=font_code,
    )


# アイコン代わりの記号グリフ（外部アセット不要・主要フォントで安定して出る範囲に限定）
# 注意: ⚡(U+26A1)等の「既定で絵文字提示」される文字は使わない。指定した色を無視して
# 多色のカラーグリフで描画され、白丸の中の白アイコンという一貫したモチーフが崩れる。
ICONS = {
    "check": "✓", "cross": "✕", "arrow": "→", "star": "★", "bolt": "↗",
    "diamond": "◆", "triangle": "▲", "circle": "●", "square": "■",
    "gear": "⚙", "plus": "＋", "warning": "！", "target": "◎",
}


# ---------------------------------------------------------------------------
# 低レベルヘルパ
# ---------------------------------------------------------------------------
def _apply_font(run, name=None, size=None, color=None, bold=None, italic=None,
                spacing=None):
    """フォント適用。日本語が正しく出るよう latin/ea/cs の全 typeface を設定する。

    python-pptx の run.font.name は latin (<a:latin>) しか設定しない。日本語は
    East Asian (<a:ea>) を見るため、ここを揃えないと環境依存の汚いフォントになる。
    """
    f = run.font
    if size is not None:
        f.size = Pt(size) if not hasattr(size, "emu") else size
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    if color is not None:
        f.color.rgb = color if isinstance(color, RGBColor) else _rgb(color)
    if name is not None:
        f.name = name
        rPr = run._r.get_or_add_rPr()
        for tag in ("a:ea", "a:cs"):
            el = rPr.find(qn(tag))
            if el is None:
                el = rPr.makeelement(qn(tag), {})
                rPr.append(el)
            el.set("typeface", name)
    if spacing is not None:
        run._r.get_or_add_rPr().set("spc", str(int(spacing * 100)))


def _apply_chart_font(font_obj, name=None, size=None, color=None, bold=None):
    """グラフ系の Font（凡例・軸ラベル・データラベル）に日本語フォントを正しく適用する。

    pptx.text.text.Font は run のフォントと同じ a:rPr/a:defRPr 要素を包むので、
    _apply_font と同じく ea/cs typeface も明示しないと日本語が理論フォントに化ける。
    """
    if size is not None:
        font_obj.size = Pt(size) if not hasattr(size, "emu") else size
    if bold is not None:
        font_obj.bold = bold
    if color is not None:
        font_obj.color.rgb = color if isinstance(color, RGBColor) else _rgb(color)
    if name is not None:
        font_obj.name = name
        rPr = font_obj._rPr
        for tag in ("a:ea", "a:cs"):
            el = rPr.find(qn(tag))
            if el is None:
                el = rPr.makeelement(qn(tag), {})
                rPr.append(el)
            el.set("typeface", name)


def _no_autofit(tf):
    """テキストフレームの自動縮小を無効化（崩れの原因になるため明示制御）。"""
    bodyPr = tf._txBody.find(qn("a:bodyPr"))
    for tag in ("a:normAutofit", "a:spAutoFit"):
        el = bodyPr.find(qn(tag))
        if el is not None:
            bodyPr.remove(el)
    if bodyPr.find(qn("a:noAutofit")) is None:
        bodyPr.append(bodyPr.makeelement(qn("a:noAutofit"), {}))


def _set_indent(p, level):
    """段落のインデントを EMU で設定（ネスト箇条書き用）。"""
    pPr = p._pPr
    if pPr is None:
        pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(Inches(0.35 * level))))
    pPr.set("indent", "0")


class Deck:
    def __init__(self, theme="tech"):
        self.t = dict(THEMES[theme]) if isinstance(theme, str) else dict(theme)
        self.name = theme if isinstance(theme, str) else "custom"
        self.prs = Presentation()
        self.prs.slide_width = SLIDE_W
        self.prs.slide_height = SLIDE_H
        self.count = 0

    # -- 内部 ---------------------------------------------------------------
    def _c(self, key):
        return _rgb(self.t[key])

    def _blank(self, bg=None):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        fill = s.background.fill
        fill.solid()
        fill.fore_color.rgb = self._c(bg or "bg")
        self.count += 1
        return s

    def _rect(self, s, x, y, w, h, fill=None, line=None, line_w=None, shape=MSO_SHAPE.RECTANGLE):
        sp = s.shapes.add_shape(shape, x, y, w, h)
        if fill is None:
            sp.fill.background()
        else:
            sp.fill.solid()
            sp.fill.fore_color.rgb = fill if isinstance(fill, RGBColor) else self._c(fill)
        if line is None:
            sp.line.fill.background()
        else:
            sp.line.color.rgb = line if isinstance(line, RGBColor) else self._c(line)
            sp.line.width = line_w or Pt(1)
        sp.shadow.inherit = False
        return sp

    def _text(self, s, text, x, y, w, h, size="body", color="ink", bold=False,
              align=PP_ALIGN.LEFT, font=None, anchor=MSO_ANCHOR.TOP, italic=False,
              spacing=None, line_spacing=1.15):
        tb = s.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        _no_autofit(tf)
        tf.vertical_anchor = anchor
        tf.margin_left = 0
        tf.margin_right = 0
        tf.margin_top = 0
        tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.alignment = align
        p.line_spacing = line_spacing
        r = p.add_run()
        r.text = text
        _apply_font(r, font or self.t["font_body"], SZ[size] if isinstance(size, str) else size,
                    self._c(color) if isinstance(color, str) else color, bold, italic, spacing)
        return tb

    def _header(self, s, title, kicker=None):
        """テーマに応じたタイトル領域を描き、本文の開始 y を返す。"""
        # 注意: タイトル直下に細いアクセント線を引かない。
        # 「タイトルの下に線」はAI生成スライドの定番の癖と指摘されている見た目で、
        # ここでは余白と背景色（帯 or 地色）だけで見出し領域を区切る。
        if self.t["header"] == "bar":
            bar_h = Inches(1.25)
            self._rect(s, 0, 0, SLIDE_W, bar_h, fill="title_bg")
            self._text(s, title, MX, 0, SLIDE_W - 2 * MX, bar_h, size="h2", bold=True,
                       color="title_ink", font=self.t["font_head"], anchor=MSO_ANCHOR.MIDDLE)
            return bar_h + Inches(0.45)
        else:
            y = MY
            if kicker:
                self._text(s, kicker.upper(), MX, y, SLIDE_W - 2 * MX, Inches(0.32),
                           size="kicker", color="accent", bold=True, spacing=2,
                           font=self.t["font_head"])
                y += Inches(0.4)
            self._text(s, title, MX, y, SLIDE_W - 2 * MX, Inches(0.9), size="h1",
                       bold=True, color="ink", font=self.t["font_head"])
            y += Inches(0.95)
            return y + Inches(0.35)

    def _bullet_frame(self, s, items, x, y, w, h, size="body"):
        tb = s.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        _no_autofit(tf)
        tf.margin_left = 0
        tf.margin_right = 0
        for i, item in enumerate(items):
            text, level = item if isinstance(item, tuple) else (item, 0)
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.line_spacing = 1.2
            p.space_after = Pt(10 if level == 0 else 6)
            _set_indent(p, level)
            glyph = "●  " if level == 0 else "–  "
            rg = p.add_run()
            rg.text = glyph
            _apply_font(rg, self.t["font_body"],
                        SZ[size] - (3 if level else 0), self._c("accent"), bold=True)
            rt = p.add_run()
            rt.text = text
            _apply_font(rt, self.t["font_body"],
                        SZ[size] - (3 if level else 0),
                        self._c("ink" if level == 0 else "muted"))
        return tb

    # -- レイアウト ---------------------------------------------------------
    def title(self, title, subtitle="", byline=""):
        s = self._blank(bg="title_bg")
        # 装飾: 左上にアクセントの細い縦帯
        self._rect(s, 0, 0, Inches(0.18), SLIDE_H, fill="accent")
        self._text(s, title, MX, Inches(2.55), SLIDE_W - 2 * MX, Inches(1.7), size="h1",
                   bold=True, color="title_ink", font=self.t["font_head"], line_spacing=1.1)
        if subtitle:
            self._text(s, subtitle, MX, Inches(4.25), SLIDE_W - 2 * MX, Inches(0.8),
                       size="lead", color="title_accent", font=self.t["font_head"])
        if byline:
            self._text(s, byline, MX, Inches(6.5), SLIDE_W - 2 * MX, Inches(0.5),
                       size="small", color="muted")
        return s

    def section(self, title, kicker=""):
        s = self._blank(bg="accent")
        ink = _auto_ink(self.t["accent"])
        if kicker:
            self._text(s, kicker.upper(), MX, Inches(2.7), SLIDE_W - 2 * MX, Inches(0.5),
                       size="h2", color=ink, bold=True, spacing=3,
                       font=self.t["font_head"])
        self._text(s, title, MX, Inches(3.35), SLIDE_W - 2 * MX, Inches(1.6), size="h1",
                   bold=True, color=ink, font=self.t["font_head"], line_spacing=1.05)
        return s

    def bullets(self, title, items, kicker=None, lead=None):
        s = self._blank()
        y = self._header(s, title, kicker)
        if lead:
            self._text(s, lead, MX, y, SLIDE_W - 2 * MX, Inches(0.7), size="lead",
                       color="muted")
            y += Inches(0.85)
        self._bullet_frame(s, items, MX, y, SLIDE_W - 2 * MX, SLIDE_H - y - MY)
        return s

    def columns(self, title, left_title, left_items, right_title, right_items, kicker=None):
        s = self._blank()
        y = self._header(s, title, kicker)
        gap = Inches(0.6)
        col_w = (SLIDE_W - 2 * MX - gap) / 2
        for cx, ctitle, citems in ((MX, left_title, left_items),
                                   (MX + col_w + gap, right_title, right_items)):
            self._text(s, ctitle, cx, y, col_w, Inches(0.5), size="h2", bold=True,
                       color="accent", font=self.t["font_head"])
            self._bullet_frame(s, citems, cx, y + Inches(0.75), col_w,
                               SLIDE_H - y - Inches(0.75) - MY)
        return s

    def compare(self, title, left_head, left_items, right_head, right_items,
                left_accent="muted", right_accent="accent", kicker=None):
        """2枚のパネルで対比（Before/After, 従来/提案 など）。"""
        s = self._blank()
        y = self._header(s, title, kicker)
        gap = Inches(0.5)
        col_w = (SLIDE_W - 2 * MX - gap) / 2
        ph = SLIDE_H - y - MY
        for cx, head, citems, acc in ((MX, left_head, left_items, left_accent),
                                      (MX + col_w + gap, right_head, right_items, right_accent)):
            self._rect(s, cx, y, col_w, ph, fill="panel", line="panel_edge", line_w=Pt(1))
            self._rect(s, cx, y, col_w, Inches(0.7), fill=acc)
            self._text(s, head, cx + Inches(0.3), y, col_w - Inches(0.6), Inches(0.7),
                       size="h2", bold=True, color=_auto_ink(self.t[acc]),
                       font=self.t["font_head"], anchor=MSO_ANCHOR.MIDDLE)
            self._bullet_frame(s, citems, cx + Inches(0.3), y + Inches(0.95),
                               col_w - Inches(0.6), ph - Inches(1.2))
        return s

    def code(self, title, code, lang="", caption="", kicker=None):
        s = self._blank()
        y = self._header(s, title, kicker)
        if caption:
            self._text(s, caption, MX, y, SLIDE_W - 2 * MX, Inches(0.5), size="body",
                       color="muted")
            y += Inches(0.6)
        ch = SLIDE_H - y - MY
        box = self._rect(s, MX, y, SLIDE_W - 2 * MX, ch, fill="code_bg")
        self._rect(s, MX, y, Inches(0.12), ch, fill="code_accent")  # 左端アクセント
        if lang:
            self._text(s, lang, MX + Inches(0.3), y + Inches(0.1), Inches(3), Inches(0.3),
                       size="small", color="code_accent", font=self.t["font_code"])
        tf = box.text_frame
        tf.word_wrap = False
        _no_autofit(tf)
        tf.vertical_anchor = MSO_ANCHOR.TOP  # autoshape 既定の縦中央を上書き
        tf.margin_left = Inches(0.45)
        tf.margin_top = Inches(0.5 if lang else 0.3)
        tf.margin_right = Inches(0.3)
        for i, line in enumerate(code.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.LEFT  # autoshape 既定の中央寄せを上書き
            p.line_spacing = 1.25
            r = p.add_run()
            r.text = line if line else " "
            _apply_font(r, self.t["font_code"], SZ["code"], self._c("code_ink"))
        return s

    def stat(self, title, value, caption="", items=None, kicker=None):
        """大きな数字を主役にするスライド。value="92%" など。"""
        s = self._blank()
        y = self._header(s, title, kicker)
        if items:
            half = SLIDE_W / 2
            self._text(s, value, MX, y + Inches(0.6), half - MX, Inches(2.2),
                       size="stat", bold=True, color="accent", font=self.t["font_head"])
            if caption:
                self._text(s, caption, MX, y + Inches(2.9), half - MX, Inches(1.0),
                           size="lead", color="muted")
            self._bullet_frame(s, items, half + Inches(0.3), y + Inches(0.3),
                               SLIDE_W - half - Inches(0.3) - MX, SLIDE_H - y - MY)
        else:
            self._text(s, value, MX, y + Inches(0.8), SLIDE_W - 2 * MX, Inches(2.4),
                       size="stat", bold=True, color="accent", align=PP_ALIGN.CENTER,
                       font=self.t["font_head"])
            if caption:
                self._text(s, caption, MX, y + Inches(3.4), SLIDE_W - 2 * MX, Inches(1.0),
                           size="lead", color="muted", align=PP_ALIGN.CENTER)
        return s

    def quote(self, text, attribution=""):
        s = self._blank(bg="panel")
        self._text(s, "“", MX, Inches(1.1), Inches(2), Inches(1.5), size=120,
                   bold=True, color="accent", font=self.t["font_head"])
        self._text(s, text, MX + Inches(0.2), Inches(2.5), SLIDE_W - 2 * MX - Inches(0.2),
                   Inches(2.8), size="h2", color="ink", italic=True, line_spacing=1.3,
                   font=self.t["font_head"])
        if attribution:
            self._text(s, "— " + attribution, MX + Inches(0.2), Inches(5.6),
                       SLIDE_W - 2 * MX, Inches(0.6), size="lead", color="muted")
        return s

    def agenda(self, title, items, kicker=None):
        """番号付きの目次。items は文字列のリスト。"""
        s = self._blank()
        y = self._header(s, title, kicker)
        row_h = min(Inches(0.95), (SLIDE_H - y - MY) / max(len(items), 1))
        for i, item in enumerate(items):
            ry = y + row_h * i
            self._text(s, f"{i + 1:02d}", MX, ry, Inches(1.0), row_h, size="h2",
                       bold=True, color="accent", font=self.t["font_head"],
                       anchor=MSO_ANCHOR.MIDDLE)
            self._text(s, item, MX + Inches(1.15), ry, SLIDE_W - 2 * MX - Inches(1.15),
                       row_h, size="lead", color="ink", anchor=MSO_ANCHOR.MIDDLE)
            if i < len(items) - 1:
                self._rect(s, MX, ry + row_h - Pt(1), SLIDE_W - 2 * MX, Pt(1),
                           fill="divider")
        return s

    def image(self, title, image_path, caption="", kicker=None):
        """画像を主役にするスライド。アスペクト比を保って収める。"""
        s = self._blank()
        y = self._header(s, title, kicker)
        area_w = SLIDE_W - 2 * MX
        area_h = SLIDE_H - y - MY - (Inches(0.5) if caption else 0)
        try:
            from PIL import Image
            iw, ih = Image.open(image_path).size
            scale = min(area_w / iw, area_h / ih)
            w, h = int(iw * scale), int(ih * scale)
            x = int((SLIDE_W - w) / 2)
            iy = int(y + (area_h - h) / 2)
            s.shapes.add_picture(image_path, x, iy, w, h)
        except Exception:
            s.shapes.add_picture(image_path, MX, y, height=area_h)
        if caption:
            self._text(s, caption, MX, SLIDE_H - MY - Inches(0.1), area_w, Inches(0.4),
                       size="small", color="muted", align=PP_ALIGN.CENTER)
        return s

    def icon_rows(self, title, rows, kicker=None):
        """アイコン（色つき丸の中に記号）＋見出し＋説明、を縦に並べる。

        rows: [(icon_key, heading, description), ...]。icon_key は ICONS のキー
        か任意の1〜2文字。テキストのみの bullets() と違い各行に視覚要素（色丸）
        が必須で付くので、内容オンリーのスライドが続くのを避けられる。
        """
        s = self._blank()
        y = self._header(s, title, kicker)
        n = len(rows)
        row_h = (SLIDE_H - y - MY) / n
        d = min(Inches(0.62), row_h - Inches(0.18))
        # 見出し+説明の実際の高さ（行が広く空いても、アイコンと文字が離れないよう
        # この高さを基準に「アイコン＋テキスト」をひとまとまりとして行内で中央寄せする）。
        block_h = min(Inches(0.85), row_h)
        icon_ink = _auto_ink(self.t["accent"])
        for i, (icon_key, heading, desc) in enumerate(rows):
            block_top = y + row_h * i + max(Inches(0), (row_h - block_h) / 2)
            ry = block_top + (block_h - d) / 2
            self._rect(s, MX, ry, d, d, fill="accent", shape=MSO_SHAPE.OVAL)
            glyph = ICONS.get(icon_key, icon_key)
            self._text(s, glyph, MX, ry, d, d, size="lead", bold=True,
                       color=icon_ink, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                       font=self.t["font_head"])
            tx = MX + d + Inches(0.35)
            tw = SLIDE_W - MX - tx
            self._text(s, heading, tx, block_top, tw, Inches(0.4), size="h2",
                       bold=True, color="ink", font=self.t["font_head"],
                       anchor=MSO_ANCHOR.BOTTOM)
            self._text(s, desc, tx, block_top + Inches(0.42), tw, block_h - Inches(0.42),
                       size="body", color="muted")
        return s

    def grid(self, title, cells, kicker=None, cols=2):
        """2x2 / 2x3 のカードグリッド。各カードに色つきチップ＋見出し＋本文。

        cells: [(heading, body), ...]。カードという視覚的な区切り（パネル＋
        アクセントチップ）自体が「視覚要素」を担うので、テキスト一枚岩にならない。
        """
        s = self._blank()
        y = self._header(s, title, kicker)
        gap = Inches(0.35)
        rows_n = -(-len(cells) // cols)  # ceil
        cw = (SLIDE_W - 2 * MX - gap * (cols - 1)) / cols
        ch = (SLIDE_H - y - MY - gap * (rows_n - 1)) / rows_n
        for i, (heading, body) in enumerate(cells):
            r, c = divmod(i, cols)
            cx = MX + c * (cw + gap)
            cy = y + r * (ch + gap)
            self._rect(s, cx, cy, cw, ch, fill="panel", line="panel_edge", line_w=Pt(1))
            chip = Inches(0.32)
            self._rect(s, cx + Inches(0.3), cy + Inches(0.28), chip, chip, fill="accent")
            self._text(s, heading, cx + Inches(0.3), cy + Inches(0.28) + chip + Inches(0.12),
                       cw - Inches(0.6), Inches(0.45), size="h2", bold=True, color="ink",
                       font=self.t["font_head"])
            self._text(s, body, cx + Inches(0.3), cy + Inches(1.25), cw - Inches(0.6),
                       ch - Inches(1.5), size="body", color="muted")
        return s

    def image_split(self, title, items, image_path, kicker=None, side="right"):
        """画像を縦いっぱいに半面ブリードさせ、残り半面に見出し＋本文を置く。

        画像が枠内に収まる image() と違い、画像を上下マージン無視で全面に
        敷くことで「半面ブリード画像」のレイアウトを作る。
        """
        s = self._blank()
        half = SLIDE_W / 2
        img_x = half if side == "right" else 0
        pic = s.shapes.add_picture(image_path, img_x, 0, width=half, height=SLIDE_H)
        try:
            from PIL import Image
            iw, ih = Image.open(image_path).size
            box_ratio = half / SLIDE_H
            img_ratio = iw / ih
            if img_ratio > box_ratio:
                crop = (1 - box_ratio / img_ratio) / 2
                pic.crop_left = pic.crop_right = crop
            else:
                crop = (1 - img_ratio / box_ratio) / 2
                pic.crop_top = pic.crop_bottom = crop
        except Exception:
            pass
        text_x = MX if side == "right" else half + MX
        text_w = half - MX - (MX if side == "right" else 0)
        y = MY
        if kicker:
            self._text(s, kicker.upper(), text_x, y, text_w, Inches(0.32),
                       size="kicker", color="accent", bold=True, spacing=2,
                       font=self.t["font_head"])
            y += Inches(0.4)
        self._text(s, title, text_x, y, text_w, Inches(1.5), size="h1", bold=True,
                   color="ink", font=self.t["font_head"], line_spacing=1.1)
        y += Inches(1.7)
        self._bullet_frame(s, items, text_x, y, text_w, SLIDE_H - y - MY)
        return s

    def table(self, title, headers, rows, kicker=None, col_widths=None):
        """テーマ配色の表。headers/rows はそのまま見せたい実データ向き。

        python-pptx の組み込みテーブルスタイル（青い既定の縞模様）はテーマと噛み合わないため、
        firstRow/bandRow を無効化し、ヘッダ・行の塗りを自前でテーマ色に揃える。
        """
        s = self._blank()
        y = self._header(s, title, kicker)
        n_rows = len(rows) + 1
        n_cols = len(headers)
        tw = SLIDE_W - 2 * MX
        th = SLIDE_H - y - MY
        gframe = s.shapes.add_table(n_rows, n_cols, MX, y, tw, th)
        tbl = gframe.table
        tblPr = tbl._tbl.find(qn("a:tblPr"))
        if tblPr is not None:
            tblPr.set("firstRow", "0")
            tblPr.set("bandRow", "0")

        if col_widths:
            total = sum(col_widths)
            for c, frac in enumerate(col_widths):
                tbl.columns[c].width = int(tw * frac / total)
        else:
            col_w = int(tw / n_cols)
            for c in range(n_cols):
                tbl.columns[c].width = col_w
        row_h = int(th / n_rows)
        for r in range(n_rows):
            tbl.rows[r].height = row_h

        def _cell(r, c, text, head=False):
            cell = tbl.cell(r, c)
            cell.margin_left = Inches(0.15)
            cell.margin_right = Inches(0.15)
            cell.margin_top = Inches(0.08)
            cell.margin_bottom = Inches(0.08)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = self._c("title_bg" if head else
                                                ("panel" if r % 2 == 1 else "bg"))
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = str(text)
            _apply_font(run, self.t["font_head"] if head else self.t["font_body"],
                        SZ["body"] - (0 if head else 1),
                        self._c("title_ink" if head else "ink"), bold=head)

        for c, htext in enumerate(headers):
            _cell(0, c, htext, head=True)
        for ri, row in enumerate(rows, start=1):
            for c, val in enumerate(row):
                _cell(ri, c, val)
        return s

    def chart(self, title, categories, series, kind="column", kicker=None, caption=""):
        """カテゴリ×系列のグラフ。実データの傾向・比較を見せたい時に `stat`/`grid` より向く。

        kind: "column"(縦棒) | "bar"(横棒) | "line" | "pie"。
        series: [(系列名, [値, ...]), ...]。pie は最初の1系列のみ使う。
        """
        from pptx.chart.data import CategoryChartData
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

        s = self._blank()
        y = self._header(s, title, kicker)
        cw = SLIDE_W - 2 * MX
        chh = SLIDE_H - y - MY - (Inches(0.45) if caption else 0)

        chart_data = CategoryChartData()
        chart_data.categories = categories
        for name, values in series:
            chart_data.add_series(name, values)

        kind_map = {
            "bar": XL_CHART_TYPE.BAR_CLUSTERED,
            "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
            "line": XL_CHART_TYPE.LINE_MARKERS,
            "pie": XL_CHART_TYPE.PIE,
        }
        gframe = s.shapes.add_chart(kind_map[kind], MX, y, cw, chh, chart_data)
        chart = gframe.chart
        chart.has_title = False

        palette = [self.t["accent"], self.t["accent2"],
                   _lighten(self.t["accent"], 0.35), _darken(self.t["accent2"], 0.25)]

        if kind == "pie":
            chart.has_legend = True
            chart.legend.position = XL_LEGEND_POSITION.RIGHT
            chart.legend.include_in_layout = False
            _apply_chart_font(chart.legend.font, self.t["font_body"], SZ["small"],
                               self.t["muted"])
            chart.plots[0].has_data_labels = True
            dl = chart.plots[0].data_labels
            dl.show_percentage = True
            dl.show_value = False
            dl.number_format = "0%"
            dl.number_format_is_linked = False
            _apply_chart_font(dl.font, self.t["font_body"], SZ["small"], "FFFFFF", bold=True)
            for i, point in enumerate(chart.series[0].points):
                slice_color = palette[i % len(palette)]
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = _rgb(slice_color)
                # スライス毎に明度が違うため、データラベルの文字色もスライス毎に
                # 高コントラストな方（白/ほぼ黒）へ個別に上書きする。
                _apply_chart_font(point.data_label.font, color=_auto_ink(slice_color))
        else:
            chart.has_legend = len(series) > 1
            if chart.has_legend:
                chart.legend.position = XL_LEGEND_POSITION.BOTTOM
                chart.legend.include_in_layout = False
                _apply_chart_font(chart.legend.font, self.t["font_body"], SZ["small"],
                                   self.t["muted"])
            for i, ser in enumerate(chart.series):
                color = palette[i % len(palette)]
                if kind == "line":
                    ser.format.line.color.rgb = _rgb(color)
                    ser.format.line.width = Pt(2.5)
                    ser.marker.format.fill.solid()
                    ser.marker.format.fill.fore_color.rgb = _rgb(color)
                else:
                    ser.format.fill.solid()
                    ser.format.fill.fore_color.rgb = _rgb(color)
                    ser.format.line.fill.background()
            cat_ax = chart.category_axis
            val_ax = chart.value_axis
            cat_ax.format.line.color.rgb = self._c("divider")
            val_ax.format.line.fill.background()
            val_ax.has_major_gridlines = True
            val_ax.major_gridlines.format.line.color.rgb = self._c("divider")
            val_ax.major_gridlines.format.line.width = Pt(0.75)
            _apply_chart_font(cat_ax.tick_labels.font, self.t["font_body"], SZ["small"],
                               self.t["muted"])
            _apply_chart_font(val_ax.tick_labels.font, self.t["font_body"], SZ["small"],
                               self.t["muted"])

        if caption:
            self._text(s, caption, MX, SLIDE_H - MY - Inches(0.1), cw, Inches(0.4),
                       size="small", color="muted", align=PP_ALIGN.CENTER)
        return s

    def process(self, title, steps, kicker=None):
        """横並びの番号ステップを矢印で繋ぐ、プロセス/タイムライン図。

        steps: [(見出し, 説明), ...]。3〜5ステップ向き。`agenda` は縦の目次、
        こちらは「手順・流れ」を見せる時に使う——両者は役割が違うので混同しない。
        各ステップは中央揃え（数字の下に見出し・説明を積む構図のため、本文中央
        揃えを避ける一般原則の例外として意図的に採用している）。
        """
        s = self._blank()
        y = self._header(s, title, kicker)
        n = len(steps)
        arrow_w = Inches(0.45)
        cw = (SLIDE_W - 2 * MX - arrow_w * (n - 1)) / n
        d = Inches(0.7)
        desc_h = Inches(0.9)
        block_h = d + Inches(0.25) + Inches(0.45) + desc_h
        avail = SLIDE_H - y - MY
        top = y + max(Inches(0), (avail - block_h) / 2)
        head_y = top + d + Inches(0.25)
        desc_y = head_y + Inches(0.5)
        step_ink = _auto_ink(self.t["accent"])
        for i, (heading, desc) in enumerate(steps):
            cx = MX + i * (cw + arrow_w)
            circ_x = cx + (cw - d) / 2
            self._rect(s, circ_x, top, d, d, fill="accent", shape=MSO_SHAPE.OVAL)
            self._text(s, str(i + 1), circ_x, top, d, d, size="h2", bold=True,
                       color=step_ink, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                       font=self.t["font_head"])
            self._text(s, heading, cx, head_y, cw, Inches(0.45), size="h2", bold=True,
                       color="ink", align=PP_ALIGN.CENTER, font=self.t["font_head"])
            self._text(s, desc, cx, desc_y, cw, SLIDE_H - MY - desc_y, size="small",
                       color="muted", align=PP_ALIGN.CENTER)
            if i < n - 1:
                ax = cx + cw
                self._text(s, "→", ax, top, arrow_w, d, size="h2", bold=True,
                           color="muted", align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                           font=self.t["font_head"])
        return s

    def closing(self, title, subtitle=""):
        s = self._blank(bg="title_bg")
        self._rect(s, 0, 0, Inches(0.18), SLIDE_H, fill="accent")
        self._text(s, title, MX, Inches(2.9), SLIDE_W - 2 * MX, Inches(1.6), size="h1",
                   bold=True, color="title_ink", align=PP_ALIGN.CENTER,
                   font=self.t["font_head"])
        if subtitle:
            self._text(s, subtitle, MX, Inches(4.5), SLIDE_W - 2 * MX, Inches(0.8),
                       size="lead", color="title_accent", align=PP_ALIGN.CENTER)
        return s

    def notes(self, slide, text):
        """スライドにスピーカーノートを付ける。各レイアウトメソッドは slide を
        返すので `d.notes(d.bullets(...), "話す内容のメモ")` の形で連結できる。
        """
        slide.notes_slide.notes_text_frame.text = text
        return slide

    # -- 保存 ---------------------------------------------------------------
    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.prs.save(path)
        return path


# 既存 pptx を開いて追記する場合のヘルパ
def open_deck(path, theme="tech"):
    d = Deck(theme=theme)
    d.prs = Presentation(path)
    d.count = len(d.prs.slides._sldIdLst)
    return d
