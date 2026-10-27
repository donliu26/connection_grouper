"""Text with positions from a drawing page: PDF text layer and/or OCR.

Drawings exported from CAD often stroke their text as vectors (SHX fonts), so
there is no text layer for member callouts; OCR (RapidOCR) is used for those.
All coordinates are PDF points in the unrotated page space.
"""

import math
from dataclasses import dataclass

import pymupdf


@dataclass
class TextItem:
    text: str
    rect: pymupdf.Rect
    vertical: bool
    conf: float = 1.0
    src: str = "text"
    angle: float = None       # text baseline direction, degrees [0, 180)

    @property
    def ang(self):
        if self.angle is None:
            return 90.0 if self.vertical else 0.0
        return self.angle

    @property
    def center(self):
        return (self.rect.tl + self.rect.br) / 2

    @property
    def height(self):
        """Character height (the short side of the box)."""
        return self.rect.width if self.vertical else self.rect.height


def text_layer(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = "".join(s["text"] for s in ln["spans"]).strip()
            if t:
                cos, sin = ln["dir"]
                vertical = abs(sin) > 0.7
                ang = math.degrees(math.atan2(sin, cos)) % 180.0
                out.append(TextItem(t, pymupdf.Rect(ln["bbox"]), vertical, angle=ang))
    return out


_engine = None


def _ocr_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as e:
            raise RuntimeError("OCR engine not installed: pip install rapidocr_onnxruntime") from e
        _engine = RapidOCR()
    return _engine


def ocr_page(page, dpi=200, min_conf=0.6, tile_px=1800, overlap_px=500, progress=None):
    """OCR the page in overlapping tiles. Overlap must exceed the longest callout."""
    import numpy as np

    eng = _ocr_engine()
    s = 72.0 / dpi
    W, H = page.rect.width, page.rect.height
    step = (tile_px - overlap_px) * s
    tile = tile_px * s
    xs = _starts(W, tile, step)
    ys = _starts(H, tile, step)
    items = []
    n, k = len(xs) * len(ys), 0
    for y0 in ys:
        for x0 in xs:
            k += 1
            if progress:
                progress(k, n)
            clip = pymupdf.Rect(x0, y0, min(x0 + tile, W), min(y0 + tile, H))
            pix = page.get_pixmap(dpi=dpi, clip=clip, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            if img.min() > 245:          # blank tile
                continue
            res, _ = eng(img[:, :, :3].copy())
            for box, txt, conf in res or []:
                conf = float(conf)
                if conf < min_conf or not txt.strip():
                    continue
                bx = [p[0] for p in box]
                by = [p[1] for p in box]
                px0, px1, py0, py1 = min(bx), max(bx), min(by), max(by)
                # drop boxes cut by an interior tile edge; a neighbour tile has them whole
                e = 4
                if ((px0 < e and clip.x0 > 0) or (py0 < e and clip.y0 > 0)
                        or (px1 > pix.w - e and clip.x1 < W) or (py1 > pix.h - e and clip.y1 < H)):
                    continue
                r = pymupdf.Rect(clip.x0 + px0 * s, clip.y0 + py0 * s,
                                 clip.x0 + px1 * s, clip.y0 + py1 * s)
                vertical = (py1 - py0) > 1.5 * (px1 - px0)
                ang = math.degrees(math.atan2(box[1][1] - box[0][1], box[1][0] - box[0][0])) % 180.0
                if vertical and min(ang, 180 - ang) < 30:     # axis-aligned box around vertical text
                    ang = 90.0
                items.append(TextItem(txt.strip(), r, vertical, conf, "ocr", ang))
    return _dedupe(items)


def _starts(total, tile, step):
    out, v = [], 0.0
    while True:
        out.append(v)
        if v + tile >= total:
            return out
        v += step


def _dedupe(items):
    items.sort(key=lambda t: -t.conf * len(t.text))
    kept = []
    for it in items:
        dup = False
        for k in kept:
            inter = pymupdf.Rect(it.rect) & k.rect
            if inter.is_empty:
                continue
            if inter.get_area() > 0.6 * max(it.rect.get_area(), 1e-6):
                dup = True
                break
        if not dup:
            kept.append(it)
    return kept
