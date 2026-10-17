"""配图骨架示例：区域 y=x² 与 y=x 的读限过程；按实际题目修改。

切片位置为演示参数，不是题目新增条件。每个子图突出一个动作。
通过 create_figure.py --kind python --source-file 本文件 运行，不自行保存文件。
"""
import numpy as np
import matplotlib.pyplot as plt
from math_figure_style import COLORS, callout

fig, axes = plt.subplots(3, 1, figsize=(7, 12), layout="constrained")
x = np.linspace(0, 1, 301)
titles = ("第 1 步：看边界，确定区域", "第 2 步：竖切，先读上下边界", "第 3 步：横切，再读左右边界")
for ax, title in zip(axes, titles):
    ax.set_title(title, loc="left", pad=16, weight="bold")
    ax.fill_between(x, x**2, x, color=COLORS["region"], alpha=0.65)
    ax.plot(x, x, color=COLORS["blue"])
    ax.plot(x, x**2, color=COLORS["blue"])
    ax.set(xlim=(-0.08, 1.35), ylim=(-0.08, 1.2), aspect="equal")
    ax.spines["bottom"].set_position("zero")
    ax.spines["left"].set_position("zero")
    ax.set_xticks([0, 1])
    ax.set_yticks([1])
    ax.set_xlabel("$x$", loc="right")
    ax.set_ylabel("$y$", loc="top", rotation=0)
    ax.text(0.92, 1.04, "$y=x$", color=COLORS["blue"])
    ax.text(1.04, 0.8, "$y=x^2$", color=COLORS["blue"])

callout(axes[0], "两条边界之间\n是同一个区域 $D$", (0.6, 0.47), (60, -30), COLORS["orange"])

# 代表切片；端点按边界公式计算，不手填屏幕坐标。
x0 = 0.6
axes[1].plot([x0, x0], [x0**2, x0], color=COLORS["red"], lw=4)
axes[1].scatter([x0, x0], [x0**2, x0], color=COLORS["red"], zorder=5)
callout(axes[1], "上端：$y=x$", (x0, x0), (-100, 40))
callout(axes[1], "下端：$y=x^2$", (x0, x0**2), (30, -32))
axes[1].text(0.03, 0.96, "$x$ 固定，$y$ 从下往上", transform=axes[1].transAxes, fontsize=13)

y0 = 0.36
axes[2].plot([y0, np.sqrt(y0)], [y0, y0], color=COLORS["red"], lw=4)
axes[2].scatter([y0, np.sqrt(y0)], [y0, y0], color=COLORS["red"], zorder=5)
callout(axes[2], "左端：$x=y$", (y0, y0), (-75, 55))
callout(axes[2], r"右端：$x=\sqrt{y}$", (np.sqrt(y0), y0), (35, -35))
axes[2].text(0.03, 0.96, "$y$ 固定，$x$ 从左往右", transform=axes[2].transAxes, fontsize=13)
