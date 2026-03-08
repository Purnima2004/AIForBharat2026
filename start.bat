@echo off
title AI Video Generation Studio
color 0A

echo.
echo  ==========================================
echo   AI Video Generation Studio
echo   Powered by Google Gemini
echo  ==========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: Install Python deps if needed
echo  [1/3] Installing Python dependencies...
pip install -r requirements.txt --quiet

:: Check if API key is set
findstr /C:"your_gemini_api_key_here" .env >nul 2>&1
if not errorlevel 1 (
    echo.
    echo  [WARNING] Your Gemini API key is NOT set!
    echo  Please edit .env and set GEMINI_API_KEY=your_key_here
    echo.
    notepad .env
    echo  Press any key after saving .env...
    pause >nul
)

:: Start n8n in background (optional)
echo  [2/3] Starting n8n (optional workflow engine)...
node --version >nul 2>&1
if not errorlevel 1 (
    start "n8n Server" cmd /c "npx n8n && pause"
    echo  n8n starting at http://localhost:5678
    timeout /t 3 /nobreak >nul
) else (
    echo  [INFO] Node.js not found — skipping n8n (built-in pipeline will be used)
)

:: Start Flask backend
echo  [3/3] Starting Flask backend...
echo.
echo  ==========================================
echo   Open your browser: http://localhost:5000
echo  ==========================================
echo.

:: Open browser after 2s delay
timeout /t 2 /nobreak >nul
start http://localhost:5000

:: Start Flask (foreground)
python app.py

pause
