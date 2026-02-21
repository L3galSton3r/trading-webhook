@echo off
echo ========================================
echo   TRADING WEBHOOK - DEPLOY TO RENDER
echo ========================================
echo.

echo [1/4] Adding changes...
git add .

echo.
echo [2/4] Committing...
set /p commit_msg="Enter commit message (or press Enter for default): "
if "%commit_msg%"=="" set commit_msg=Update webhook code

git commit -m "%commit_msg%"

echo.
echo [3/4] Pushing to GitHub...
git push origin main

echo.
echo [4/4] Done!
echo.
echo Render will auto-deploy in 30-60 seconds.
echo Check: https://dashboard.render.com/
echo.
pause