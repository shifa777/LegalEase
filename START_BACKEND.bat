@echo off
echo ================================================
echo    LegalEase Flask Backend Startup
echo ================================================
echo.
echo [1/4] Activating virtual environment...
call venv\Scripts\activate.bat

echo [2/4] Navigating to Flask directory...
cd LegalEase_Flask

echo [3/4] Verifying MongoDB cache configuration...
python verify_cache_config.py
echo.

echo [4/4] Starting Flask server...
echo.
echo Backend will be available at: http://127.0.0.1:5000
echo Cache stats available at: http://127.0.0.1:5000/cache/stats
echo.
echo Press Ctrl+C to stop the server
echo ================================================
python start_server.py
