# 医学问诊智能体 · 界面原型（纯前端）

用于**先确认页面结构、布局排列和交互效果**的静态原型。不含后端、数据库与鉴权，全部数据写死在本地。

## 简约 Demo 页（demo.html）

单页产品展示版，适合快速演示：产品简介 + **能力概览**（5 大类 × ✅/⚠️/❌ 实现度，数据与
《微信能力对标核查与实施计划.md》一致）+ 3 个轻量交互示例（**智能问诊对话**、**结构化报告预览**、**分享中心**）。

- 入口：`demo.html`（双击即可打开，同样零依赖零构建）；
- 样式完全复用 `assets/css/`，图标复用 `assets/js/core/dom.js`；
- 页面逻辑集中在 `assets/js/demo-page.js`（含模拟数据，接真实接口时替换即可）。

## 运行方式

**方式一（推荐）**：直接双击 `index.html`，浏览器打开即可。

**方式二**：若浏览器对 `file://` 有限制，在项目目录起一个静态服务：

```bash
cd demo-web
python -m http.server 8080
# 然后访问 http://localhost:8080
```

无需 npm install，无需构建。

---

## 目录结构

```
demo-web/
├── index.html                     # 唯一入口，按序加载脚本
├── README.md
└── assets/
    ├── css/
    │   ├── variables.css          # 设计变量（配色 / 圆角 / 尺寸）—— 换肤改这里
    │   ├── base.css               # 重置、文字层级、按钮、表单、开关、图标
    │   ├── layout.css             # 侧边导航 + 顶栏 + 主内容区 + 响应式断点
    │   └── components.css         # 卡片、表格、空态、骨架、弹窗、抽屉、对话气泡等
    └── js/
        ├── core/
        │   ├── dom.js             # 工具集：转义 / 查询 / 事件委托 / 图标 / 格式化
        │   └── router.js          # 哈希路由（支持 /records/:id 与 ?kw= 查询）
        ├── data/
        │   └── mock.js            # 全部模拟数据 —— 接后端后整层删除
        ├── api/
        │   └── index.js           # 接口占位层 ★接后端只改这一个文件★
        ├── components/
        │   ├── ui.js              # 页头、卡片、统计卡、表格、空态、骨架、分页、图表
        │   ├── overlay.js         # 弹窗、抽屉、Toast、确认框
        │   └── layout.js          # 侧边导航、顶栏渲染与骨架事件
        ├── pages/                 # 每个页面一个文件
        │   ├── dashboard.js       # 概览
        │   ├── consult.js         # 智能问诊（对话）
        │   ├── records.js         # 问诊记录（列表）
        │   ├── record-detail.js   # 记录详情
        │   ├── profile.js         # 个人中心（表单）
        │   ├── share.js           # 分享中心
        │   └── settings.js        # 设置
        └── app.js                 # 启动：定义导航 → 注册路由 → 渲染骨架
```

---

## 页面清单

| 路由 | 页面 | 主要元素 | 演示的交互 |
|---|---|---|---|
| `#/dashboard` | 概览 | 统计卡 ×4、趋势条形图、快捷入口卡、最近记录列表 | 骨架屏、卡片 hover、列表跳转、刷新 |
| `#/consult` | 智能问诊 | 5 阶段指示器、对话气泡、快捷提问 chip、输入区、免责声明 | 发送消息、「正在输入」占位、阶段切换、清空确认 |
| `#/records` | 问诊记录 | 搜索框、状态分段筛选、数据表格、分页、行操作 | 骨架屏、空数据提示、删除确认弹窗、筛选抽屉（移动端） |
| `#/records/:id` | 记录详情 | 患者信息卡、要点 chip、主诉卡、结构化报告、操作栏 | 加载占位、返回、导出提示、分享弹窗、小程序码弹窗 |
| `#/profile` | 个人中心 | 头像卡、KV 信息、基本信息表单、健康档案、开关 | 表单校验、保存中禁用、Toast、重置 |
| `#/share` | 分享中心 | 分享链接列表、有效期/访问数、复制/二维码/撤销 | 空态、新建弹窗、复制 Toast、撤销确认 |
| `#/settings` | 设置 | 开关分组、密度分段控件、会员方案卡、关于 | 开关即时保存、密度切换、升级弹窗 |

---

## 响应式断点

| 断点 | 表现 |
|---|---|
| ≥ 1100px | 左侧固定导航（236px）+ 顶栏 + 主内容 |
| 760–1100px | 侧栏收窄为图标条（72px） |
| < 760px | 侧栏变为抽屉（顶栏汉堡按钮唤起 + 遮罩），搜索隐藏，间距收紧 |

---

## 接入真实后端（三步）

### 1. 改基址
`assets/js/api/index.js` 顶部：
```js
App.api.base = 'https://api.your-domain.com';
App.api.usingMock = false;
```

### 2. 逐个替换函数
该文件里每个函数都写明了对应的真实接口，例如：

| 占位函数 | 真实接口 |
|---|---|
| `getOverview()` | `GET /api/overview` |
| `createSession()` | `POST /api/sessions` |
| `sendMessage(sessionId, text)` | `POST /api/chat`（SSE 流式） |
| `listRecords(params)` | `GET /api/records?page=1&size=10&keyword=&status=` |
| `getRecord(id)` | `GET /api/records/{id}` |
| `deleteRecord(id)` | `DELETE /api/records/{id}` |
| `exportRecordPdf(id)` | `GET /api/records/{id}/export?format=pdf` |
| `getProfile()` / `saveProfile()` | `GET /auth/me` / `PUT /auth/profile` |
| `listShareLinks()` / `createShare()` / `revokeShare()` | `GET /api/share/list`、`POST /api/share`、`DELETE /api/share/{token}` |
| `getSettings()` / `saveSettings()` | `GET /api/settings` / `PUT /api/settings` |
| `listPlans()` / `subscribePlan()` | `GET /api/plans` / `POST /api/orders` |

文件里已预留 `App.api.request()` 模板（含鉴权头位置），打开注释即可使用。

### 3. 删除模拟数据层
删掉 `assets/js/data/mock.js` 与 `index.html` 中对应的一行 `<script>`。

**关键约束**：页面层不允许直接引用 `App.mock`，一律走 `App.api.*`。替换后端时改动面就只有那一个文件。

---

## 新增一个页面

1. 在 `assets/js/pages/` 新建文件，导出对象：
   ```js
   App.pages.xxx = {
     path: '/xxx', title: '新页面', icon: 'star', group: '工作台',
     render: function (params) { return '<骨架 HTML>'; },   // 同步
     mount:  function (root, params) { /* 取数 + 绑定事件 */ }  // 异步
   };
   ```
2. 在 `app.js` 的 `ORDER` 数组里加上 `'xxx'`；
3. 若需在侧边导航显示，在 `App.nav` 里加一项。

---

## 说明

- 所有插入 `innerHTML` 的动态文本都经过 `App.esc()` 转义；
- 图标为内联 SVG，无字体依赖、无网络请求；
- 弹窗/抽屉支持 ESC 与点遮罩关闭，打开时锁定页面滚动；
- 骨架屏动画在 `prefers-reduced-motion` 下自动关闭。
