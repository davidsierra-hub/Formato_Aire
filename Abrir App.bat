@echo off
cd /d "%~dp0"
echo ========================================
echo   AIR-E Cumplimiento - Iniciando...
echo   NO CIERRES ESTA VENTANA
echo ========================================
echo.

REM Abrir navegador despues de 7 segundos en segundo plano
start /b cmd /c "timeout /t 7 /nobreak >nul && start http://localhost:8501"

REM Iniciar Streamlit (mantiene esta ventana abierta)
python -m streamlit run app.py --server.port 8501 --browser.gatherUsageStats false --server.headless true --browser.serverAddress localhost
