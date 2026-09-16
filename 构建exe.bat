@echo off
chcp 936 >nul
cd /d "%~dp0"
title 构建「文档转 Markdown」exe

echo ==========================================================
echo   把「文档转 Markdown」打包成单个 exe
echo   产物： dist\MarkItDownUI.exe
echo ==========================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 找不到 .venv 虚拟环境。
    echo        请先创建环境并安装依赖：
    echo          python -m venv .venv
    echo          .venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [提示] 尚未安装 PyInstaller，正在安装...
    ".venv\Scripts\python.exe" -m pip install pyinstaller
    echo.
)

echo [1/2] 清理上次产物...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo [2/2] 开始打包（首次约 2-5 分钟，请勿关闭窗口）...
echo.
".venv\Scripts\python.exe" -m PyInstaller MarkItDownUI.spec --noconfirm

if errorlevel 1 (
    echo.
    echo [失败] 打包出错，请查看上方日志。
    pause
    exit /b 1
)

if not exist "dist\MarkItDownUI.exe" (
    echo.
    echo [失败] 未生成 dist\MarkItDownUI.exe。
    pause
    exit /b 1
)

echo.
echo [完成] 产物： dist\MarkItDownUI.exe
for %%A in ("dist\MarkItDownUI.exe") do echo        体积： %%~zA 字节
echo.
echo 该 exe 可单独复制到其它 Windows 电脑（64 位）直接运行，无需安装 Python。
echo.
pause
