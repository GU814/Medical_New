@echo off
chcp 65001 >nul 2>&1
setlocal

@echo ============================================================
@echo   医学问诊智能体 - 启动脚本（支持 Web / API 双模式）
@echo ============================================================
@echo.

REM ---------- 1. 检查 Python ----------
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请确保 Python 已安装并添加到 PATH
    pause
    exit /b 1
)

REM ---------- 2. 自动激活虚拟环境（若存在）----------
if exist ".venv\Scripts\activate.bat" (
    echo [信息] 检测到虚拟环境 .venv，正在激活...
    call ".venv\Scripts\activate.bat"
) else (
    echo [警告] 未检测到 .venv，将使用系统 Python（建议先运行 setup_offline.py 创建环境）
)

REM ---------- 3. 检查 Ollama（仅警告，不阻断）----------
where ollama >nul 2>nul
if %errorlevel% neq 0 (
    echo [警告] 未检测到 Ollama，模型调用可能失败
    echo   建议先运行: python setup_offline.py
) else (
    echo [信息] 检测到 Ollama 已安装
)

REM ---------- 4. 解析模式参数 / 交互菜单 ----------
set "MODE_ARG=%~1"
set "PORT_ARG=%~2"

if "%MODE_ARG%"=="" goto :MENU
if /i "%MODE_ARG%"=="web"     ( set "DESKTOP_MODE=true"  & set "MODE_NAME=Web 端（桌面模式）" & goto :CONFIG )
if /i "%MODE_ARG%"=="desktop" ( set "DESKTOP_MODE=true"  & set "MODE_NAME=Web 端（桌面模式）" & goto :CONFIG )
if /i "%MODE_ARG%"=="api"     ( set "DESKTOP_MODE=false" & set "MODE_NAME=API 模式（小程序后端）" & goto :CONFIG )
if /i "%MODE_ARG%"=="miniapp" ( set "DESKTOP_MODE=false" & set "MODE_NAME=API 模式（小程序后端）" & goto :CONFIG )
echo [错误] 未知参数: %MODE_ARG%
goto :USAGE

:MENU
echo 请选择启动模式：
echo   1) Web 端   - 桌面模式，浏览器打开聊天界面（http://127.0.0.1:8000）
echo   2) API 模式 - 小程序后端，提供接口服务（http://localhost:8000/docs）
echo.
set /p choice="请输入 1 或 2（默认 1）: "
if "%choice%"=="2" (
    set "DESKTOP_MODE=false"
    set "MODE_NAME=API 模式（小程序后端）"
) else (
    set "DESKTOP_MODE=true"
    set "MODE_NAME=Web 端（桌面模式）"
)

:CONFIG
REM 端口：可用第二个参数或 SERVER_PORT 环境变量覆盖
if not "%PORT_ARG%"=="" set "SERVER_PORT=%PORT_ARG%"

REM 根据模式决定访问地址提示
if "%DESKTOP_MODE%"=="true" (
    set "ACCESS_URL=http://127.0.0.1:8000"
) else (
    set "ACCESS_URL=http://localhost:8000/docs  （接口文档）"
)

@echo.
@echo ------------------------------------------------------------
@echo   启动模式  : %MODE_NAME%
@echo   访问地址  : %ACCESS_URL%
if defined SERVER_PORT (
    @echo   服务端口  : %SERVER_PORT%
)
@echo   按 Ctrl+C 停止服务
@echo ------------------------------------------------------------
@echo.

REM ---------- 5. 启动 ----------
python main.py
set "EXIT_CODE=%errorlevel%"

if %EXIT_CODE% neq 0 (
    echo.
    echo [错误] 程序启动失败（退出码 %EXIT_CODE%），请检查上方日志
    echo   若提示缺少依赖，请运行: pip install -r requirements.txt
    echo   若需离线模型，请运行: python setup_offline.py
    pause
)
endlocal
exit /b %EXIT_CODE%

:USAGE
@echo.
@echo 用法:
@echo   start.bat                进入交互菜单选择模式
@echo   start.bat web            Web 端（桌面模式，浏览器聊天界面）
@echo   start.bat api            API 模式（小程序后端）
@echo   start.bat web 8080       指定端口（Web 端，端口 8080）
@echo.
pause
exit /b 1
