@echo off
echo ========================================
echo AutoTestGPT 简易启动脚本
echo ========================================
echo.

REM 检查Python
python --version
if errorlevel 1 (
    echo [ERROR] Python未安装或未添加到PATH
    pause
    exit /b 1
)

REM 创建虚拟环境（如果不存在）
if not exist ".venv\" (
    echo [INFO] 创建虚拟环境...
    python -m venv .venv
)

REM 激活虚拟环境
echo [INFO] 激活虚拟环境...
call .venv\Scripts\activate.bat

REM 安装依赖
echo [INFO] 安装依赖...
pip install -r requirements.txt

REM 创建工作空间目录
echo [INFO] 创建工作空间目录...
mkdir workspace 2>nul
mkdir workspace\logs 2>nul
mkdir workspace\scripts 2>nul
mkdir workspace\temp 2>nul
mkdir report 2>nul
mkdir report\html 2>nul
mkdir report\json 2>nul

REM 启动服务
echo [INFO] 启动AutoTestGPT服务...
echo [INFO] 服务地址: http://localhost:8000
echo [INFO] 按Ctrl+C停止服务
echo.

python main.py

pause