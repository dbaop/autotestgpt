@echo off
echo ========================================
echo AutoTestGPT 启动脚本
echo ========================================
echo.

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python未安装或未添加到PATH
    pause
    exit /b 1
)

REM 检查虚拟环境
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

REM 安装Playwright
echo [INFO] 安装Playwright浏览器...
playwright install chrome

REM 初始化数据库
echo [INFO] 初始化数据库...
python init_db.py

REM 启动服务
echo [INFO] 启动AutoTestGPT服务...
echo [INFO] 服务地址: http://localhost:8000
echo [INFO] API文档: http://localhost:8000
echo.

python main.py

pause