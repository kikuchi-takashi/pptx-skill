"""
extract_text.py — .pptx の全テキストをスライド単位で書き出す（コンテンツQA用）。

なぜ存在するか:
視覚QA（render.py → 目視）は配置や見た目のバグを見つけるが、誤字・抜け・
プレースホルダーの残留・順序ミスは画像を眺めるだけでは気づきにくい。
markitdown 相当の役割を、追加の依存なし（python-pptx のみ）で代替する。

使い方:
    python3 extract_text.py output/foo.pptx
    python3 extract_text.py output/foo.pptx | grep -iE "xxxx|lorem|ipsum|TODO|プレースホルダ"
"""
import sys

from pptx import Presentation


def extract(path):
    prs = Presentation(path)
    lines = []
    for i, slide in enumerate(prs.slides, start=1):
        lines.append(f"--- slide {i} ---")
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = "".join(r.text for r in para.runs)
                    if text.strip():
                        lines.append(text)
            elif shape.has_table:
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        lines.append(" | ".join(cells))
            elif shape.has_chart:
                chart = shape.chart
                plot = chart.plots[0]
                if plot.categories:
                    lines.append("[chart categories] " + " | ".join(str(c) for c in plot.categories))
                for series in chart.series:
                    if series.name:
                        lines.append(f"[chart series] {series.name}")
    return "\n".join(lines)


def main():
    if len(sys.argv) != 2:
        sys.exit("使い方: python3 extract_text.py <pptx>")
    print(extract(sys.argv[1]))


if __name__ == "__main__":
    main()
