@echo off
echo ===================================================
echo               Analytics Foundry Start
echo ===================================================
echo.

if exist .venv\Scripts\activate.bat (
    echo Activating virtual environment .venv...
    call .venv\Scripts\activate.bat
    goto :venv_done
)
if exist venv\Scripts\activate.bat (
    echo Activating virtual environment venv...
    call venv\Scripts\activate.bat
    goto :venv_done
)
:venv_done

echo Ensuring API dependencies are installed...
python -m pip install -e ".[api]"

echo Starting the Uvicorn server in a new window...
start "Analytics Foundry Server" cmd /k "python -m uvicorn analytics_foundry.api:app --host 127.0.0.1 --port 8000 --reload"

echo Waiting for the server to spin up...
ping 127.0.0.1 -n 4 >nul

echo Launching browser to http://127.0.0.1:8000/admin...
start http://127.0.0.1:8000/admin

echo.
echo Analytics Foundry is running!
echo Keep the server console window open. You can close this window.
ping 127.0.0.1 -n 6 >nul
