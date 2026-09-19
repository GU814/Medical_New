@echo off
@echo ====================================
@echo  医学问诊智能体 - 离线环境设置
@echo ====================================
@echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请确保 Python 已安装并添加到环境变量
    pause
    exit /b 1
)

echo [信息] 正在启动离线环境设置...
echo [信息] 这可能需要一些时间，请耐心等待

echo.
python setup_offline.py

if %errorlevel% equ 0 (
    echo.
    echo [成功] 离线环境设置完成！
    echo 现在可以运行 start.bat 启动医学问诊智能体
) else (
    echo.
    echo [错误] 设置过程中出现问题，请检查错误信息
)

pause