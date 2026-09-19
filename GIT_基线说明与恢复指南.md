# medical_bot 仓库基线与恢复指南

仓库根：`C:\Users\lenovo\Desktop\作品集\medical_bot`
初始化时间：2026-09-19

---

## 一、为什么要做这件事

在此之前，这个目录**根本不是 Git 仓库**（只有一份 `.gitignore`），而它内部的
`miniapp/.git` 是独立的、**至今 0 个 commit**。也就是说这几天新增的所有内容
（demo-web 原型、两份报告、后端与小程序代码修改）**完全无法回退**。

现在已补上版本管理。

---

## 二、提交结构（关键设计）

刻意分成两个 commit，让你能直接回到「新增内容之前」：

| commit | 说明 | 内容 |
|---|---|---|
| **`88d4883`** | `chore: 初始化仓库基线（demo-web 原型之前的项目状态）` | 155 个文件：app/、miniapp/src/、static/、training/、data/knowledge、根目录 .py 与文档 |
| **`381a517`** | `feat: 新增纯前端原型 demo-web 与两份核查报告` | 23 个文件：demo-web/（21）+ 小程序上传部署检查报告.md + 微信能力对标核查与实施计划.md |

分支与标签：

| 名称 | 指向 | 用途 |
|---|---|---|
| `main` | `381a517` | 主线 |
| `feat-demo-web-prototype`（当前所在） | `381a517` | 原型后续迭代用这个分支 |
| 标签 `before-demo-web` | `88d4883` | 语义化的「改动前」锚点 |

> 分支名用 `feat-` 而不是 `feat/`：本机 git 在带斜杠的引用上执行提交时会把该引用删掉
> （详见第五节），为了能正常在这个分支上继续提交，这里改用连字符。

> ⚠️ 说明：`88d4883` 只排除了 demo-web 与两份报告。
> `consultation.py` / `config.py` / `app/core/crypto.py` / `miniapp/src/**` 的修改
> 在此之前就已落盘且无从还原，因此它们被包含在基线 commit 里 —— 这是唯一无法补救的部分。

---

## 三、常用命令

### 回到「新增 demo-web 之前」的版本

```bash
cd C:/Users/lenovo/Desktop/作品集/medical_bot

# 方式一：只查看/临时切换（推荐）
git switch --detach before-demo-web      # 工作区回到基线状态，demo-web 会暂时消失
git switch feat/demo-web-prototype       # 切回来，demo-web 恢复

# 方式二：只把某个目录还原到基线
git checkout before-demo-web -- demo-web
```

### 对比两个版本

```bash
git diff before-demo-web HEAD --stat      # 看改了哪些文件
git diff before-demo-web HEAD             # 看具体内容
```

### 撤销新增内容（保留历史记录，推荐用于协作场景）

```bash
git switch main
git revert --no-commit 381a517            # 生成一个「反向」改动
git commit -m "revert: 回退 demo-web 原型与两份报告"
```

### 彻底丢弃（本地私有分支才用）

```bash
git switch main
git reset --hard before-demo-web          # main 直接指回基线
```

---

## 四、初始化时做的处理（避免踩坑）

1. **搁置了嵌套空仓库** `miniapp/.git` → 改名为 `miniapp/.git_empty_backup`。
   它 0 commit、0 对象、无远程，搁置无任何损失；不处理的话外层仓库无法跟踪
   `miniapp/src`（git 会把它当成嵌套仓库/子模块）。
   需要还原就改回名字即可。

2. **补了 `.gitignore`**：新增 `python_embed/`、`.pai/`、`.idea/`、`.workbuddy/`、
   `node_modules/`、`miniapp/node_modules_bak/`、`miniapp/_dist_old*/`、
   `miniapp/.git_empty_backup/`、`*.log`。

3. **核验结果**：共 178 个文件入库；`.env`、`python_embed`、`node_modules`、
   `.venv`、`data/chroma_db`、`data/medical.db`、`data/.dev_master_key`
   均确认**未被跟踪**（计数全为 0）。

---

## 五、本环境的 Git 坑（两个仓库都遇到）

这台机器上 **带斜杠的引用（`feat/xxx`、`backup/xxx`）不可靠**，实测有三种坏法：

1. `git branch feat/xxx <hash>` / `git tag backup/xxx <hash>` → **exit 0 但引用根本没被创建**（静默失败）；
2. 手动写入引用后 `git switch` 能成功，但**一旦在该分支上执行 `git commit`，
   引用文件会被整个删掉**，只剩 `.git/logs/refs/heads/feat/` 的空 reflog；
3. 随后报 `fatal: invalid reference` 或 `does not have any commits yet`，
   让人误以为提交丢了（其实工作区和 index 都还在，用 `git symbolic-ref HEAD refs/heads/main` 即可复位）。

**结论：本仓库一律使用扁平分支名（`feat-xxx`、`backup-xxx`）。**

若确实需要 `feat/xxx` 这样的名字（例如要与远端规范对齐），手动创建方式如下 ——
但**不要在该分支上 commit**：

```bash
mkdir -p .git/refs/heads/feat
git rev-parse <hash> > .git/refs/heads/feat/<branch-name>
```

诊断时请用 `git show-ref` 看真实引用，**不要相信 exit code**。

---

## 六、另一个仓库（如同样需要）

`C:\Users\lenovo\Desktop\mdeicla\medical-agent` 已于同日完成分支隔离：
`main` 回退到 `c76411b`，新增内容保留在 `feat/merge-medical-new-license`(`98914b8`)
及标签 `backup/main-before-reset-20260919`，详见该仓库的 `GIT_恢复指南.md`。
