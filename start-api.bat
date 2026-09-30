@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM 以「小程序后端 API 模式」启动服务(DESKTOP_MODE=false 才会加载 app/ 下的 auth 等路由)
set DESKTOP_MODE=false

echo ============================================
echo  医学问诊智能体 - 小程序后端 API
echo  地址: http://127.0.0.1:8000
echo  健康检查: http://127.0.0.1:8000/healthz
echo  接口文档: http://127.0.0.1:8000/docs
echo ============================================
echo.
echo 未配置 WX_APPID/WX_SECRET 时,登录走 dev 模拟 openid,可本地联调。
echo 关闭此窗口即停止服务。
echo.

REM --host 0.0.0.0:同时监听局域网网卡,供手机真机联调(127.0.0.1 仍可正常访问)
".venv\Scripts\python.exe" -m uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000

pause
