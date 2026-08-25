@echo off
REM Weekly refresh: pull, then rebuild the page.
REM
REM --week is passed explicitly and NOT inferred. A scheduled job runs while
REM games are in progress, and anything that guesses the week from whether
REM points exist will confidently rebuild the wrong one with nobody watching.
REM %1 is the week number; if omitted the tools fall back to Sleeper's own
REM NFL state, which is correct but worth pinning when it matters.

cd /d "%~dp0"
set PY=C:\Users\PJ\AppData\Local\Programs\Python\Python313\python.exe
if not exist "%PY%" set PY=python

echo [%date% %time%] refreshing cache
"%PY%" pull.py --user pjmaniatis

echo [%date% %time%] building weekly page
if "%~1"=="" (
  "%PY%" weekly.py --fragment
  "%PY%" weekly.py
) else (
  "%PY%" weekly.py --fragment --week %~1
  "%PY%" weekly.py --week %~1
)

echo [%date% %time%] done
