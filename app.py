"""LECGI Connection Grouper - web app.

Upload the structural drawings PDF -> Excel connection grouping file
(plus optional marked drawings and letterhead PDF schedule).

Start:  streamlit run app.py      (or double-click "Start Connection Grouper.bat")
"""

import hashlib
import os
import tempfile

import pandas as pd
import streamlit as st

from cg import pipeline
from cg.config import CATEGORIES, load_config
from cg.letterhead import logo_png
from cg.report import CONN_COLS, EDITABLE, normalize_rows
from cg.shapes import ShapeDB

st.set_page_config(page_title="LECGI Connection Grouper", page_icon="🔩", layout="wide")


@st.cache_resource
def _logo():
    return logo_png(os.path.join(tempfile.gettempdir(), "lecgi_logo_app.png"))


@st.cache_resource
def _workdir():
    return tempfile.mkdtemp(prefix="lecgi_cg_")


@st.cache_data(max_entries=20)
def _preview(pdf, page_no, sig):
    """PNG of one marked sheet (~2400 px wide). sig busts the cache when marks change."""
    import pymupdf
    with pymupdf.open(pdf) as doc:
        page = doc[page_no - 1]
        dpi = int(max(40, min(150, 2400 * 72 / max(page.rect.width, page.rect.height))))
        return page.get_pixmap(dpi=dpi).tobytes("png")


def _save_upload(up):
    data = up.getvalue()
    h = hashlib.md5(data).hexdigest()[:12]
    path = os.path.join(_workdir(), f"{h}_{os.path.basename(up.name)}")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    return path, h


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.image(_logo(), width="stretch")
    st.header("Project")
    project_no = st.text_input("Project No.")
    project_name = st.text_input("Project name")
    project_location = st.text_input("Project location", placeholder="e.g. Fairfield, Ohio")
    prepared_by = st.text_input("Prepared by")
    reviewed_by = st.text_input("Reviewed by")
    approved_by = st.text_input("Approved by", help="Licensed Professional Engineer")
    calc_no = st.text_input("Calc. No.", placeholder="blank = <Project No.>-0001")

    st.header("Options")
    pages_arg = st.text_input("Sheets (blank = framing plans)", placeholder="e.g. 5,6 or 4-7",
                              help="1-based PDF page numbers. Blank picks sheets titled FRAMING PLAN, "
                                   "BRACING ELEVATION, etc.")
    scale_arg = st.text_input("Scale override (in per ft)", placeholder='e.g. 3/16 (blank = read from sheet)')
    group_by = st.radio("Group by", ["shape", "depth"], horizontal=True,
                        help="shape: same member + support size.  depth: e.g. all W16 to W21 together.")
    with st.expander("Load criteria"):
        min_shear = st.number_input("Minimum beam shear (k)", value=10.0, step=1.0)
        hss_shear = st.number_input("HSS beam Vy = Vz (k)", value=15.0, step=1.0)
        udl_frac = st.number_input("Fraction of beam UDL capacity", value=0.5, step=0.05, min_value=0.1,
                                   max_value=1.0)
        moment_default = st.selectbox("Moment connections without posted M", ["ask", "phiMp"],
                                      help="ask = flag NEEDS INPUT; phiMp = use beam flexural strength")
        ocr_dpi = st.select_slider("OCR resolution (dpi)", [150, 200, 250], value=200)
    aisc_up = st.file_uploader("AISC Shapes Database v16.0 (.xlsx, optional)", type=["xlsx"])

cfg = load_config()
cfg.update(group_by=group_by, min_shear_k=min_shear, hss_beam_shear_k=hss_shear,
           udl_fraction=udl_frac, moment_default=moment_default, ocr_dpi=ocr_dpi)


@st.cache_resource
def _db(aisc_bytes_hash, aisc_path):
    db = ShapeDB()
    if aisc_path:
        db.load_aisc_xlsx(aisc_path)
    return db


aisc_path = None
if aisc_up:
    aisc_path, ah = _save_upload(aisc_up)
db = _db(aisc_up and aisc_up.file_id, aisc_path)

# ---------------------------------------------------------------- main
st.title("Connection Grouper")
st.caption("Upload structural drawings, then download the Excel connection grouping file. "
           "Groups are for design in RISA Connection / IDEA StatiCa. No connection design is performed.")

up = st.file_uploader("Structural drawings (PDF)", type=["pdf"])
if not up:
    st.info("Upload a PDF of the structural plans to begin.")
    st.stop()

pdf_path, pdf_hash = _save_upload(up)
meta = dict(project_no=project_no, project_name=project_name, drawing=up.name, prepared_by=prepared_by,
            project_location=project_location, reviewed_by=reviewed_by, approved_by=approved_by, calc_no=calc_no)
run_key = (pdf_hash, pages_arg.strip(), scale_arg.strip(), ocr_dpi)

if st.button("Generate connection grouping", type="primary") or st.session_state.get("run_key") == run_key:
    if st.session_state.get("run_key") != run_key:
        bar = st.progress(0.0, "Reading drawings ...")
        log_box = st.status("Take-off", expanded=True)

        def log(msg):
            log_box.write(msg)

        def progress(page, k, n):
            bar.progress(k / n, f"Sheet {page}: reading text (OCR) {k}/{n}")

        try:
            rows, info = pipeline.take_off(pdf_path, pages_arg, cfg, scale_arg.strip() or None, log, progress)
        except Exception as e:                      # show the error, keep the app alive
            log_box.update(label="Take-off failed", state="error")
            st.exception(e)
            st.stop()
        bar.empty()
        log_box.update(label=f"Take-off complete: {len(rows)} connections", state="complete", expanded=False)
        st.session_state.update(run_key=run_key, rows=rows, info=info)

    rows = st.session_state["rows"]
    info = st.session_state["info"]
    groups = pipeline.compute(rows, db, cfg)
    if not rows:
        st.warning("No steel member callouts were found on the selected sheets. Check the sheet numbers.")
        st.stop()

    # ---- summary
    need = [g for g in groups if g["status"] == "NEEDS INPUT"]
    verify = [g for g in groups if g["status"] == "VERIFY"]
    c = st.columns(4)
    c[0].metric("Connections", sum(1 for r in rows if not r.get("exclude")))
    c[1].metric("Groups", len(groups))
    c[2].metric("Groups needing loads", len(need))
    c[3].metric("Groups to verify", len(verify))

    # ---- outputs: group numbers on the original drawings + Excel grouping + letterhead schedule
    # regenerated only when marks, loads or project info change (Streamlit reruns on every click)
    base = os.path.splitext(up.name)[0]
    sig = hashlib.md5(repr((run_key, sorted(meta.items()), group_by, min_shear, hss_shear, udl_frac,
                            moment_default, [(r["conn_id"], r.get("mark"), r.get("x"), r.get("y"), r.get("V"),
                                              r.get("PT"), r.get("PC"), r.get("M"), r.get("exclude"))
                                             for r in rows])).encode()).hexdigest()
    if st.session_state.get("out_sig") != sig:
        with st.spinner("Writing connection group numbers on the drawings ..."):
            xls = pipeline.write_excel(os.path.join(_workdir(), f"{base}_CONN_GROUPS.xlsx"),
                                       rows, groups, info, cfg, meta)
            marked, sched = pipeline.write_drawing_outputs(pdf_path, rows, groups, info, cfg, meta,
                                                           _workdir(), log=lambda m: None)
        st.session_state.update(out_sig=sig, outputs=(marked, xls, sched))
    marked, xls, sched = st.session_state["outputs"]
    d = st.columns(3)
    for col, path, label, primary in ((d[0], marked, "Drawings with group numbers (PDF)", True),
                                      (d[1], xls, "Excel grouping file", True),
                                      (d[2], sched, "Structural calculation - connection summary (PDF)", False)):
        with open(path, "rb") as f:
            col.download_button(label, f.read(), file_name=os.path.basename(path),
                                type="primary" if primary else "secondary", width="stretch")

    # ---- preview of the marked sheets
    marked_pages = sorted({int(r["page"]) for r in rows if r.get("mark") and r.get("page")})
    if marked_pages:
        with st.expander("Preview drawings with group numbers", expanded=True):
            pg = st.selectbox("Sheet", marked_pages, format_func=lambda p: f"PDF page {p}")
            st.image(_preview(marked, pg, st.session_state["out_sig"]), width="stretch")

    # ---- group schedule
    st.subheader("Connection groups")
    gdf = pd.DataFrame([{
        "Mark": g["mark"], "Category": CATEGORIES.get(g["category"], g["category"]), "Member": g["member"],
        "Support": g["support"], "Qty": g["qty"], "Vu (k)": g["V"], "Vz (k)": g["Vz"], "Pu T (k)": g["PT"],
        "Pu C (k)": g["PC"], "Mu (k-ft)": g["M"], "Status": g["status"], "Load basis": g["load_basis"],
    } for g in groups])
    st.dataframe(gdf, hide_index=True, width="stretch")

    # ---- review / edit
    st.subheader("Review connections")
    st.caption("Edit the white columns (category, support, span, loads, exclude), then click "
               "**Apply edits**. Add missed members as new rows. Category: BB / BC / MBB / MBC / BR / TR. "
               "Loads are factored, in kips and kip-ft.")
    only = st.toggle("Show only rows needing input / verification", value=bool(need or verify))
    df = pd.DataFrame([{k: r.get(k) for k in CONN_COLS} for r in rows], columns=CONN_COLS)
    view = (df[df["status"].isin(["NEEDS INPUT", "VERIFY"])] if only else df).reset_index(drop=True)
    edited = st.data_editor(
        view, hide_index=True, width="stretch", num_rows="dynamic", key=f"ed_{run_key}_{only}",
        disabled=[c for c in CONN_COLS if c not in EDITABLE],
        column_config={
            "category": st.column_config.SelectboxColumn(options=["", "BB", "BC", "MBB", "MBC", "BR", "TR"]),
            "support_kind": st.column_config.SelectboxColumn(options=["COL", "BEAM", "UNKNOWN"]),
            "role": st.column_config.SelectboxColumn(options=["BEAM", "MOMENT", "BRACE", "TRUSS"]),
        })
    if st.button("Apply edits"):
        merged = df.set_index("conn_id")
        ed = edited.copy()
        new = ed[ed["conn_id"].isna()]
        ed = ed[ed["conn_id"].notna()].set_index("conn_id")
        cols = [c for c in ed.columns if c in EDITABLE]
        merged.loc[ed.index, cols] = ed[cols]
        records = merged.reset_index().to_dict("records") + new.to_dict("records")
        st.session_state["rows"] = normalize_rows(records)
        st.rerun()
