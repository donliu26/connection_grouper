@echo off
REM LECGI Connection Grouper - usage: cg extract^|build^|run drawings.pdf [options]
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
python -m cg %*
