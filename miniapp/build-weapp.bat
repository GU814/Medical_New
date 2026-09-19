@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM 防御：部分精简环境缺少 APPDATA，会导致 npm-conf 崩溃（报 paths[0] undefined）
if not defined APPDATA set "APPDATA=%USERPROFILE%\AppData\Roaming"

echo ==========================================
echo  Taro 微信小程序构建脚本 (输出到 dist/)
echo ==========================================
echo.

REM 国内镜像，加速依赖下载（首次安装约 1500 个包，较慢属正常）
set REGISTRY=https://registry.npmmirror.com

echo [1/2] 安装依赖 ...
call npm install --legacy-peer-deps --no-audit --no-fund --registry=%REGISTRY%
if errorlevel 1 (
  echo.
  echo [失败] 依赖安装失败，请检查网络后重试。
  pause
  exit /b 1
)

echo.
REM 修补 ajv 版本错配：Taro 4.1.9 模板的 peer 冲突（webpack 版本不一致）被 --legacy-peer-deps
REM 放行后，会导致 ajv-keywords@5 错误 dedupe 到根目录的 ajv@6，编译时抛
REM   "Cannot find module 'ajv/dist/compile/codegen'"。把已存在的 ajv@8 嵌套到 ajv-keywords 下即可修复。
if not exist "node_modules\ajv-keywords\node_modules\ajv" (
  if exist "node_modules\schema-utils\node_modules\ajv" (
    mkdir "node_modules\ajv-keywords\node_modules" 2>nul
    xcopy /E /I /Y "node_modules\schema-utils\node_modules\ajv" "node_modules\ajv-keywords\node_modules\ajv" >nul 2>&1
    echo [修补] 已为 ajv-keywords 嵌套 ajv@8
  ) else (
    echo [提示] 未找到可用的 ajv@8，将直接尝试编译（若报 ajv 错误请手动处理）
  )
)

echo [2/2] 编译小程序 (taro build --type weapp) ...
call npm run build:weapp
if errorlevel 1 (
  echo.
  echo [失败] 编译失败，请查看上方日志。
  pause
  exit /b 1
)

echo.
if exist "dist\app.json" (
  echo [成功] 已生成 dist\app.json
  echo        现在回到微信开发者工具，点击顶部「编译」即可正常启动模拟器。
) else (
  echo [警告] 未找到 dist\app.json，请检查编译日志。
)
echo.
pause
