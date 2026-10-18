"""元技能的只读浏览投影。JSON 保存归属，卡片保存复习记录，Markdown 仅为派生视图。"""
from collections import Counter, defaultdict
from pathlib import Path
import json
import re
import os
from urllib.parse import quote

from metaskill_index import INDEX_RELPATH
from metaskill_text import parse_decision, unmarked_math

MARKDOWN_RELPATH = Path("错题本/元技能目录.md")
STATUSES = ("不会", "半会", "会", "未标注")


def cluster_heading(cluster):
    return f"{cluster['id']} · {cluster['name'].replace('|', '丨')}"


def markdown_link(source, target, label, heading=None):
    """Obsidian 可解析的相对 Markdown 链接；路径与标题分别编码。"""
    href = quote(Path(os.path.relpath(target, Path(source).parent)).as_posix(), safe='/')
    if heading:
        href += '#' + quote(heading, safe='')
    label = str(label).replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]').replace('|', '\\|')
    return f'[{label}]({href})'


def natural_key(value):
    return tuple((0, int(p)) if p.isdigit() else (1, p.casefold())
                 for p in re.split(r"(\d+)", str(value)))


def build_metaskills(root, cards, make_link):
    root = Path(root)
    warnings = []
    try:
        index = json.loads((root / INDEX_RELPATH).read_text(encoding="utf-8"))
        if not isinstance(index, dict) or not isinstance(index.get("clusters"), list):
            raise ValueError("索引结构不是簇列表")
    except FileNotFoundError:
        index = {"clusters": []}
        warnings.append("尚未建立元技能索引。")
    except (ValueError, OSError) as exc:
        index = {"clusters": []}
        warnings.append(f"元技能索引无法读取：{exc}")
    by_qid = {str(c.get("question_id", "")).removeprefix("qid-"): c for c in cards}
    primary = defaultdict(list)
    secondary = defaultdict(list)
    for c in index["clusters"]:
        for q in c.get("qids", []):
            primary[q].append(c["id"])
        for q in c.get("also", []):
            secondary[q].append(c["id"])
    rows = []
    for c in index["clusters"]:
        if unmarked_math(c.get('skill', '')):
            warnings.append(f"{c['id']} 的口诀含未标记公式，请用 LaTeX 数学定界符补齐。")
        members = []
        qids = list(dict.fromkeys(c.get("qids", [])))
        also = [q for q in dict.fromkeys(c.get("also", [])) if q not in qids]
        for role, refs in [("主归属", qids), ("次归属", also)]:
            for q in refs:
                card = by_qid.get(q)
                if card is None:
                    warnings.append(f"{c['id']} 引用了未读到的题卡 qid-{q}。")
                members.append({
                    "qid": q, "role": role, "missing": card is None,
                    "topic": card["topic"] if card else f"未读到题卡 qid-{q}",
                    "status": card["status"] if card and card["status"] in STATUSES else "未标注",
                    "due": bool(card and card["is_due"]),
                    "next_review": card["next_review"] if card else "-",
                    "last_review": card["last_review_at"] if card else "-",
                    "chapter": card["chapter"] if card else "未读到",
                    "path": card["path"] if card else None,
                    "link": make_link(card["path"], root) if card else None,
                    "primary_clusters": primary[q], "secondary_clusters": secondary[q],
                    "command": f"/review qid-{q}",
                })
        main = [m for m in members if m["role"] == "主归属" and not m["missing"]]
        subjects = Counter(by_qid[q]["subject"] for q in qids if q in by_qid)
        subject = c.get("subject") or (subjects.most_common(1)[0][0] if subjects else "未标注")
        paths = [Path(by_qid[q]["path"]).relative_to(root / "错题本").parts for q in qids if q in by_qid]
        raw_module = paths[0][1] if paths and len(paths[0]) > 1 else ""
        module = {"高等数学": "高数", "线性代数": "线代", "概率论与数理统计": "概率统计",
                  "计算机组成原理": "计组", "操作系统": "操作系统", "数据结构": "数据结构",
                  "计算机网络": "计算机网络"}.get(raw_module, raw_module or "未标注")
        chapter = re.sub(r"^(?:408[·\s]+CO[·\s]+|概率论\s+|线代\s+)", "", c.get("ch", "未标注"))
        group = f"{subject} · {module} · {chapter}"
        title = c.get("name") or (main[0]["topic"] if len(qids) == 1 and main else c.get("family") or c["id"])
        rows.append({"id": c["id"], "name": title, "subject": subject, "module": module,
                     "chapter": chapter, "chapter_group": group, "family": c.get("family") or "未标注方法",
                     "skill": c.get("skill", ""), "decision": parse_decision(c.get("skill", "")), "note": c.get("note", ""),
                     "primary_count": len(qids), "secondary_count": len(also),
                     "counts": dict(Counter(m["status"] for m in main)),
                     "due_count": sum(m["due"] for m in main), "members": members})
    rows.sort(key=lambda c: ({"数学一": 0, "408": 1, "英语一": 2, "政治": 3}.get(c["subject"], 4),
                             {"高数": 0, "线代": 1, "概率统计": 2, "计组": 3}.get(c["module"], 4),
                             natural_key(c["chapter"]), natural_key(c["id"])))
    unclustered = [{"qid": q, "topic": c["topic"], "link": make_link(c["path"], root)}
                   for q, c in by_qid.items() if q and q not in primary]
    duplicates = [q for q, ids in primary.items() if len(ids) > 1]
    if duplicates:
        warnings.append(f"{len(duplicates)} 张卡存在重复主归属，需核对索引。")
    return {"clusters": rows, "warnings": list(dict.fromkeys(warnings)), "unclustered": unclustered,
            "total_cards": len(set(primary) & set(by_qid)), "families": len({c["family"] for c in rows}),
            "singleton_count": sum(c["primary_count"] == 1 for c in rows),
            "markdown_path": str(root / MARKDOWN_RELPATH),
            "markdown_uri": make_link(root / MARKDOWN_RELPATH, root)}


def render_metaskill_markdown(data, today):
    rows = data["clusters"]
    source = Path(data['markdown_path'])
    def ref(c):
        return markdown_link(source, source, c['name'], cluster_heading(c))
    out = ["# 元技能目录", "", f"> 更新于 {today} · {len(rows)} 簇 · {data['total_cards']} 张主归属题卡 · {data['families']} 个方法族。",
           "> 此页自动生成。名称、口诀与归属维护在 `_元技能索引.json`，复习记录维护在题卡；重新生成会覆盖此页。",
           "> 状态统计只汇总主归属卡的现有记录，不代表整个簇已通过迁移验收。", "",
           "- [[#按章节浏览]]", "- [[#按方法浏览]]", "- [[#簇详情]]", ""]
    for label, field in [("按章节浏览", "chapter_group"), ("按方法浏览", "family")]:
        out += [f"## {label}", ""]
        groups = defaultdict(list)
        for c in rows:
            groups[c[field]].append(c)
        for group, members in sorted(groups.items(), key=lambda item: natural_key(item[0])):
            out += [f"### {group}", ""]
            for c in members:
                out.append(f"- {ref(c)} · {c['primary_count']} 题 · 到期 {c['due_count']} · {c['id']}")
            out.append("")
    out += ["## 簇详情", ""]
    for c in rows:
        counts = "、".join(f"{s} {c['counts'].get(s, 0)}" for s in STATUSES if c["counts"].get(s)) or "暂无可读题卡记录"
        out += [f"### {cluster_heading(c)}", "", f"- 章节：{c['chapter_group']}", f"- 方法族：{c['family']}",
                f"- 主归属 {c['primary_count']} 题；次归属 {c['secondary_count']} 题；到期 {c['due_count']} 题。",
                f"- 主归属卡记录：{counts}", ""]
        decision = c['decision']
        if decision['trigger']:
            out += ['**看到什么**', '', decision['trigger'], '']
        out += ['**怎么做**', '']
        for i, step in enumerate(decision['steps'], 1):
            lines = step.splitlines()
            prefix = f'{i}. '
            out.append(prefix + lines[0])
            out += [' ' * len(prefix) + line if line else '' for line in lines[1:]]
            out.append('')
        out.append('')
        if decision['boundaries']:
            out += ['**适用边界**', '', *[f'- {item}' for item in decision['boundaries']], '']
        if decision['examples']:
            out += ['> [!example]- 补充例子与自查', '>']
            for item in decision['examples']:
                lines = item.splitlines()
                out.append('> - ' + lines[0])
                out += ['>   '+line if line else '>' for line in lines[1:]]
                out.append('>')
            out.append('')
        if c["note"]:
            out += [c["note"], ""]
        role = None
        for m in c["members"]:
            if m['role'] != role:
                role = m['role']
                out += [f'**{role}题目**', '']
            if m["path"]:
                card_ref = markdown_link(source, m['path'], m['topic'])
            else:
                card_ref = m["topic"]
            out += [f"- {m['role']}：{card_ref} · {m['status']} · 最近记录 {m['last_review']} · 到期 {m['next_review']}"]
        siblings = [s for s in rows if s["family"] == c["family"] and s["id"] != c["id"]]
        if siblings:
            out += ["", "同方法族（不等于同簇）：" + "、".join(ref(s) for s in siblings)]
        out.append("")
    if data["unclustered"] or data["warnings"]:
        out += ["## 待核对", "", *[f"- {w}" for w in data["warnings"]]]
        out += [f"- 未归类：{c['topic']}（qid-{c['qid']}）" for c in data["unclustered"]]
    return "\n".join(out).rstrip() + "\n"
