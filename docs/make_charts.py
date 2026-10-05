# -*- coding: utf-8 -*-
"""测试数据可视化 —— 医疗问诊智能体 PPT 配图
数据来源：_bench/_bench2/_bench3/_bench4 实测输出、pytest 实测（77 passed）、
knowledge_base.py / react/loop.py / react/tools.py 中的实测注释。
风格：浅蓝 + 白 + 深蓝，浅色调、去 AI 化。
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 100

# 配色（与 PPT 一致）
DEEP = "#0F3D6E"
BLUE = "#2E7FC4"
LBLUE = "#DDEAF7"
TEAL = "#1F9E8E"
GREY = "#6B7A8C"
TEXT = "#22334A"
WARN = "#C06A2B"
BG = "#FFFFFF"

OUT = r"C:\Users\lenovo\Desktop\作品集\medical_bot\docs\charts"
os.makedirs(OUT, exist_ok=True)


def style_ax(ax):
    ax.set_facecolor(BG)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#C9DAEC")
    ax.tick_params(colors=TEXT, labelsize=10)
    ax.grid(axis="y", color="#E8F0F8", linewidth=0.9)
    ax.set_axisbelow(True)


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print("saved:", path)


# =====================================================================
# 图 1：模型单轮响应耗时实测（deepseek-r1:8b 14 次采样 + qwen2.5:7b 对比）
# =====================================================================
ds = [25.71, 64.34, 32.19, 64.09, 32.51, 38.32, 40.67, 54.34, 63.67, 64.80,
      43.54, 30.95, 34.18, 30.64]
fig, ax = plt.subplots(figsize=(7.6, 3.5))
x = np.arange(len(ds))
bars = ax.bar(x, ds, width=0.62, color=LBLUE, edgecolor=BLUE, linewidth=1.1, zorder=3)
avg = np.mean(ds)
ax.axhline(avg, color=WARN, linestyle="--", linewidth=1.4, zorder=4)
ax.text(len(ds)-0.4, avg+1.2, f"均值 {avg:.1f}s", color=WARN, fontsize=10.5,
        ha="right", fontweight="bold")
# qwen2.5:7b 参考带
ax.axhspan(2.5, 15, color=TEAL, alpha=0.10, zorder=1)
ax.axhline(15, color=TEAL, linestyle=":", linewidth=1.4, zorder=4)
ax.text(0.1, 15.6, "qwen2.5:7b 问诊单轮 2.5~15s（切换后）", color=TEAL, fontsize=10.5,
        fontweight="bold")
style_ax(ax)
ax.set_xlabel("deepseek-r1:8b 实测轮次（14 次采样）", fontsize=10.5, color=TEXT)
ax.set_ylabel("单轮总耗时（秒）", fontsize=10.5, color=TEXT)
ax.set_ylim(0, 72)
ax.set_title("切换指令模型前后：单轮问诊响应耗时对比", fontsize=13, color=DEEP,
             fontweight="bold", pad=10)
save(fig, "1_model_latency.png")

# =====================================================================
# 图 2：知识库分块质量对比（heading vs legacy）
# =====================================================================
fig, ax = plt.subplots(figsize=(7.6, 3.4))
strategies = ["旧「装箱」策略\nlegacy", "新「## 主题」策略\nheading"]
counts = [117, 104]
cross = [114, 0]
cross_ratio = [c/n*100 for c, n in zip(cross, counts)]
x = np.arange(2)
w = 0.36
b1 = ax.bar(x-w/2, counts, w, color=LBLUE, edgecolor=BLUE, linewidth=1.2,
            label="块总数", zorder=3)
b2 = ax.bar(x+w/2, cross, w, color=BLUE, edgecolor=DEEP, linewidth=1.2,
            label="跨主题块数", zorder=3)
for i, (c, r) in enumerate(zip(cross, cross_ratio)):
    ax.text(i+w/2, c+2, f"{c} 块\n({r:.1f}%)", ha="center", fontsize=10,
            color=DEEP, fontweight="bold")
for i, c in enumerate(counts):
    ax.text(i-w/2, c+2, f"{c}", ha="center", fontsize=10, color=BLUE, fontweight="bold")
style_ax(ax)
ax.set_xticks(x); ax.set_xticklabels(strategies, fontsize=10.5, color=TEXT)
ax.set_ylabel("块数量", fontsize=10.5, color=TEXT)
ax.set_ylim(0, 135)
ax.legend(frameon=False, fontsize=10, loc="upper right")
ax.set_title("知识库分块质量实测：主题纯度对比（11 篇文档）", fontsize=13,
             color=DEEP, fontweight="bold", pad=10)
ax.annotate("新策略 0 块跨主题\n（旧策略 97.4% 跨主题）",
            xy=(1+w/2, 3), xytext=(0.42, 60),
            fontsize=10, color=TEAL, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=TEAL, lw=1.2))
save(fig, "2_chunk_quality.png")

# =====================================================================
# 图 3：ReAct 编排预算分配 + Planner 冷启动
# =====================================================================
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.4, 3.3), gridspec_kw={"width_ratios": [1.15, 1]})
# 左：预算条形
items = ["单轮编排总预算\nREACT_BUDGET_MS", "Planner 单次超时上限\n(预算×0.75)", "工具调用超时\nREACT_TOOL_TIMEOUT_MS"]
vals = [8000, 6000, 4000]
colors = [DEEP, BLUE, TEAL]
y = np.arange(len(items))[::-1]
ax1.barh(y, vals, height=0.55, color=colors, edgecolor="none", zorder=3)
for yi, v in zip(y, vals):
    ax1.text(v+120, yi, f"{v} ms", va="center", fontsize=10.5, color=TEXT, fontweight="bold")
ax1.set_yticks(y); ax1.set_yticklabels(items, fontsize=9.6, color=TEXT)
ax1.set_xlim(0, 9800)
for spine in ["top", "right"]:
    ax1.spines[spine].set_visible(False)
ax1.spines["left"].set_color("#C9DAEC"); ax1.spines["bottom"].set_color("#C9DAEC")
ax1.tick_params(colors=TEXT, labelsize=9)
ax1.set_xlabel("毫秒（ms）", fontsize=10, color=TEXT)
ax1.set_title("ReAct 编排时间预算（双闸控制）", fontsize=11.5, color=DEEP, fontweight="bold")
ax1.grid(axis="x", color="#E8F0F8", linewidth=0.9); ax1.set_axisbelow(True)
# 右：Planner 冷启动曲线
rounds = ["第 1 次\n（冷启动）", "第 2 次", "第 3 次\n（预热后）"]
pt = [5700, 2600, 1300]
ax2.plot(range(3), pt, marker="o", color=BLUE, linewidth=2.2, markersize=7,
         markerfacecolor=DEEP, zorder=4)
for i, v in enumerate(pt):
    ax2.text(i, v+230, f"{v/1000:.1f}s", ha="center", fontsize=10.5, color=DEEP,
             fontweight="bold")
ax2.fill_between(range(3), pt, color=LBLUE, alpha=0.55, zorder=2)
style_ax(ax2)
ax2.set_xticks(range(3)); ax2.set_xticklabels(rounds, fontsize=9.2, color=TEXT)
ax2.set_ylabel("Planner 规划耗时（ms）", fontsize=9.8, color=TEXT)
ax2.set_ylim(0, 6600)
ax2.set_title("Planner 冷启动 → 预热（qwen2.5:7b）", fontsize=11.5, color=DEEP, fontweight="bold")
fig.tight_layout(w_pad=2.4)
save(fig, "3_react_budget.png")

# =====================================================================
# 图 4：检索防幻觉评分对比（对乙酰氨基酚案例）
# =====================================================================
fig, ax = plt.subplots(figsize=(7.8, 3.6))
labels = ["含「对乙酰氨基酚」\n片段（对症）", "普通感冒\n沾边片段"]
scores = [0.48, 0.58]
colors = [BLUE, GREY]
x = np.arange(2)
bars = ax.bar(x, scores, width=0.5, color=colors, edgecolor=DEEP, linewidth=1.1, zorder=3)
for xi, s in zip(x, scores):
    ax.text(xi, s+0.012, f"{s:.2f}", ha="center", fontsize=12, color=DEEP, fontweight="bold")
# 阈值线（标签放在左侧空白区，避免与柱/数值碰撞）
ax.axhline(0.60, color="#B03A3A", linestyle="-.", linewidth=1.5, zorder=4)
ax.text(-0.42, 0.648, "search() 默认阈值 0.60", color="#B03A3A", fontsize=9.8,
        ha="left", fontweight="bold")
ax.axhline(0.50, color=WARN, linestyle="--", linewidth=1.5, zorder=4)
ax.text(-0.42, 0.525, "证据门槛 REACT_MIN_SCORE=0.50", color=WARN, fontsize=9.8,
        ha="left", fontweight="bold")
style_ax(ax)
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10.5, color=TEXT)
ax.set_ylabel("语义相关度 score（1 - cosine distance）", fontsize=10, color=TEXT)
ax.set_xlim(-0.55, 1.55)
ax.set_ylim(0, 0.78)
ax.set_title("宽召回 + strong_hit 豁免：解决「对症片段被门槛拦下」", fontsize=12.5,
             color=DEEP, fontweight="bold", pad=10)
ax.annotate("0.48 < 0.60 被 search() 拦下\n→ 宽召回捞回 + 强命中置顶",
            xy=(0.02, 0.44), xytext=(0.30, 0.24),
            fontsize=9.8, color=BLUE, fontweight="bold",
            arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.2))
save(fig, "4_retrieval_guard.png")

# =====================================================================
# 图 5：测试套件模块分布（pytest 实测 77 passed）
# =====================================================================
modules = ["上下文保持\ncontext_retention", "ReAct 循环\nreact_cycle", "多模态\nmultimodal",
           "知识分块\nchunking", "报告日期\nreport_visit_date", "思维链\nthinking",
           "微信 API\nwx_api", "位置订阅\nlocation_subscribe"]
counts = [21, 17, 10, 10, 7, 7, 3, 2]
fig, ax = plt.subplots(figsize=(8.0, 3.5))
x = np.arange(len(modules))
colors = [DEEP if c >= 15 else (BLUE if c >= 7 else LBLUE) for c in counts]
bars = ax.bar(x, counts, width=0.6, color=colors, edgecolor=DEEP, linewidth=0.8, zorder=3)
for xi, c in zip(x, counts):
    ax.text(xi, c+0.35, str(c), ha="center", fontsize=10.5, color=DEEP, fontweight="bold")
style_ax(ax)
ax.set_xticks(x)
ax.set_xticklabels(modules, fontsize=8.6, color=TEXT, rotation=14, ha="right")
ax.set_ylabel("测试用例数", fontsize=10.5, color=TEXT)
ax.set_ylim(0, 24)
ax.set_title("回归测试分布：8 个模块 77 条用例，本轮实测全部通过（10.77s）",
             fontsize=12.5, color=DEEP, fontweight="bold", pad=10)
save(fig, "5_test_suite.png")

print("ALL CHARTS DONE")
