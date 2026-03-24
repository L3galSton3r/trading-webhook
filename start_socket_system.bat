@echo off
title Socket Server (NEW SYSTEM - Port 9091)
echo ========================================
echo Starting Socket-Based Signal Server
echo (NEW SYSTEM - Testing Mode)
echo ========================================
echo.
echo Flask webhook: http://localhost:9091
echo Socket server: localhost:9090
echo.
cd /d "C:\Users\mario\Documents\trading-webhook"
python socket_server.py
pause