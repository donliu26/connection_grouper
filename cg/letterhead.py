"""LECGI letterhead template for PDF reports (org standard: logo + letter header)."""

import os

import pymupdf

ASSET = os.path.join(os.path.dirname(__file__), "assets", "Letterhead.pdf")
LOGO_CLIP = pymupdf.Rect(31.86, 31.92, 155.43, 89.46)      # logo strips on the letterhead
PAGE_BOX = pymupdf.Rect(484.26, 745.74, 586.68, 767.34)    # "Page 1 of 1" footer box
BRAND = (0.5019, 0.0, 0.0)
CONTACT = "Phone: 502-425-1647   Fax: 502-241-4103   www.lecgi.us"


def logo_png(path, dpi=200):
    """Extract the company logo from the letterhead to a PNG (used in Excel)."""
    with pymupdf.open(ASSET) as lh:
        lh[0].get_pixmap(dpi=dpi, clip=LOGO_CLIP, alpha=False).save(path)
    return path


def _wrap(text, width, font, size):
    out = []
    for para in str(text).split("\n"):
        words, cur = para.split(" "), ""
        for w in words:
            trial = (cur + " " + w).strip()
            if pymupdf.get_text_length(trial, fontname=font, fontsize=size) <= width or not cur:
                cur = trial
            else:
                out.append(cur)
                cur = w
        out.append(cur)
    return out


class LetterheadDoc:
    BODY = pymupdf.Rect(40, 110, 572, 734)

    def __init__(self, header_title, header_sub=""):
        self.doc = pymupdf.open()
        self.lh = pymupdf.open(ASSET)
        self.header_title = header_title
        self.header_sub = header_sub
        self.page = None
        self.y = 0
        self.plain = set()          # page indexes without the letterhead (e.g. a calc cover sheet)

    # ---- page handling ----------------------------------------------
    def new_page(self):
        self.page = self.doc.new_page(width=612, height=792)
        self.page.show_pdf_page(self.page.rect, self.lh, 0)
        p, b = self.page, self.BODY
        p.insert_text((b.x0, b.y0 + 8), self.header_title, fontname="hebo", fontsize=10, color=BRAND)
        if self.header_sub:
            w = pymupdf.get_text_length(self.header_sub, fontname="helv", fontsize=8)
            p.insert_text((b.x1 - w, b.y0 + 8), self.header_sub, fontname="helv", fontsize=8)
        p.draw_line((b.x0, b.y0 + 12), (b.x1, b.y0 + 12), color=BRAND, width=0.8)
        self.y = b.y0 + 24

    def plain_page(self):
        """Blank page without the letterhead; it gets a plain 'Page i of n' footer."""
        self.page = self.doc.new_page(width=612, height=792)
        self.plain.add(len(self.doc) - 1)
        return self.page

    def logo(self, page, rect):
        """Draw the company logo (vector, from the letterhead) into rect."""
        page.show_pdf_page(rect, self.lh, 0, clip=LOGO_CLIP)

    def ensure(self, h):
        if self.page is None or self.y + h > self.BODY.y1:
            self.new_page()

    # ---- content ----------------------------------------------------
    def heading(self, text, size=11):
        self.ensure(size * 3)
        self.y += 4
        self.page.insert_text((self.BODY.x0, self.y + size), text, fontname="hebo", fontsize=size, color=BRAND)
        self.y += size + 6

    def para(self, text, size=8.5, bold=False, indent=0, color=(0, 0, 0)):
        font = "hebo" if bold else "helv"
        for ln in _wrap(text, self.BODY.width - indent, font, size):
            self.ensure(size * 1.35)
            self.page.insert_text((self.BODY.x0 + indent, self.y + size), ln, fontname=font,
                                  fontsize=size, color=color)
            self.y += size * 1.35
        self.y += 2

    def table(self, columns, rows, size=7.0, row_fills=None):
        """columns: [(header, width_fraction, align 0/1/2)]; rows: list of lists of str."""
        W = self.BODY.width
        widths = [c[1] * W for c in columns]
        pad = 2.0
        lh = size * 1.25

        def draw_header():
            hh = max(len(_wrap(c[0], w - 2 * pad, "hebo", size)) for c, w in zip(columns, widths)) * lh + 2 * pad
            self.ensure(hh + lh * 2)
            x = self.BODY.x0
            for (h, _, _a), w in zip(columns, widths):
                r = pymupdf.Rect(x, self.y, x + w, self.y + hh)
                self.page.draw_rect(r, color=(0.4, 0.4, 0.4), fill=BRAND, width=0.4)
                self._cell(r, h, "hebo", size, (1, 1, 1), 1, pad)
                x += w
            self.y += hh

        draw_header()
        for i, row in enumerate(rows):
            wrapped = [_wrap(v, w - 2 * pad, "helv", size) for v, w in zip(row, widths)]
            rh = max(len(c) for c in wrapped) * lh + 2 * pad
            if self.y + rh > self.BODY.y1:
                self.new_page()
                draw_header()
            x = self.BODY.x0
            fill = (row_fills[i] if row_fills else None) or ((0.96, 0.94, 0.94) if i % 2 else None)
            for (_h, _, a), w, lines in zip(columns, widths, wrapped):
                r = pymupdf.Rect(x, self.y, x + w, self.y + rh)
                self.page.draw_rect(r, color=(0.6, 0.6, 0.6), fill=fill, width=0.3)
                self._cell(r, "\n".join(lines), "helv", size, (0, 0, 0), a, pad)
                x += w
            self.y += rh
        self.y += 6

    def _cell(self, r, text, font, size, color, align, pad):
        lh = size * 1.25
        for k, ln in enumerate(text.split("\n")):
            tw = pymupdf.get_text_length(ln, fontname=font, fontsize=size)
            if align == 1:
                x = (r.x0 + r.x1 - tw) / 2
            elif align == 2:
                x = r.x1 - pad - tw
            else:
                x = r.x0 + pad
            self.page.insert_text((x, r.y0 + pad + size + k * lh - 0.5), ln, fontname=font,
                                  fontsize=size, color=color)

    # ---- output -----------------------------------------------------
    def save(self, path):
        n = len(self.doc)
        for i, p in enumerate(self.doc, 1):
            if i - 1 in self.plain:
                s = f"Page {i} of {n}"
                w = pymupdf.get_text_length(s, fontname="helv", fontsize=9)
                p.insert_text((561 - w, 766), s, fontname="helv", fontsize=9)
                continue
            p.draw_rect(PAGE_BOX, color=None, fill=BRAND, width=0)
            s = f"PAGE {i} OF {n}"
            w = pymupdf.get_text_length(s, fontname="hebo", fontsize=8.5)
            p.insert_text(((PAGE_BOX.x0 + PAGE_BOX.x1 - w) / 2, PAGE_BOX.y1 - 7), s,
                          fontname="hebo", fontsize=8.5, color=(1, 1, 1))
        self.doc.save(path, garbage=3, deflate=True)
        self.doc.close()
        self.lh.close()
