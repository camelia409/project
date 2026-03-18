@echo off
echo =====================================================
echo  TN Floor Plan AI - Starting up...
echo =====================================================
echo.
cd /d "%~dp0"
echo Installing/checking dependencies...
pip install streamlit matplotlib numpy pandas -q
echo.
echo Launching app at http://localhost:8501
echo Press Ctrl+C to stop.
echo.
streamlit run app.py
pause
