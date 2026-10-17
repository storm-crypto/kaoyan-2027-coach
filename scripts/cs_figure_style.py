"""408 讲解图的比例、时间区间与二叉树骨架，复用 Python 配图入口。"""
from numbers import Integral

from math_figure_style import COLORS


def field_strip(ax, fields, total_bits):
    """fields 为高位到低位的 (名称, 位宽)；矩形宽度直接使用位宽。"""
    from matplotlib.patches import Rectangle
    if not fields or any(not isinstance(width, Integral) or isinstance(width, bool) or width <= 0 for _, width in fields):
        raise ValueError("字段位宽必须是正整数")
    if sum(width for _, width in fields) != total_bits:
        raise ValueError("字段位宽之和必须等于总位宽")
    colors = [COLORS["blue"], COLORS["orange"], COLORS["red"]]
    cursor = 0
    patches = []
    for index, (name, width) in enumerate(fields):
        color = colors[index % len(colors)]
        patch = Rectangle((cursor, 0), width, 1, facecolor=color, alpha=0.15, edgecolor=color, lw=2)
        ax.add_patch(patch)
        patches.append(patch)
        high, low = total_bits - cursor - 1, total_bits - cursor - width
        ax.text(cursor + width / 2, 0.5, f"{name}\n{width} bit", ha="center", va="center", fontsize=13)
        ax.text(cursor + width / 2, 1.2, str(high) if high == low else f"{high} … {low}", ha="center", fontsize=12)
        cursor += width
    ax.text(total_bits / 2, -0.55, " + ".join(str(width) for _, width in fields) + f" = {total_bits} bit", ha="center", fontsize=14)
    ax.set(xlim=(-0.5, total_bits + 0.5), ylim=(-0.9, 1.65))
    ax.axis("off")
    return patches


def timeline(ax, segments):
    """单资源甘特图；每段 (标签, 开始, 结束)，横轴按真实时长。"""
    from matplotlib.patches import Rectangle
    segments = sorted(segments, key=lambda segment: segment[1])
    if not segments or any(end <= start for _, start, end in segments):
        raise ValueError("时间区间必须有正时长")
    if any(right[1] < left[2] for left, right in zip(segments, segments[1:])):
        raise ValueError("单资源时间区间不能重叠")
    palette = [COLORS["blue"], COLORS["orange"], COLORS["red"], COLORS["muted"]]
    labels = list(dict.fromkeys(label for label, _, _ in segments))
    patches = []
    for label, start, end in segments:
        color = palette[labels.index(label) % len(palette)]
        patch = Rectangle((start, 0), end - start, 0.8, facecolor=color, alpha=0.2, edgecolor=color, lw=2)
        ax.add_patch(patch)
        patches.append(patch)
        ax.text((start + end) / 2, 0.4, label, ha="center", va="center")
    ax.set(xlim=(segments[0][1], segments[-1][2]), ylim=(-0.15, 1.2), yticks=[])
    ax.set_xticks(sorted({value for _, start, end in segments for value in (start, end)}))
    ax.spines[["left", "right", "top"]].set_visible(False)
    return patches


def binary_tree(ax, children, root, active=()):
    """中序序号决定横坐标，孩子方向明确标 L/R；旋转前后节点身份不变。"""
    from matplotlib.patches import Circle
    visited, ordered, depths = set(), [], {}

    def visit(node, depth):
        if node is None:
            return
        if node in visited:
            raise ValueError("二叉树不能有环或共享孩子")
        visited.add(node)
        depths[node] = depth
        left, right = children.get(node, (None, None))
        visit(left, depth + 1)
        ordered.append(node)
        visit(right, depth + 1)

    visit(root, 0)
    if not ordered:
        raise ValueError("二叉树不能为空")
    positions = {node: (index, -depths[node]) for index, node in enumerate(ordered)}
    for node in ordered:
        for side, child in zip(("L", "R"), children.get(node, (None, None))):
            if child is None:
                continue
            x, y = positions[node]
            cx, cy = positions[child]
            color = COLORS["red"] if node in active or child in active else COLORS["muted"]
            ax.annotate("", xy=(cx, cy + 0.18), xytext=(x, y - 0.18), arrowprops={"arrowstyle": "->", "color": color, "lw": 2})
            ax.text((x + cx) / 2 + 0.13, (y + cy) / 2, side, fontsize=12, color=color)
    for node, (x, y) in positions.items():
        color = COLORS["red"] if node in active else COLORS["blue"]
        ax.add_patch(Circle((x, y), 0.22, facecolor=COLORS["paper"], edgecolor=color, lw=2, zorder=3))
        ax.text(x, y, str(node), ha="center", va="center", zorder=4)
    ax.set(xlim=(-0.7, len(ordered) - 0.3), ylim=(-max(depths.values()) - 0.55, 0.55), aspect="equal")
    ax.axis("off")
    return positions
