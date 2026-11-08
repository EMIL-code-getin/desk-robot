@echo off
rem Windows: double-click. Starts the offline library and opens the portal.
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set PORT=8090
echo.
echo  ============================================
echo    OFFLINE-BIBLIOTEK  (Wikipedia med mera)
echo  ============================================
echo  Ett uppslagsverk, inte en ersattning for 112 eller varden.
echo.
set ZIMS=
set COUNT=0
for %%f in ("library\*.zim") do (
  set ZIMS=!ZIMS! "%%~nxf"
  set /a COUNT+=1
)
if !COUNT!==0 (
  echo  Inga .zim-filer i library\. Nodkorten fungerar anda.
  start "" "%~dp0portal\index.html"
  pause
  exit /b
)
if not exist "kiwix\win\kiwix-serve.exe" (
  echo  kiwix\win\kiwix-serve.exe saknas. Nodkorten oppnas anda.
  start "" "%~dp0portal\index.html"
  pause
  exit /b 1
)
rem An earlier start that never shut down still holds the port.
taskkill /f /im kiwix-serve.exe >nul 2>&1
rem Run inside library\ with bare file names: kiwix-serve names each book after the file.
rem Windows asks once whether to allow it on the network: Allow lets phones connect.
start "Offline-bibliotek" /min /d "%~dp0library" "%~dp0kiwix\win\kiwix-serve.exe" --port %PORT% !ZIMS!
timeout /t 3 /nobreak >nul
echo  Bibliotek: !COUNT! arkiv pa http://localhost:%PORT%/
echo  Fran en mobil pa samma wifi eller hotspot, nagon av:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do for /f "tokens=*" %%b in ("%%a") do echo     http://%%b:%PORT%/
start "" "%~dp0portal\index.html"
echo.
echo  Lat det har fonstret vara oppet. Tryck en tangent for att stanga biblioteket.
pause >nul
taskkill /f /im kiwix-serve.exe >nul 2>&1
