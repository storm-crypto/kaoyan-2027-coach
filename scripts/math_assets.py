"""内联本地 KaTeX 与 woff2 字体，使工作台不依赖网络加载公式。"""
import base64
from functools import lru_cache
from pathlib import Path
import re


@lru_cache(maxsize=1)
def math_assets():
    root = Path(__file__).resolve().parent.parent / "resources/katex"
    css = (root / "katex.min.css").read_text(encoding="utf-8")
    def font(match):
        payload = base64.b64encode((root / match[1]).read_bytes()).decode("ascii")
        return 'src:url(data:font/woff2;base64,' + payload + ') format("woff2")'
    css = re.sub(r'src:url\((fonts/[^)]+\.woff2)\).*?;', lambda m: font(m) + ';', css)
    js = (root / "katex.min.js").read_text(encoding="utf-8") + "\n" + (root / "auto-render.min.js").read_text(encoding="utf-8")
    return css, js.replace("</script", "<\\/script")
