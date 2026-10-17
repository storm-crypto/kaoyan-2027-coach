"""数学与 408 讲解图的共用样式；由 Python 配图入口自动配置，也可供源码显式导入。"""

COLORS = {
    "ink": "#263445", "muted": "#738196", "blue": "#347FE5",
    "red": "#E95157", "orange": "#D88A36", "region": "#F8E7A1",
    "paper": "#FFFEFA", "grid": "#E6EAF0",
}


def configure():
    import matplotlib
    matplotlib.use("Agg", force=True)
    from matplotlib import font_manager, rcParams
    candidates = ("PingFang SC", "Heiti TC", "Microsoft YaHei", "Noto Sans CJK SC", "SimHei")
    installed = {font.name for font in font_manager.fontManager.ttflist}
    # 按字体文件补充 macOS 未被默认扫描到的系统中文字体。
    if not installed.intersection(candidates):
        from pathlib import Path
        for font_path in ("/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc"):
            if Path(font_path).is_file():
                font_manager.fontManager.addfont(font_path)
        installed = {font.name for font in font_manager.fontManager.ttflist}
    families = [name for name in candidates if name in installed] + ["DejaVu Sans"]
    rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": families,
        "font.size": 14, "axes.titlesize": 16, "axes.labelsize": 14,
        "xtick.labelsize": 12, "ytick.labelsize": 12, "legend.fontsize": 12,
        "text.color": COLORS["ink"], "axes.labelcolor": COLORS["ink"],
        "axes.edgecolor": COLORS["muted"], "xtick.color": COLORS["muted"],
        "ytick.color": COLORS["muted"], "axes.spines.top": False,
        "axes.spines.right": False, "axes.grid": False,
        "figure.facecolor": COLORS["paper"], "axes.facecolor": COLORS["paper"],
        "savefig.facecolor": COLORS["paper"], "savefig.transparent": False,
        "lines.linewidth": 2.3, "mathtext.fontset": "stix",
        "text.usetex": False, "svg.fonttype": "path", "axes.unicode_minus": False,
    })


def callout(ax, text, xy, xytext, color=None):
    """短标注贴近对象；xy 为数据坐标，xytext 为相对点的屏幕偏移。"""
    color = color or COLORS["red"]
    return ax.annotate(
        text, xy=xy, xytext=xytext, textcoords="offset points",
        fontsize=14, color=color,
        bbox={"boxstyle": "round,pad=0.3", "fc": COLORS["paper"], "ec": "none", "alpha": 0.96},
        arrowprops={"arrowstyle": "->", "color": color, "lw": 1.6},
    )
