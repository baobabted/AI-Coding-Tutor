@echo off
chcp 65001 >nul 2>&1
title Guided Cursor - Startup
cd /d "%~dp0"

echo.
echo  ============================================
echo   Guided Cursor: AI Coding Tutor
echo  ============================================
echo.

:: 1. Start database + backend via docker-compose
echo  [1/4] Starting database and backend...
start "Guided Cursor - Backend" cmd /c "docker-compose up --build db backend"

:: 2. Wait for backend health check
echo  [2/4] Waiting for backend to be ready...
set ATTEMPTS=0
set MAX_ATTEMPTS=60

:health_loop
set /a ATTEMPTS+=1
if %ATTEMPTS% gtr %MAX_ATTEMPTS% (
    echo.
    echo  ERROR: Backend did not start within 60 seconds.
    echo  Check the Backend window for errors.
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost:8000/health | findstr "200" >nul 2>&1
if errorlevel 1 (
    <nul set /p "=."
    goto health_loop
)

echo.
echo  Backend is ready!
echo.

:: 3. Start frontend dev server
echo  [3/4] Starting frontend...
start "Guided Cursor - Frontend" /d "%~dp0frontend" cmd /c "npm install && npm run dev"

:: 4. Wait for Vite to start, then open browser
echo  [4/4] Waiting for frontend to start...
set FATTEMPTS=0

:frontend_loop
set /a FATTEMPTS+=1
if %FATTEMPTS% gtr %MAX_ATTEMPTS% (
    echo.
    echo  ERROR: Frontend did not start within 60 seconds.
    echo  Check the Frontend window for errors.
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost:5173 | findstr "200" >nul 2>&1
if errorlevel 1 (
    <nul set /p "=."
    goto frontend_loop
)
echo.
echo  Frontend is ready!
start http://localhost:5173

echo.
echo  ============================================
echo   All services running!
echo  --------------------------------------------
echo   Frontend : http://localhost:5173
echo   Backend  : http://localhost:8000
echo  --------------------------------------------
echo   To stop: close the Backend and Frontend
echo            command windows.
echo  ============================================
echo.
timeout /t 5 /nobreak >nul
