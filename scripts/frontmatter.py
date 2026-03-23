"""共享 YAML frontmatter 解析与序列化模块。

三种用法：
- parse_frontmatter(text)        → 完整解析，返回 (dict, body, key_order)
- serialize_frontmatter(fm, ...)  → 序列化回 markdown
- parse_frontmatter_field(text, field) → 轻量提取单个字段
"""


def _find_closing_fence(text):
    """找到 frontmatter 结束的 --- 位置（必须独占一行）。

    从第一行 --- 之后开始，逐行扫描，返回结束 --- 的字符偏移。
    未找到返回 -1。
    """
    # 跳过开头的 ---\n
    start = text.index("\n") + 1 if "\n" in text[:4] else 3
    while start < len(text):
        line_end = text.find("\n", start)
        if line_end == -1:
            line = text[start:]
            if line.strip() == "---":
                return start
            break
        line = text[start:line_end]
        if line.strip() == "---":
            return start
        start = line_end + 1
    return -1


def _split_list_items(raw):
    """拆分 YAML 内联列表，支持引号保护含逗号的项。

    例：'极坐标, "item, with comma", 普通项' → ['极坐标', 'item, with comma', '普通项']
    """
    items = []
    current = []
    in_quote = False
    for ch in raw:
        if ch == '"':
            in_quote = not in_quote
        elif ch == ',' and not in_quote:
            piece = ''.join(current).strip()
            if piece:
                items.append(piece)
            current = []
        else:
            current.append(ch)
    piece = ''.join(current).strip()
    if piece:
        items.append(piece)
    return items


def parse_frontmatter(text):
    """解析 --- 包裹的 YAML frontmatter。

    返回 (fm_dict, body_str, key_order_list)。
    - fm_dict: 字段字典，列表值解析为 list
    - body_str: frontmatter 之后的正文（含前导换行）
    - key_order_list: 字段出现顺序，用于序列化时保持原始顺序
    """
    if not text.startswith("---"):
        return {}, text, []
    end = _find_closing_fence(text)
    if end == -1:
        return {}, text, []
    fm_text = text[3:end].strip()
    fm = {}
    key_order = []
    for line in fm_text.split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            fm[key] = _split_list_items(inner) if inner.strip() else []
        else:
            fm[key] = val
        key_order.append(key)
    # body starts after the closing --- line
    body_start = text.find("\n", end)
    body = text[body_start:] if body_start != -1 else ""
    return fm, body, key_order


def _serialize_list(items):
    """序列化列表为 YAML 内联格式，含逗号的项用引号保护。"""
    parts = []
    for item in items:
        if ',' in item:
            parts.append(f'"{item}"')
        else:
            parts.append(item)
    return f"[{', '.join(parts)}]"


def serialize_frontmatter(fm, key_order, body):
    """将 frontmatter dict 序列化为 markdown 文本。

    key_order 控制字段输出顺序，不在 key_order 中的新字段追加到末尾。
    """
    lines = ["---"]
    for k in key_order:
        if k not in fm:
            continue
        v = fm[k]
        if isinstance(v, list):
            lines.append(f"{k}: {_serialize_list(v)}")
        else:
            lines.append(f"{k}: {v}")
    for k, v in fm.items():
        if k not in key_order:
            if isinstance(v, list):
                lines.append(f"{k}: {_serialize_list(v)}")
            else:
                lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + body


def parse_frontmatter_field(text, field):
    """快速提取 frontmatter 中某个字段的值（字符串），未找到返回空串。"""
    if not text.startswith("---"):
        return ""
    end = _find_closing_fence(text)
    if end == -1:
        return ""
    for line in text[3:end].split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        if key.strip() == field:
            return val.strip()
    return ""
