"""408 Python 配图骨架集。修改 EXAMPLE 选类别，再将示例数据换成本题已知/已推出的数据。

通过 create_figure.py --kind python --source-file 本文件运行；定义 fig，不自行保存。
"""
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon

from math_figure_style import COLORS, callout
from cs_figure_style import binary_tree, field_strip, timeline

EXAMPLE = "cache"


def tree():
    # LL 型失衡：中序顺序始终为 10、20、30；横坐标由中序序号固定。
    before = {30: (20, None), 20: (10, None), 10: (None, None)}
    after = {20: (10, 30), 10: (None, None), 30: (None, None)}
    fig, axes = plt.subplots(2, 1, figsize=(7, 7), layout="constrained")
    for ax, data, root, title in (
        (axes[0], before, 30, "第 1 步：找到失衡点 30（示例）"),
        (axes[1], after, 20, "第 2 步：右旋，20 成为局部根"),
    ):
        binary_tree(ax, data, root, active=(20, 30))
        # 两步保留同一画布范围，避免自动缩放造成视觉跳动。
        ax.set_ylim(-2.55, 0.55)
        ax.set_title(title, loc="left", pad=12)
    fig.supxlabel("L / R 表示孩子方向；中序顺序保持 10、20、30", fontsize=13)
    return fig


def linked_list():
    # 只解释一次迭代，固定节点位置；箭头数据就是 next 指针状态。
    fig, axes = plt.subplots(3, 1, figsize=(7, 8), layout="constrained")
    states = [
        ("第 1 步：先保存后继 nxt = B（示例）", {"A": "B", "B": "C", "C": "NULL"}, "NULL", "A", "B"),
        ("第 2 步：改指向 A.next = prev", {"A": "NULL", "B": "C", "C": "NULL"}, "NULL", "A", "B"),
        ("第 3 步：前移 prev = A，cur = B", {"A": "NULL", "B": "C", "C": "NULL"}, "A", "B", "B"),
    ]
    x = {"NULL": 0, "A": 2, "B": 4, "C": 6}
    for ax, (title, edges, prev, cur, nxt) in zip(axes, states):
        ax.set_title(title, loc="left", fontsize=15, pad=14)
        ax.set(xlim=(-0.5, 7.4), ylim=(-1.25, 1.3))
        ax.axis("off")
        for name in ("A", "B", "C"):
            ax.add_patch(Rectangle((x[name] - 0.6, -0.25), 1.2, 0.5, facecolor=COLORS["paper"], edgecolor=COLORS["blue"], lw=2))
            ax.plot([x[name] + 0.1] * 2, [-0.25, 0.25], color=COLORS["blue"], lw=1)
            ax.text(x[name] - 0.25, 0, name, ha="center", va="center")
        ax.text(0, 0, "NULL", ha="center", va="center", fontsize=12)
        for node, target in edges.items():
            if node == "C":
                ax.text(x[node] + 0.85, -0.9, "NULL", fontsize=12, ha="center")
                ax.annotate("", xy=(x[node] + 0.85, -0.65), xytext=(x[node] + 0.4, 0),
                            arrowprops={"arrowstyle": "->", "color": COLORS["muted"]})
                continue
            color = COLORS["red"] if node == "A" else COLORS["muted"]
            end_x = x[target] - 0.65 if target != "NULL" else 0.4
            ax.annotate("", xy=(end_x, 0), xytext=(x[node] + 0.4, 0),
                        arrowprops={"arrowstyle": "->", "color": color, "lw": 2,
                                    "connectionstyle": "arc3,rad=-0.5" if target == "NULL" else "arc3,rad=0"})
        # 分行标出同指向的变量，不靠颜色猜变量身份。
        for label, target, y in (("prev", prev, 0.9), ("cur", cur, 0.5), ("nxt", nxt, -0.85)):
            ax.text(x[target], y, label, ha="center", color=COLORS["red"], fontsize=13)
    return fig


def cache():
    # 示例：16 位地址、4 行直接映射、16B/块；地址 0x0064。
    address, line_count, block_bytes, address_bits = 0x0064, 4, 16, 16
    offset_bits, index_bits = block_bytes.bit_length() - 1, line_count.bit_length() - 1
    tag_bits = address_bits - index_bits - offset_bits
    block, offset = divmod(address, block_bytes)
    tag, index = divmod(block, line_count)
    fig, axes = plt.subplots(2, 1, figsize=(7, 8), height_ratios=(1, 2.3), layout="constrained")
    axes[0].set_title("第 1 步：按位宽切地址（示例）", loc="left", pad=14)
    field_strip(axes[0], [("Tag", tag_bits), ("Index", index_bits), ("Offset", offset_bits)], address_bits)
    ax = axes[1]
    ax.set_title("第 2 步：组号选行，标记区分块", loc="left", pad=14)
    ax.set(xlim=(-1, 6.6), ylim=(-0.6, 8.8))
    ax.axis("off")
    ax.text(0, 8.2, "主存局部：仅列 0–7 块", fontsize=12)
    ax.text(4.3, 8.2, "Cache：4 行", fontsize=12)
    for b in range(8):
        y = 7 - b
        color = COLORS["red"] if b == block else COLORS["muted"]
        ax.add_patch(Rectangle((0, y), 1.8, 0.7, facecolor=COLORS["paper"], edgecolor=color, lw=2 if b == block else 1))
        ax.text(0.9, y + 0.35, f"块 {b}", ha="center", va="center", fontsize=12)
    for row in range(line_count):
        y = 5.5 - row * 1.3
        color = COLORS["red"] if row == index else COLORS["blue"]
        ax.add_patch(Rectangle((4.4, y), 1.5, 0.8, facecolor=COLORS["paper"], edgecolor=color, lw=2))
        ax.text(5.15, y + 0.4, f"行 {row}", ha="center", va="center", fontsize=12)
    for b in (2, block):
        row = b % line_count
        ax.annotate("", xy=(4.4, 5.5 - row * 1.3 + 0.4), xytext=(1.8, 7 - b + 0.35),
                    arrowprops={"arrowstyle": "->", "color": COLORS["red"] if b == block else COLORS["muted"], "lw": 2})
    ax.text(2.1, 6.4, f"块 {block} → 行 {index}\nTag = {tag}\nOffset = {offset} B", fontsize=13, color=COLORS["red"])
    fig.supxlabel(f"0x{address:04X}；{block} = {tag} × {line_count} + {index}（直接映射）", fontsize=13)
    return fig


def pipeline():
    # 示例采用五段、单周期段、独立指令，无停顿；不能据此推断具体题的冒险。
    stages = ["IF", "ID", "EX", "MEM", "WB"]
    count = 3
    rows = [[(stage, instruction + stage_index) for stage_index, stage in enumerate(stages)] for instruction in range(count)]
    fig, ax = plt.subplots(figsize=(7, 4.6), layout="constrained")
    palette = [COLORS["blue"], COLORS["orange"], COLORS["red"], "#598A75", COLORS["muted"]]
    for instruction, cells in enumerate(rows):
        for stage, cycle in cells:
            color = palette[stages.index(stage)]
            ax.add_patch(Rectangle((cycle, instruction), 1, 0.8, facecolor=color, alpha=0.2, edgecolor=color))
            ax.text(cycle + 0.5, instruction + 0.4, stage, ha="center", va="center", fontsize=12)
    total = max(cycle + 1 for cells in rows for _, cycle in cells)
    ax.set(xlim=(0, total), ylim=(count, -0.6), yticks=[i + 0.4 for i in range(count)], yticklabels=[f"I{i + 1}" for i in range(count)])
    ax.set_xticks([i + 0.5 for i in range(total)], labels=range(1, total + 1))
    ax.set_xlabel("时钟周期（每格 1 周期）")
    ax.set_title("流水线时空图：先看重叠，再查停顿（示例）", loc="left", fontsize=15, pad=16)
    fig.supxlabel(f"假设：独立指令、五段、每段 1 周期、无停顿；末条 WB 在第 {total} 周期", fontsize=12)
    return fig


def scheduling():
    # FCFS，三个进程均在 0 到达，同到达按 P1/P2/P3 入队；忽略切换开销。
    service = [("P1", 3), ("P2", 2), ("P3", 4)]
    segments, cursor = [], 0
    for name, duration in service:
        segments.append((name, cursor, cursor + duration))
        cursor += duration
    fig, ax = plt.subplots(figsize=(7, 3.5), layout="constrained")
    timeline(ax, segments)
    ax.set_xlabel("时间 / ms")
    ax.set_title("FCFS：运行区间宽度对应服务时间（示例）", loc="left", fontsize=15, pad=16)
    fig.supxlabel("均在 0 到达；队列 P1 → P2 → P3；无切换开销\n服务时间依次为 3、2、4 ms；正文另列周转时间核对表", fontsize=12)
    return fig


def network():
    # 示例：L=12000 bit，R=6000 bit/ms，单向传播时延 3 ms；无 ACK、无处理时延。
    length, rate, propagation = 12000, 6000, 3
    sending = length / rate
    fig, ax = plt.subplots(figsize=(7, 6.5), layout="constrained")
    end = sending + propagation
    ax.set(xlim=(-0.4, 1.65), ylim=(end + 0.8, -0.7), xticks=[0, 1], xticklabels=["发送端 A", "接收端 B"])
    ax.xaxis.tick_top()
    ax.set_yticks(sorted({0, sending, propagation, end}))
    ax.set_ylabel("时间 / ms（向下增加）")
    for side in (0, 1):
        ax.plot([side, side], [0, end + 0.4], color=COLORS["muted"], lw=1)
    ax.add_patch(Polygon([(0, 0), (1, propagation), (1, end), (0, sending)],
                         facecolor=COLORS["blue"], alpha=0.12))
    ax.annotate("", xy=(1, propagation), xytext=(0, 0), arrowprops={"arrowstyle": "->", "color": COLORS["blue"], "lw": 2})
    ax.annotate("", xy=(1, end), xytext=(0, sending), arrowprops={"arrowstyle": "->", "color": COLORS["red"], "lw": 2})
    ax.text(0.15, 0.5, "首比特", color=COLORS["blue"], fontsize=13)
    ax.text(0.25, 3.8, "末比特", color=COLORS["red"], fontsize=13)
    ax.text(1.05, propagation, f"首比特到达：{propagation:g} ms", va="center", fontsize=12)
    ax.text(1.05, end, f"末比特到达：{end:g} ms", va="center", fontsize=12, color=COLORS["red"])
    ax.text(0.04, sending, f"发送完：{sending:g} ms", va="bottom", fontsize=12, color=COLORS["red"])
    ax.set_title("发送完与接收完发生在不同时刻（示例）", loc="left", fontsize=15, pad=32)
    fig.supxlabel(f"发送时延 = L/R = {sending:g} ms；传播时延 = {propagation:g} ms\n无确认、处理与排队时延；时间按比例，横向只表示端点", fontsize=12)
    return fig


EXAMPLES = {"tree": tree, "linked_list": linked_list, "cache": cache,
            "pipeline": pipeline, "scheduling": scheduling, "network": network}
fig = EXAMPLES[EXAMPLE]()
