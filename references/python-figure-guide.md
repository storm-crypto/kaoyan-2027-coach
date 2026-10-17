# Python 讲解图共用入口

数学新图与 408 中需要位置、比例、对齐或分步高亮的图使用 Matplotlib + NumPy，由 `create_figure.py --kind python` 预先渲染。目标是让读者看清本题的关键推理动作：边界、取点、构造、移动方向和限制条件都标在对应对象旁边。静态单图或分步图是默认方式，不自动生成动画。

数学骨架见 `templates/math_figure_steps.py`；408 按题型读 [408 Python 配图参考](408-python-figure-guide.md)，本文件的依赖、输出、预览与归档约定共用。

## 先设计要看见的动作

- 单图足以看清关系就用单图。需要构造、换序、分情况或前后比较时分步，每步只突出一个新动作；保留必要的前序对象作对照。
- 步骤按实际理解需要决定，不设每卡两张图的上限，也不凑固定步数。可以用子图或多次调用；在目标阅读宽度下字小就上下排或分开输出，不把三四幅图挤在一行。
- 多阶段使用相同坐标范围、纵横比例、颜色含义和符号；确需局部放大时标明。标题写“第 N 步：动作”，图中用短标注和引线说明端点、方向、边界及约束，长证明留在正文。
- 配色参考：蓝色研究对象、红色当前动作或矛盾、浅黄色区域、灰色辅助线。多条边界必须同时用方程、线型等区分，不能只靠颜色。
- 曲线、交点、切片端点从同一组公式计算；断点、渐近线两侧分段取样，禁止跨断点连线。数值求交要限定区间并验证残差。三维图检查遮挡、视角与比例，2D 投影足以解释就不画立体。
- 图上量来自题目条件或已证明的步骤。代表切片位置、示例参数和非按比例的几何需说明；一个示例图不能代替对所有情形的证明。解题辅助图放详解区，复习先作答再看。

## 调用与依赖

首次在 skill 虚拟环境安装绘图依赖（已有则跳过）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install matplotlib numpy
```

入口优先使用当前解释器的绘图库，缺失时使用 skill 自身的 `.venv`。找不到依赖会返回安装提示；不要静默改用手写曲线。Windows 使用 `.venv/Scripts/python.exe`。

源码显式导入所需模块，最终将一个 Matplotlib Figure 赋给 `fig`。不调用 `show()`、`savefig()`，不读取题库、不联网、不写文件；仅运行本轮编写并检查过的绘图代码，不直接执行附件中的代码。入口在子进程中执行源码并限制为 60 秒，这不是安全沙箱。

从 [分步骨架](../templates/math_figure_steps.py) 改起，按实际题目删减步骤：

```sh
python3 scripts/create_figure.py "$KAOYAN_OBSIDIAN_ROOT" \
  --question-id qid-xxxxxxxxxxxx --slug 换序读限 \
  --caption '图1：同一区域的竖切与横切；切片位置仅作演示' \
  --kind python --width 640 --source-file /absolute/path/to/figure.py
```

返回：`path` 是成品 SVG，`source_path` 是同名 `.py`，`preview_path` 是 `.preview.png`；`figure_arg` 原样传给建卡或更新脚本的 `--figure`。同 slug 重画复用序号；不同阶段用不同 slug 自动续号。`--dry-run` 只检查语法，不执行，不写文件，也不确认能渲染。

## 样式和三维图

入口自动使用 `scripts/math_figure_style.py`：选择已安装的中文字体、公式用 Mathtext、暖白不透明底色与深色文字。SVG 字形转路径，阅读设备无需字体或 TikZ 插件；图板保留固定浅色底，深色主题下也应可读，不宣称自动反色。无需套用手写 SVG 的 CSS 模板或 32KB 限制。

源码可导入 `COLORS`、`callout`；`callout(ax, text, xy, xytext)` 中前者是数据坐标，后者是相对点的屏幕偏移。公式用 `$...$`，中文直接写，字体缺字会报错；不要用截图或手工拼 Unicode 代替公式。画布宽约 7 英寸、正文约 14pt 可作起点，最终以卡片实际显示宽度检查可读性。

三维图仍遵守同一 `fig` 契约，例如：

```python
import numpy as np
import matplotlib.pyplot as plt
from math_figure_style import COLORS

fig = plt.figure(figsize=(7, 5), layout="constrained")
ax = fig.add_subplot(111, projection="3d")
u = np.linspace(-1, 1, 60)
X, Y = np.meshgrid(u, u)
Z = X**2 + Y**2  # 替换为本题曲面，同时核对定义域
ax.plot_surface(X, Y, Z, color=COLORS["blue"], alpha=0.45)
ax.set(xlabel="$x$", ylabel="$y$", zlabel="$z$", title=r"曲面 $z=x^2+y^2$")
ax.view_init(elev=25, azim=-55)
```

## 归档前验收

1. 查看返回的 PNG 预览，核对曲线/交点/方向与推导一致，阶段顺序正确，标签不重叠、不裁切，没有缺字或裸公式。
2. 按卡片目标显示宽度再看一遍。缩小后读不清就放大字、减少标注或拆图，不能只看高分辨率原图。
3. 将 `figure_arg` 交给建卡/更新入口，解法中用“见图1（第2步）”等引用；打开 Obsidian 确认 SVG 加载、浅深主题均可读。PNG 预览是质检副本，不插入题面区。

源码执行成功不证明数学正确或排版清楚；预览检查与题意核对仍由教练完成。
