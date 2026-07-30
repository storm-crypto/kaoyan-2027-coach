"""解析学习日志中的时长字段。

日志允许使用纯小时、小时+分钟或纯分钟，例如：
3、3h、3小时、5h47min、1小时22分钟、50min、26分钟。
"""
from __future__ import annotations

import re


_DURATION_LINE_RE = re.compile(r"[^\n]*时长[^\n]*", re.IGNORECASE)
_HOUR_RE = re.compile(r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?:h|小时)", re.IGNORECASE)
_MINUTE_RE = re.compile(r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?:min|分钟)", re.IGNORECASE)


def parse_logged_hours(text: str) -> float:
    """从文本中第一条“时长”字段解析小时数。

    带单位时，按单位换算；没有单位时兼容旧日志，把数值视为小时。
    """
    line_match = _DURATION_LINE_RE.search(text or "")
    if not line_match:
        return 0.0
    line = line_match.group(0)

    hours = sum(float(match.group("value")) for match in _HOUR_RE.finditer(line))
    minutes = sum(float(match.group("value")) for match in _MINUTE_RE.finditer(line))
    if hours or minutes:
        return hours + minutes / 60.0

    # 兼容旧日志里的“时长：8”或“时长：数学一=8”。
    bare = re.search(r"[0-9]+(?:\.[0-9]+)?", line)
    return float(bare.group(0)) if bare else 0.0
