@echo off
REM LECGI Connection Grouper - opens the upload page in your browser
cd /d "%~dp0"
python -m streamlit run app.py
