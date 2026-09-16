@echo off
title 文档转 Markdown 工具
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" goto nopy
if not exist "%~dp0ui.py" goto nofile

echo 正在启动「文档转 Markdown 工具」...
echo.
"%PY%" "%~dp0ui.py"
if errorlevel 1 goto failed
exit /b 0

:nopy
echo [错误] 未找到虚拟环境中的 Python 解释器：
echo        %PY%
echo.
echo 请先在本目录执行以下命令完成环境安装：
echo        python -m venv .venv
echo        .venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
pause
exit /b 1

:nofile
echo [错误] 未找到程序主文件 ui.py，请确认本脚本与 ui.py 位于同一目录。
echo.
pause
exit /b 1

:failed
echo.
echo [错误] 程序启动失败，请查看上方错误信息。
echo.
pause
exit /b 1
