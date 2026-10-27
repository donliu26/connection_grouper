"""Headless smoke test of app.py: fake the PDF upload, click Generate, check outputs.
usage: python tests/app_smoke.py drawings.pdf [pages]"""
import os
import sys

from streamlit.testing.v1 import AppTest

PDF = os.path.abspath(sys.argv[1])
PAGES = sys.argv[2] if len(sys.argv) > 2 else ""

WRAPPER = f'''
import os, streamlit as st
class _Up:
    name = os.path.basename({PDF!r}); file_id = "t"
    def getvalue(self):
        return open({PDF!r}, "rb").read()
_orig = st.file_uploader
st.file_uploader = lambda label, *a, **k: _Up() if label.startswith("Structural") else _orig(label, *a, **k)
import sys; sys.path.insert(0, {os.getcwd()!r}); os.chdir({os.getcwd()!r})
exec(compile(open("app.py", encoding="utf-8").read(), "app.py", "exec"))
'''

at = AppTest.from_string(WRAPPER, default_timeout=900)
at.run()
assert not at.exception, at.exception
if PAGES:
    next(t for t in at.sidebar.text_input if t.label.startswith("Sheets")).set_value(PAGES).run()
gen = next(b for b in at.button if "Generate" in b.label)
gen.click().run()
assert not at.exception, at.exception
print("metrics:", [(m.label, m.value) for m in at.metric])
print("groups table rows:", len(at.dataframe[0].value))
print(at.dataframe[0].value[["Mark", "Member", "Support", "Qty", "Vu (k)", "Status"]].to_string())
print("downloads:", [b.proto.label for b in at.get("download_button")])
print("element types:", sorted({type(e).__name__ + ":" + getattr(e, "type", "") for e in at.main}))
exp = [e for e in at.get("expandable")]
print("expanders:", [e.label for e in exp], "children:", [[getattr(c, "type", "") for c in e.children.values()] for e in exp])
