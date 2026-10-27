# LECGI Connection Grouper

This tool turns structural framing drawings (PDF) into connection groups with
design loads. It produces:

- the drawings with every connection marked with its connection number (BB01, BC03, BR01, ...)
- a **Structural Calculation** PDF: the LECGI calculation cover sheet (calc no., project, prepared /
  reviewed / approved by, stamp box, revision table) followed by the **Connection Summary** on the
  LECGI letterhead
- the same cover and Connection Summary in an Excel workbook, plus the group detail and review sheets

The tool does **not** design connections. Engineering designs each group in
RISA Connection or IDEA StatiCa using the tabulated worst-case loads.

## Install (one time)

```
pip install pymupdf pandas openpyxl rapidocr_onnxruntime
```

`rapidocr_onnxruntime` is needed for CAD drawings whose text is drawn as
vectors (SHX fonts), which is most AutoCAD/Revit plots. It installs with pip
only; no admin rights are needed.

## Web app (upload PDF -> Excel grouping file)

Double-click **`Start Connection Grouper.bat`**, or run `python -m streamlit run app.py`.
A browser page opens at http://localhost:8501.

1. Enter the project number and name in the sidebar. Optionally set sheets, scale or grouping.
2. Upload the structural drawings PDF and click **Generate connection grouping**.
   Sheets with vector text are read with OCR, about 1-2 minutes per sheet the first time.
   The results are cached, so re-uploading the same PDF is fast.
3. Three outputs are produced automatically:
   - **Drawings with group numbers (PDF):** the original design drawings with the group
     number (BB01, BC03, BR02 ...) at every connection. You can preview them on the page.
   - **Excel grouping file:** the group schedule with worst-case loads, the connection list,
     loads still needed from the EOR, and the criteria, with the LECGI logo and header.
   - **Structural calculation (PDF):** cover sheet + Connection Summary on the letterhead.
4. Optional: fix rows in **Review connections** (category, support, span, loads, exclude, or add
   missed members) and click **Apply edits**. All three outputs regenerate.

The app runs on this PC only (localhost). Drawings are not sent anywhere.

## Command-line workflow

```
cd C:\Users\dliu\projects\connection_grouper

:: 1. Auto take-off -> review workbook
python -m cg extract "S-drawings.pdf" --project-no 25144 --project-name "Mavis #2309"

:: 2. Engineer reviews  S-drawings_review.xlsx  (sheet "Connections", yellow columns)

:: 3. Group, mark drawings, issue schedule (--ask prompts for any missing loads)
python -m cg build "S-drawings.pdf" "S-drawings_review.xlsx" --ask --project-no 25144 --project-name "Mavis #2309"
```

`python -m cg run ...` does steps 1 and 3 in one go, without stopping for review.

`build` writes three files next to the PDF, or into `--outdir`:

| File | Content |
|---|---|
| `<name>_CONN_MARKS.pdf` | Original drawings with group marks at each connection and a stamp block on each marked sheet |
| `<name>_CONN_SCHEDULE.pdf` | Structural calculation: cover sheet + Connection Summary (letterhead) |
| `<name>_CONN_SCHEDULE.xlsx` | Cover, Connection Summary, Group Schedule, Connections, Needs Input, Criteria |

Cover sheet fields: `--location`, `--prepared-by`, `--reviewed-by`, `--approved-by`, `--calc-no`
(default `<project-no>-0001`). The web app has the same fields in the sidebar.

### Connection Summary

Same layout as the LECGI connection design calculation: sections BEAM - BEAM, BEAM - COLUMN and
BRACING CONNECTIONS; one line per member / supporting member pair. Beam connections share one
connection number per member family and depth (all W8 beam-to-beam = BB03); braces are numbered
per group. Moment connections (MBB/MBC) are listed in the beam sections.

- **Min Shear (No reaction shown):** reaction from the load rules below (minimum 10 k), or `Vy=Vz=15` for HSS beams.
- **Max Shear (Shown on dwg)**, **Max Axial**, **Max moment:** loads posted on the drawings / entered.
- **Max Capacity, Conn. Ratio, Max Capacity Axial/moment, RISA Conn. Result:** left blank for the
  engineer to fill from RISA Connection. In Excel the ratio is a formula (max shear / capacity) and
  Pass / Fail are colored automatically.
- **Note (red):** loads still needed from the EOR or supports to verify.

The `Connections` sheet of the schedule workbook can be edited and fed back
into `build` again.

### Useful options

| Option | Meaning |
|---|---|
| `--pages 5,6` / `--pages 4-7` | Sheets to process. Default: sheets whose title contains FRAMING PLAN, BRACING ELEVATION, etc. |
| `--scale 3/16` | Drawing scale (inches per foot), if the scale note can't be read |
| `--aisc-db aisc-shapes-database-v16.0.xlsx` | Use the official AISC shape properties. Recommended; otherwise a built-in table of common W/C shapes is used |
| `--group-by depth` | Coarser groups, e.g. all W16 beams to a W21 together. Uses the lightest web in the group with the maximum load |
| `--config project.json` | Override defaults: minimum shear, HSS default, UDL fraction, materials, bolts and more. See `cg/config.py` |
| `--ocr always/never` | Force OCR on or off |

## Load rules (AISC 360-22, LRFD)

1. **Loads posted on the drawings** are used: `R=`, `V=`, `P=±`, `T=`, `C=`, `M= k-ft`, or a bare `25K` next to a beam end. Beam shear is still raised to the minimum (10 k by default).
2. **Beams with no posted load** use 50% of the beam's maximum total uniform load:
   - Wc = min(8·φMp / L, 2·φVn)
   - φMp = 0.9·Fy·Zx (F2.1)
   - φVn = 0.6·Fy·d·tw with φ = 1.0, Cv1 = 1.0 for rolled W shapes (G2.1)
   - R = 0.5·Wc / 2, but not less than the minimum
   - The span comes from the dimension in the callout (e.g. `(20'-5 1/2")`), otherwise it is measured from the drawing at the sheet scale.
3. **HSS beams** use Vy = Vz = 15 k unless a load is posted.
4. **Braces, truss members and moment connections** need forces from the drawings or the EOR. Without them they are flagged **NEEDS INPUT**. They appear on the "Needs Input" sheet, and `--ask` prompts for them. Setting `"moment_default": "phiMp"` in the config uses the beam's φMp instead.

## Categories / marks

| Mark | Meaning |
|---|---|
| BB | Beam-to-beam |
| BC | Beam-to-column |
| MBB | Moment beam-to-beam |
| MBC | Moment beam-to-column |
| BR | Bracing |
| TR | Truss |

Connections are grouped by category, member size and support size. Each group
carries the maximum Vu, Vz, Pu (tension and compression) and Mu of its members.

## Review checklist (automatic take-off is heuristic)

- **Status VERIFY:** the support at a beam end wasn't identified (no column symbol or supporting beam found). Set `support_kind` (COL/BEAM) and `support`, or the `category`.
- **"member line not found":** the callout couldn't be tied to a drawn member. Check its location and the span.
- **Missed members:** add rows by hand. `member`, `category` and the loads/span are enough; leave `x`/`y` blank if no mark is needed on the drawing.
- **Moment connections:** set `category` to MBC or MBB. Moment symbols aren't detected automatically.
- **Joists and joist girders** (K, KSP, LH, DLH, G) are excluded. Their connections are by the joist supplier.

## Files

```
app.py            web app (upload PDF -> Excel grouping file)
cg/pipeline.py    shared take-off / compute / output steps (app + CLI)
cg/extract.py     callouts, spans, posted loads, beam ends, supports
cg/textsrc.py     PDF text layer + OCR (cached in %TEMP%\lecgi_cg_ocr)
cg/geometry.py    member lines, column symbols, scale
cg/loads.py       categories + AISC 360-22 load rules
cg/grouping.py    grouping / worst case / marks
cg/annotate.py    marks on drawings
cg/letterhead.py  LECGI letterhead template (cg/assets/Letterhead.pdf)
cg/report.py      PDF + Excel schedule, review workbook reader
tests/make_sample.py   synthetic framing plan used for testing
```
