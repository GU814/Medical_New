# 微信开发者工具报错「dist/app.json 未找到」排查手册

> 报错原文
> `[ app.json 文件内容错误] dist/app.json: 根据 project.config.json 中 miniprogramRoot
> 指定的小程序目录 dist/，在该目录下未找到 app.json。`
>
> 环境：Windows / 开发者工具 2.02.2609231 / 基础库 3.17.3 / Taro 4.1.9

---

## 一、结论速览

**`miniprogramRoot` 配置本身是正确的，不需要改。**

真正原因是 `miniapp/dist/` 里**缺少应用入口三件套** `app.js` / `app.json` / `app.wxss`——
那份 `dist/` 是一份**构建到一半被中断的产物**，不是完整的小程序包。
重新完整构建一次即可，约 30 秒。

---

## 二、本项目的实际情况（取证）

`miniapp/dist/` 修复前的实际内容：

| 文件 | 存在 | 说明 |
|---|---|---|
| `app.js` / `app.json` / `app.wxss` | ❌ | **应用入口，缺失** |
| `taro.js` / `vendors.js` / `runtime.js` | ✅ | 运行时打包产物 |
| `pages/` | ⚠️ 残缺 | 只有 6 个文件，`pages/records/` 缺 `.js` / `.json` |
| 其余（`project.config.json`、`utils.wxs` 等）| ✅ | |

两个关键证据：

1. **`pages/records/` 有 `.wxml` / `.wxss` 却没有 `.js` / `.json`。**
   正常的「编译报错」不会只丢 js/json——`wxml`/`wxss` 都写盘成功了，偏偏 js/json 没有，
   说明**写盘过程是被外力打断的**。
2. **时间戳停在 2026-09-28 14:36**，与「上一轮后台构建被中断」的时刻吻合。

对照物：`miniapp/_dist_old2_1789783732/` 里 `app.js` / `app.json` / `app.wxss` 齐全，
那是上一次**成功**构建的产物——进一步印证本次构建没走到应用入口就断了。

源码侧完全正常，`src/app.tsx` 与 `src/app.config.ts` 都在，编译没有报错。

---

## 三、影响因素梳理

| # | 可能因素 | 是否是本次原因 | 如何自行判定 |
|---|---|---|---|
| 1 | `miniprogramRoot` 路径写错 | ❌ | 本项目是 `"dist/"`，相对 `project.config.json` 所在目录即 `miniapp/dist/`，正确 |
| 2 | 构建未完成 / 产物残缺 | ✅ **是** | `ls dist/` 里没有 `app.json` 即为此 |
| 3 | 构建进程被中断（强杀、超时 kill、并发抢写）| ✅ **是（诱因）** | 页面目录只缺 `.js`/`.json` 却留下 `.wxml`/`.wxss` |
| 4 | 打开的目录不对（打开到项目根而非 `miniapp/`）| ⚠️ 需排除 | 项目根 `medical_bot/dist/` 是 PyInstaller 产物，与小程序无关 |
| 5 | `app.json` 被 `.gitignore` / 打包忽略 | ❌ | 本项目 `miniapp/.gitignore` 只忽略了 `node_modules` |
| 6 | `app.config.ts` 源码缺失或语法错误 | ❌ | `src/app.config.ts` 存在，且编译日志 `Compiled successfully` |
| 7 | `outputRoot` 被环境变量改写 | ❌ | `TARO_OUTPUT_DIR` 未设置，`outputRoot` 回落为 `dist` |
| 8 | 微信开发者工具缓存 / 基础库异常 | ❌ | 产物缺失属于文件层面的问题，清缓存解决不了 |

> 记住：**这条报错 95% 的情况不是路径配错，而是 `app.json` 没被构建出来。**
> 先确认 `dist/app.json` 在不在，再去怀疑配置。

---

## 四、排查步骤（按顺序执行）

**Step 1 — 确认开发者工具打开的目录**

应该是 `...\medical_bot\miniapp`，而不是项目根 `...\medical_bot`。

**Step 2 — 看产物里有没有应用入口**

```bash
ls miniapp/dist/
```

- 有 `app.js` / `app.json` / `app.wxss` → 不是产物问题，转 Step 5（清缓存 / 查目录）
- 三者缺一 → 转 Step 3

**Step 3 — 看是不是构建残缺，并找源码对照**

```bash
ls miniapp/dist/app.* 2>&1                       # 预期：三个都没有
ls miniapp/src/app.tsx miniapp/src/app.config.ts # 预期：两个都在
```

源码在、产物不在 ⇒ 确认是**构建没跑完**。

**Step 4 — 干净重建**

```powershell
# 用 PowerShell 执行（bash 下 npm 会被安全策略拦截）
$env:APPDATA = "C:\Users\lenovo\AppData\Roaming"
Set-Location "C:\Users\lenovo\Desktop\作品集\medical_bot\miniapp"
& "D:\New Folder\npm.cmd" run build:weapp
```

成功标志：`Compiled successfully in XX s` 且 `BUILD_EXIT=0`。

**Step 5 — 校验产物完整性**

```bash
ls miniapp/dist/app.json          # 必须存在
ls miniapp/dist/pages/*/index.js  # 所有页面都要有
```

**Step 6 — 若仍报错，再清开发者工具缓存**

详情 → 本地设置 → 清除缓存 → 重新编译。

---

## 五、修复执行记录（本次）

| 步骤 | 结果 |
|---|---|
| 隔离残缺产物 `mv miniapp/dist _dist_broken_1790600494` | 完成 |
| 重新构建 | `Compiled successfully in 26.86s`，`BUILD_EXIT=0`，耗时 33s |
| `dist/app.json` | ✅ 1165 字节，声明 9 个页面 |
| `app.js` / `app.wxss` | ✅ 97490 / 344 字节 |
| 文件总数 | 60 |
| 9 个页面的 js/json/wxml | ✅ 全部齐全（含此前残缺的 `pages/records`） |

`dist/app.json` 声明的 9 个页面：
`index` / `consult` / `records` / `profile` / `login` / `recordDetail` / `privacy` / `location` / `share`

---

## 六、注意事项

- **构建前先把旧 `dist` 挪走**，不要让它留在原地。残缺产物会污染本次写入，
  也会让下次排查时误以为「构建过」。
- **不要在构建过程中杀进程**。写到一半被 kill，`dist/` 就会被永久留在残缺状态。
- 目录里累积的 `_dist_old2_*`、`_dist_broken_*` 是 Taro 备份 / 本次隔离的历史产物，
  确认新构建正常后可以删除（当前剩余：`_dist_broken_1790600494`、`_dist_old2_1789783732`）。
- 改了 `miniapp/src` 之后必须重新构建，开发者工具打开的是 `dist/`，不是 `src/`。
