@echo off
echo.
echo Launching Chrome in Remote Debugging Mode...
echo ------------------------------------------
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
echo ✅ Port 9222 is now active. 
echo ✅ You can now run 'python jarvis_browser.py' to control this window.
echo.
pause
