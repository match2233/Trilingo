@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  Trilingo 调试启动 (保留控制台, 显示日志)
echo ============================================
echo.

rem 优先用 pythonw 的同一目录下的 python.exe；找不到就退回 PATH 里的 python
set "PYEXE=python"
where pythonw.exe >nul 2>nul && for /f "delims=" %%i in ('where pythonw.exe') do (
    if exist "%%~dpi\python.exe" set "PYEXE=%%~dpi\python.exe"
)

echo 使用解释器: %PYEXE%
"%PYEXE%" "Trilingo.pyw"

echo.
echo ---- 程序已退出 ----
echo 详细日志: trilingo.log
pause
