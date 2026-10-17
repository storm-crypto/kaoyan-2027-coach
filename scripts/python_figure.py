"""执行本轮编写的 Matplotlib 源码，预渲染 SVG 与 PNG；子进程不是安全沙箱。"""
import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def validate_source(source):
    try:
        ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"Python 绘图源码语法错误（第 {exc.lineno} 行）：{exc.msg}") from exc


def renderer_python():
    if all(importlib.util.find_spec(name) for name in ("matplotlib", "numpy")):
        return sys.executable
    root = Path(__file__).resolve().parent.parent
    local_python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(local_python) if local_python.is_file() else sys.executable


def render_source(source):
    """仅成功后交回成品字节；失败不在 vault 留下源码或半张图。"""
    validate_source(source)
    interpreter = renderer_python()
    with tempfile.TemporaryDirectory(prefix="kaoyan-figure-") as temp:
        svg = Path(temp) / "figure.svg"
        preview = Path(temp) / "preview.png"
        try:
            result = subprocess.run(
                [interpreter, str(Path(__file__).resolve()), str(svg), str(preview)],
                input=source, text=True, capture_output=True, cwd=temp,
                env={**os.environ, "MPLBACKEND": "Agg"}, timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Python 配图超过 60 秒，请减少采样或拆分步骤") from exc
        if result.returncode:
            detail = result.stderr.strip()[-1800:]
            if "ModuleNotFoundError" in detail:
                detail += f"\n绘图依赖请安装到该解释器：{interpreter} -m pip install matplotlib numpy"
            raise ValueError(f"Python 配图失败：\n{detail}")
        if not svg.is_file() or not preview.is_file():
            raise ValueError("Python 配图未生成 SVG / PNG 成品")
        return svg.read_text(encoding="utf-8"), preview.read_bytes(), result.stderr.strip()


def main():
    import runpy
    import warnings
    from math_figure_style import configure
    configure()
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure

    # 中文缺字必须在生成时暴露，不能把方框静默写进错题卡。
    warnings.filterwarnings("error", message=r"Glyph .* missing from .*font")
    source_file = Path("source.py")
    source_file.write_text(sys.stdin.read(), encoding="utf-8")
    namespace = runpy.run_path(str(source_file), run_name="__main__")
    fig = namespace.get("fig")
    if not isinstance(fig, Figure):
        raise ValueError("源码必须把待保存的 Matplotlib Figure 赋给 fig；不要自行 savefig 或 show")
    if len(plt.get_fignums()) != 1:
        raise ValueError("一次调用只生成一个 fig；多阶段用子图或分次调用，避免漏保存")
    if not fig.axes and not fig.texts:
        raise ValueError("fig 没有坐标系或文字，不能保存空白图")
    # 字形转路径并烘焙公式，阅读端不需要中文字体或 TeX 插件。
    fig.savefig(sys.argv[1], format="svg", bbox_inches="tight", pad_inches=0.2)
    fig.savefig(sys.argv[2], format="png", dpi=180, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)


if __name__ == "__main__":
    main()
