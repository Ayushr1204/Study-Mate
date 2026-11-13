@echo off
REM Re-launch inside a window that never closes, so any error stays readable.
if /i not "%~1"=="run" (
  cmd /k ""%~f0" run"
  exit /b
)
setlocal EnableExtensions
title StudyMate launcher
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "VENV=%ROOT%.venv"
set "OLLAMA_MODEL=llama3.2"

echo ==================================================
echo   StudyMate - one-click setup and start
echo ==================================================
echo.

REM ---------- 1. Pick a compatible Python (3.11 - 3.13 preferred) ----------
set "PY="
for %%V in (3.13 3.12 3.11) do (
  if not defined PY (
    py -%%V --version >nul 2>&1
    if not errorlevel 1 set "PY=py -%%V"
  )
)
if not defined PY (
  python --version >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo [ERROR] No Python found. Install Python 3.12 from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  goto :fail
)
echo Using: 
%PY% --version
%PY% -c "import sys; sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,13) else 1)"
if errorlevel 1 (
  echo.
  echo [WARN] Your Python is outside 3.11-3.13. Some packages may fail to install.
  echo        If setup fails below, install Python 3.12 from python.org and run this file again.
  echo.
)

where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Node.js 20+ was not found. Install it from https://nodejs.org/ and run this file again.
  goto :fail
)

REM ---------- 2. Backend environment ----------
if exist "%VENV%\Scripts\python.exe" (
  "%VENV%\Scripts\python.exe" --version >nul 2>&1
  if errorlevel 1 (
    echo Existing .venv is broken, removing it...
    rmdir /s /q "%VENV%"
  )
)
if not exist "%VENV%\Scripts\python.exe" (
  echo [1/5] Creating Python virtual environment...
  %PY% -m venv "%VENV%"
  if errorlevel 1 goto :venvfail
) else (
  echo [1/5] Virtual environment found.
)
echo [2/5] Installing backend dependencies - this can take a few minutes the first time...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install --prefer-binary -r "%BACKEND%\requirements.txt"
if errorlevel 1 goto :pipfail
echo       Backend dependencies OK.
if not exist "%BACKEND%\.env" copy "%BACKEND%\.env.example" "%BACKEND%\.env" >nul

REM ---------- 3. Frontend dependencies ----------
if exist "%FRONTEND%\node_modules" goto :havenode
echo [3/5] Installing frontend dependencies - first run takes a minute...
cd /d "%FRONTEND%"
call npm install --no-audit --no-fund
if errorlevel 1 goto :npmfail
cd /d "%ROOT%"
goto :nodedone
:havenode
echo [3/5] Frontend dependencies found.
:nodedone

REM ---------- 4. Ollama (optional) ----------
echo [4/5] Checking Ollama - local language model...
where ollama >nul 2>&1
if errorlevel 1 goto :noollama
curl -s -o nul http://localhost:11434/api/tags
if errorlevel 1 (
  echo       Starting Ollama...
  start "Ollama" /min ollama serve
  timeout /t 5 /nobreak >nul
)
ollama list 2>nul | findstr /i /c:"%OLLAMA_MODEL%" >nul
if errorlevel 1 (
  echo       Downloading model %OLLAMA_MODEL% - one-time download, can take several minutes...
  ollama pull %OLLAMA_MODEL%
) else (
  echo       Model %OLLAMA_MODEL% is ready.
)
goto :startapp
:noollama
echo       Ollama is not installed. StudyMate will use its built-in offline fallback.
echo       For real AI answers install Ollama from https://ollama.com and run this file again.

:startapp
REM ---------- Desktop shortcut with the StudyMate icon (created once) ----------
if not exist "%USERPROFILE%\Desktop\StudyMate.lnk" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:USERPROFILE+'\Desktop\StudyMate.lnk'); $s.TargetPath='%ROOT%start_app.bat'; $s.WorkingDirectory='%ROOT%'; $s.IconLocation='%ROOT%frontend\public\icon.ico'; $s.Description='StudyMate - AI study assistant'; $s.Save()" >nul 2>&1
  if exist "%USERPROFILE%\Desktop\StudyMate.lnk" echo       Desktop shortcut "StudyMate" created.
)

REM ---------- 5. Start servers ----------
echo [5/5] Starting servers...
start "StudyMate Backend (port 8000)" /D "%BACKEND%" cmd /k ""%VENV%\Scripts\python.exe" -m uvicorn app.main:app_factory --factory --host 127.0.0.1 --port 8000"

set /a TRIES=0
:waitbackend
curl -s -o nul http://127.0.0.1:8000/api/health
if not errorlevel 1 goto :backendup
set /a TRIES+=1
if %TRIES% GEQ 90 goto :backendfail
timeout /t 1 /nobreak >nul
goto :waitbackend

:backendup
echo       Backend is up.
start "StudyMate Frontend (port 5173)" /D "%FRONTEND%" cmd /k "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort"
timeout /t 6 /nobreak >nul
start "" http://127.0.0.1:5173
echo.
echo ==================================================
echo   StudyMate is running:  http://127.0.0.1:5173
echo   API docs:              http://127.0.0.1:8000/docs
echo   Close the two server windows to stop the app.
echo ==================================================
goto :eof

:venvfail
echo [ERROR] Could not create the virtual environment.
goto :fail
:pipfail
echo.
echo [ERROR] Installing backend dependencies failed - see the messages above.
echo         Common fixes: check your internet connection; use Python 3.12 (python.org);
echo         if a package needs "Microsoft C++ Build Tools", you are on an unsupported Python version.
goto :fail
:npmfail
echo [ERROR] npm install failed - see the messages above.
goto :fail
:backendfail
echo [ERROR] The backend did not start. Look at the "StudyMate Backend" window for the error.
goto :fail

:fail
echo.
echo Setup stopped. Fix the problem above and run start_app.bat again.
