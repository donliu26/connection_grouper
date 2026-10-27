"""Command line:

  extract  drawings.pdf -> <name>_review.xlsx  (auto take-off for engineer review)
  build    drawings.pdf review.xlsx -> marked drawings PDF + group schedule (PDF/XLSX)
  run      extract + build in one step (no review pause)
"""

import argparse
import os
import sys

from . import pipeline, report
from .config import load_config
from .shapes import ShapeDB


def _db(args):
    db = ShapeDB()
    if args.aisc_db:
        n = db.load_aisc_xlsx(args.aisc_db)
        print(f"Loaded {n} shapes from {args.aisc_db}")
    return db


def _meta(args):
    return dict(project_no=args.project_no or "", project_name=args.project_name or "",
                drawing=os.path.basename(args.pdf), prepared_by=args.prepared_by or "",
                project_location=args.location or "", reviewed_by=args.reviewed_by or "",
                approved_by=args.approved_by or "", calc_no=args.calc_no or "")


def do_extract(args, cfg):
    rows, info = pipeline.take_off(args.pdf, args.pages, cfg, args.scale)
    groups = pipeline.compute(rows, _db(args), cfg)
    out = args.out or os.path.splitext(args.pdf)[0] + "_review.xlsx"
    pipeline.write_excel(out, rows, groups, info, cfg, _meta(args))
    print(f"Review workbook: {out}")
    return out, info


def _ask(rows):
    """Prompt for missing loads, one question per member/category."""
    asked = {}
    for r in rows:
        if r.get("status") != "NEEDS INPUT" or r.get("exclude"):
            continue
        key = (r["member"], r["category"], r.get("support"))
        if key not in asked:
            q = f"{r['category']} {r['member']} -> {r.get('support') or r.get('support_kind')} " \
                f"(e.g. {r['conn_id']}, {r['load_basis']}).\n  Enter "
            if r["category"] in ("BR", "TR"):
                q += "axial T,C in kips (e.g. 40,40) or blank to skip: "
            elif r["category"] in ("MBB", "MBC"):
                q += "V,M in kips,kip-ft (e.g. 20,80) or blank: "
            else:
                q += "shear V in kips (or span in ft as e.g. 'L=24') or blank: "
            asked[key] = input(q).strip()
        ans = asked[key]
        if not ans:
            continue
        if ans.upper().startswith("L="):
            r["span_ft"] = float(ans[2:])
            r["span_src"] = "user"
            continue
        vals = [float(v) for v in ans.replace(" ", "").split(",") if v]
        if r["category"] in ("BR", "TR"):
            r["PT_posted"] = vals[0]
            r["PC_posted"] = vals[1] if len(vals) > 1 else vals[0]
        elif r["category"] in ("MBB", "MBC"):
            r["V_posted"] = vals[0]
            if len(vals) > 1:
                r["M_posted"] = vals[1]
        else:
            r["V_posted"] = vals[0]
        r["notes"] = "; ".join(x for x in (r.get("notes"), "load by user (prompt)") if x)


def do_build(args, cfg, rows=None, info=None):
    if rows is None:
        rows = report.read_review(args.review)
        info = []
    db = _db(args)
    groups = pipeline.compute(rows, db, cfg)
    if args.ask:
        _ask(rows)
        groups = pipeline.compute(rows, db, cfg)
    outdir = args.outdir or os.path.dirname(os.path.abspath(args.pdf))
    os.makedirs(outdir, exist_ok=True)
    meta = _meta(args)
    if not info:
        info = [dict(page=p, ocr=False, scale_ppf=0, scale_src="from review", n_members=0)
                for p in sorted({int(r["page"]) for r in rows if r.get("page")})]
    marked, pdf = pipeline.write_drawing_outputs(args.pdf, rows, groups, info, cfg, meta, outdir)
    xls = os.path.join(outdir, os.path.splitext(meta["drawing"])[0] + "_CONN_SCHEDULE.xlsx")
    pipeline.write_excel(xls, rows, groups, info, cfg, meta)

    need = sum(1 for g in groups if g["status"] == "NEEDS INPUT")
    print(f"{len(rows)} connections -> {len(groups)} groups ({need} need loads from EOR)")
    for p in (marked, pdf, xls):
        print("  " + p)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cg", description="LECGI connection grouper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("pdf", help="structural drawings PDF")
        p.add_argument("--config", help="JSON file overriding defaults (see cg/config.py)")
        p.add_argument("--aisc-db", help="AISC Shapes Database v16.0 .xlsx")
        p.add_argument("--project-no")
        p.add_argument("--project-name")
        p.add_argument("--prepared-by")
        p.add_argument("--reviewed-by")
        p.add_argument("--approved-by")
        p.add_argument("--location", help="project location for the calculation cover sheet")
        p.add_argument("--calc-no", help="calculation number (default <project-no>-0001)")
        p.add_argument("--group-by", choices=["shape", "depth"])

    p = sub.add_parser("extract", help="auto take-off to a review workbook")
    common(p)
    p.add_argument("--pages", help="1-based sheets, e.g. 5,6 or 4-7 (default: framing sheets)")
    p.add_argument("--scale", help="drawing scale override, inches per foot e.g. 3/16, or 1:64")
    p.add_argument("--ocr", choices=["auto", "always", "never"])
    p.add_argument("-o", "--out")

    p = sub.add_parser("build", help="group, mark drawings and issue the schedule")
    common(p)
    p.add_argument("review", help="review workbook (Connections sheet)")
    p.add_argument("--outdir")
    p.add_argument("--ask", action="store_true", help="prompt for missing loads")

    p = sub.add_parser("run", help="extract + build without the review pause")
    common(p)
    p.add_argument("--pages")
    p.add_argument("--scale")
    p.add_argument("--ocr", choices=["auto", "always", "never"])
    p.add_argument("-o", "--out")
    p.add_argument("--outdir")
    p.add_argument("--ask", action="store_true")

    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.group_by:
        cfg["group_by"] = args.group_by
    if getattr(args, "ocr", None):
        cfg["ocr"] = args.ocr

    if args.cmd == "extract":
        do_extract(args, cfg)
    elif args.cmd == "build":
        do_build(args, cfg)
    else:
        out, info = do_extract(args, cfg)
        args.review = out
        do_build(args, cfg, report.read_review(out), info)


if __name__ == "__main__":
    sys.exit(main())
