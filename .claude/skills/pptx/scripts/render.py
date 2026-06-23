"""
render.py — .pptx を1枚のコンタクトシート画像に焼く。

なぜ存在するか:
プレゼン品質の最大のレバーは「生成物を実際に目で見て直す」こと。テキストのはみ出し、
要素の重なり、コントラスト不足、余白の不均衡は、コードを読むだけでは気づけない。
このスクリプトは全スライドをサムネイル化して1枚の画像に並べ、Claude が Read で
視認 → 問題箇所を特定 → スクリプト修正、というループを回せるようにする。

パイプライン: pptx --(LibreOffice)--> pdf --(pdftoppm)--> png/slide --(Pillow)--> grid.png

使い方:
    python3 render.py ./output/foo.pptx
    python3 render.py ./output/foo.pptx --out /tmp/preview.png --cols 3 --dpi 96
    python3 render.py ./output/foo.pptx --slide 4        # 1枚だけ等倍で確認
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw


def find_soffice():
    for cand in (
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        shutil.which("soffice"),
        shutil.which("libreoffice"),
    ):
        if cand and os.path.exists(cand):
            return cand
    sys.exit("ERROR: LibreOffice (soffice) が見つかりません。"
             "`brew install --cask libreoffice` を実行してください。")


def find_pdftoppm():
    p = shutil.which("pdftoppm")
    if not p:
        sys.exit("ERROR: pdftoppm が見つかりません。`brew install poppler` を実行してください。")
    return p


def pptx_to_pngs(pptx, workdir, dpi):
    soffice = find_soffice()
    pdftoppm = find_pdftoppm()
    # 1) pptx -> pdf
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", workdir, pptx],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    pdf = os.path.join(workdir, os.path.splitext(os.path.basename(pptx))[0] + ".pdf")
    if not os.path.exists(pdf):
        sys.exit("ERROR: PDF 変換に失敗しました。")
    # 2) pdf -> png/slide
    subprocess.run(
        [pdftoppm, "-png", "-r", str(dpi), pdf, os.path.join(workdir, "slide")],
        check=True,
    )
    return sorted(glob.glob(os.path.join(workdir, "slide*.png")))


def contact_sheet(pngs, out, cols, pad=18, label=True):
    thumbs = [Image.open(p).convert("RGB") for p in pngs]
    tw, th = thumbs[0].size
    rows = (len(thumbs) + cols - 1) // cols
    lab = 26 if label else 0
    W = cols * tw + (cols + 1) * pad
    H = rows * (th + lab) + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), (228, 231, 237))
    draw = ImageDraw.Draw(sheet)
    for i, im in enumerate(thumbs):
        r, c = divmod(i, cols)
        x = pad + c * (tw + pad)
        y = pad + r * (th + lab + pad)
        if label:
            draw.text((x + 4, y), f"slide {i + 1}", fill=(60, 70, 90))
        sheet.paste(im, (x, y + lab))
        draw.rectangle([x, y + lab, x + tw, y + lab + th], outline=(150, 160, 175))
    sheet.save(out)
    return sheet.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("--out", default=None, help="出力PNG（既定: <pptx>_preview.png）")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--dpi", type=int, default=96, help="サムネ解像度。1枚確認時は150推奨")
    ap.add_argument("--slide", type=int, default=None, help="指定番号(1始まり)を等倍で1枚出力")
    args = ap.parse_args()

    if not os.path.exists(args.pptx):
        sys.exit(f"ERROR: ファイルが見つかりません: {args.pptx}")
    out = args.out or os.path.splitext(args.pptx)[0] + "_preview.png"

    with tempfile.TemporaryDirectory() as wd:
        pngs = pptx_to_pngs(args.pptx, wd, dpi=150 if args.slide else args.dpi)
        if not pngs:
            sys.exit("ERROR: スライド画像が生成されませんでした。")
        if args.slide:
            idx = args.slide - 1
            if not (0 <= idx < len(pngs)):
                sys.exit(f"ERROR: slide {args.slide} は範囲外 (全{len(pngs)}枚)")
            Image.open(pngs[idx]).convert("RGB").save(out)
            print(f"OK: slide {args.slide} -> {out}")
        else:
            size = contact_sheet(pngs, out, cols=args.cols)
            print(f"OK: {len(pngs)} slides -> {out}  ({size[0]}x{size[1]})")


if __name__ == "__main__":
    main()
