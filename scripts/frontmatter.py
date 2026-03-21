"""共享 YAML frontmatter 解析与序列化模块。

三种用法：
- parse_frontmatter(text)        → 完整解析，返回 (dict, body, key_order)
- serialize_frontmatter(fm, ...)  → 序列化回 markdown
- parse_frontmatter_field(text, field) → 轻量提取单个字段
"""


def parse_frontmatter(text):
    """解析 --- 包裹的 YAML frontmatter。

    返回 (fm_dict, body_str, key_order_list)。
    - fm_dict: 字段字典，列表值解析为 list
    - body_str: frontmatter 之后的正文（含前导换行）
    - key_order_list: 字段出现顺序，用于序列化时保持原始顺序
    """
    if not text.startswith("---"):
        return {}, text, []
    end = text.find("---", 3)
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
            items = val[1:-1]
            fm[key] = [x.strip() for x in items.split(",") if x.strip()] if items else []
        else:
            fm[key] = val
        key_order.append(key)
    body = text[end + 3:]
    return fm, body, key_order


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
            lines.append(f"{k}: [{', '.join(v)}]")
        else:
            lines.append(f"{k}: {v}")
    for k, v in fm.items():
        if k not in key_order:
            if isinstance(v, list):
                lines.append(f"{k}: [{', '.join(v)}]")
            else:
                lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + body


def parse_frontmatter_field(text, field):
    """快速提取 frontmatter 中某个字段的值（字符串），未找到返回空串。"""
    if not text.startswith("---"):
        return ""
    end = text.find("---", 3)
    if end == -1:
        return ""
    for line in text[3:end].split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        if key.strip() == field:
            return val.strip()
    return ""
