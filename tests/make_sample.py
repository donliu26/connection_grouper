"""Build a small synthetic framing plan (text layer, posted loads, brace) for testing."""
import sys

import pymupdf

S = 9.0          # 1/8" = 1'-0"  -> 9 pt per foot
X0, Y0 = 100, 150


def ft(x, y):
    return pymupdf.Point(X0 + x * S, Y0 + y * S)


doc = pymupdf.open()
p = doc.new_page(width=1224, height=792)
cols = [(0, 0), (30, 0), (60, 0), (0, 25), (30, 25), (60, 25)]
for c in cols:                                   # column symbols: filled squares 1 ft
    q = ft(*c)
    p.draw_rect(pymupdf.Rect(q.x - 4.5, q.y - 4.5, q.x + 4.5, q.y + 4.5), color=(0, 0, 0), fill=(0, 0, 0))
# girders on column lines
for y in (0, 25):
    for x0, x1 in ((0, 30), (30, 60)):
        p.draw_line(ft(x0, y), ft(x1, y), width=1.4)
for x in (0, 30, 60):
    p.draw_line(ft(x, 0), ft(x, 25), width=1.4)
# infill beams framing into girders on x=0..30 bay (beam-to-beam)
for x in (10, 20):
    p.draw_line(ft(x, 0), ft(x, 25), width=1.4)
# diagonal brace in second bay
p.draw_line(ft(30, 0), ft(60, 25), width=1.4)


def label(text, x, y, rotate=0):
    if rotate in (0, 90):
        p.insert_text(ft(x, y), text, fontsize=7, rotate=rotate)
    else:                                         # skewed text along a diagonal member
        p.insert_text(ft(x, y), text, fontsize=7, morph=(ft(x, y), pymupdf.Matrix(rotate)))


label("W24X55", 12, -0.6)
label("W24X55 (R=45K)", 40, -0.6)
label("W21X44", 12, 24.4)
label("W21X44", 42, 24.4)
label("W16X26", 9.4, 15, rotate=90)
label("W16X26", 19.4, 15, rotate=90)
label("W18X35", -0.6, 15, rotate=90)
label("W18X35", 29.4, 15, rotate=90)
label("W18X35", 59.4, 15, rotate=90)
label("HSS6X6X3/8", 44, 11.0, rotate=-40)
label("P=±60K", 46, 13.4, rotate=-40)
label("25K", 10.3, 23.6)
p.insert_text((900, 760), 'SECOND FLOOR FRAMING PLAN   SCALE: 1/8" = 1\'-0"', fontsize=9)
doc.save(sys.argv[1])
