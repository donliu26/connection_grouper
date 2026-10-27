"""Shared take-off -> loads -> groups -> outputs steps (used by the CLI and the web app)."""

import os

import pymupdf

from . import annotate, extract, grouping, loads, report
from .geometry import scale_from_arg


def parse_pages(arg, doc, cfg):
    """'5,6' / '4-7' (1-based) -> 0-based list; blank -> framing sheets by title keywords."""
    if not arg or not str(arg).strip():
        return extract.select_pages(doc, cfg["page_keywords"])
    out = []
    for part in str(arg).replace(" ", "").split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a) - 1, int(b)))
        elif part:
            out.append(int(part) - 1)
    return [p for p in out if 0 <= p < len(doc)]


def take_off(pdf_path, pages_arg, cfg, scale=None, log=print, progress=None):
    with pymupdf.open(pdf_path) as doc:
        pages = parse_pages(pages_arg, doc, cfg)
        log(f"Extracting {len(pages)} sheet(s): {', '.join(str(p + 1) for p in pages)}")
        return extract.extract(doc, pages, cfg, scale_from_arg(scale) if scale else None, log, progress)


def compute(rows, db, cfg):
    """Categories, design loads and groups (sets row['mark'])."""
    for r in rows:
        r["category"] = loads.classify(r)
        loads.design_loads(r, db, cfg)
    return grouping.make_groups(rows, cfg["group_by"])


def write_excel(path, rows, groups, info, cfg, meta):
    report.excel_report(path, groups, rows, info, cfg, meta)
    return path


def write_drawing_outputs(pdf_path, rows, groups, info, cfg, meta, outdir, log=print):
    """Marked drawings + letterhead PDF schedule. Returns (marks_pdf, schedule_pdf)."""
    base = os.path.splitext(meta.get("drawing") or os.path.basename(pdf_path))[0]
    proj = " - ".join(x for x in (meta.get("project_no"), meta.get("project_name")) if x)
    marked = os.path.join(outdir, f"{base}_CONN_MARKS.pdf")
    with pymupdf.open(pdf_path) as doc:
        annotate.annotate(doc, rows, cfg, proj, log)
        doc.save(marked, garbage=3, deflate=True)
    sched = os.path.join(outdir, f"{base}_CONN_SCHEDULE.pdf")
    report.pdf_report(sched, groups, rows, info, cfg, meta)
    return marked, sched
