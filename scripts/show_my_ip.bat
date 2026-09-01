@echo off
echo Deine IPv4-Adressen:
ipconfig | findstr /i "IPv4"
echo.
echo Beispiel Browser-Adresse im WLAN: http://DEINE-IP:5050
pause
