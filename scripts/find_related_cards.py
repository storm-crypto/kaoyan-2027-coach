#!/usr/bin/env python3
"""为错题卡查找「相关题目」，并可把 wikilink 回写进卡片。

用法:
  # 查询（只输出 JSON，不改文件）
  python3 find_related_cards.py [OBSIDIAN_ROOT] --question-id qid-xxxxxxxxxxxx
  python3 find_related_cards.py --topic [考点] --chapter [章节] --question [题面]

  # 回写单张卡
  python3 find_related_cards.py --question-id qid-xxx --write

  # 一次性回填索引中的全部卡片
  python3 find_related_cards.py --backfill

  环境变量 KAOYAN_OBSIDIAN_ROOT 可替代 CLI 参数

两种工作模式:
- lookup（qid 已在元技能索引里）：直接返回同簇兄弟卡；同簇不足 2 张时，
  再按 family 向外扩一跳补齐。这是主路径，精度最高。
- predict（qid 不在索引里，即刚建的新卡）：按 topic 词元重叠 + 同叶子章节 +
  题面结构相似度打分，返回候选，并推荐它最该加入哪个簇。

注意: error_tags 字段在本库中不可用作信号（300 张卡 539 个标签、529 个只出现一次），
      因此本脚本刻意不使用它。
"""
import argparse
import difflib
import json
import re
from pathlib import Path

from env_util import resolve_obsidian_root

INDEX_RELPATH = Path("错题本") / "_元技能索引.json"
SECTION_TITLE = "### 相关题目"
HISTORY_TITLE = "### 历史记录"
QID_RE = re.compile(r"qid-([0-9a-f]{12})")

# 打分权重（predict 模式）
W_TOPIC = 0.50
W_CHAPTER = 0.30
W_QUESTION = 0.20
MIN_SCORE = 0.18


def load_index(root: Path) -> dict:
    path = root / INDEX_RELPATH
    if not path.exists():
        return {"clusters": []}
    return json.loads(path.read_text(encoding="utf-8"))


def scan_cards(root: Path) -> dict:
    """qid -> {qid, path, stem, topic, chapter, question}"""
    cards = {}
    base = root / "错题本"
    if not base.exists():
        return cards
    for md in base.rglob("*.md"):
        m = QID_RE.search(md.name)
        if not m:
            continue
        text = md.read_text(encoding="utf-8", errors="ignore")
        topic = _frontmatter(text, "topic")
        cards[m.group(1)] = {
            "qid": m.group(1),
            "path": md,
            "stem": md.stem,
            "topic": topic,
            "chapter": md.parent.name,
            "chapter_path": str(md.parent.relative_to(base)),
            "question": _section(text, "题目"),
        }
    return cards


def _frontmatter(text: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def _section(text: str, name: str) -> str:
    m = re.search(rf"###\s*{name}\s*\n(.*?)(?=\n###|\Z)", text, re.S)
    return m.group(1).strip() if m else ""


def normalize_math(text: str) -> str:
    """把题面压成可比较的骨架：去掉题号、LaTeX 装饰、空白与标点。"""
    t = re.sub(r"例\s*\d+|\(\s*[IVXivx0-9]+\s*\)", "", text)
    t = re.sub(r"\\(mathrm|left|right|frac|displaystyle|,|;|!|quad|qquad)", "", t)
    t = re.sub(r"[\s$（）()\[\]{}<>,.，。；;：:\-—+*/\\|'\"]", "", t)
    return t


def tokenize_topic(topic: str) -> set:
    """把中文 topic 切成 2-gram 词元集合，用于重叠打分。"""
    t = re.sub(r"[\s（）()\[\]，。、·]", "", topic)
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def build_qid_to_cluster(index: dict) -> dict:
    out = {}
    for c in index.get("clusters", []):
        for q in c.get("qids", []):
            out[q] = c
        for q in c.get("also", []):
            out.setdefault(q, c)
    return out


def lookup_related(qid: str, index: dict, cards: dict, limit: int) -> list:
    """qid 已在索引里：返回同簇兄弟，不足则按 family 扩一跳。"""
    q2c = build_qid_to_cluster(index)
    cluster = q2c.get(qid)
    if not cluster:
        return []
    results = []
    siblings = [q for q in cluster.get("qids", []) + cluster.get("also", []) if q != qid]
    for q in siblings:
        if q in cards:
            results.append({
                "qid": q,
                "stem": cards[q]["stem"],
                "topic": cards[q]["topic"],
                "reason": f"同元技能「{cluster['skill'][:24]}…」",
                "relation": "same_cluster",
                "cluster_id": cluster["id"],
                "score": 1.0,
            })
    if len(results) < 2:
        fam = cluster.get("family")
        seen = {qid} | set(siblings)
        for c in index.get("clusters", []):
            if c["id"] == cluster["id"] or c.get("family") != fam:
                continue
            for q in c.get("qids", []):
                if q in seen or q not in cards:
                    continue
                results.append({
                    "qid": q,
                    "stem": cards[q]["stem"],
                    "topic": cards[q]["topic"],
                    "reason": f"同族「{fam}」·簇 {c['id']}",
                    "relation": "same_family",
                    "cluster_id": c["id"],
                    "score": 0.6,
                })
                seen.add(q)
    return results[:limit]


def predict_related(topic: str, chapter: str, question: str, cards: dict,
                    index: dict, exclude: str, limit: int) -> dict:
    """新卡：按 topic 词元 + 同章节 + 题面相似度打分。"""
    my_tok = tokenize_topic(topic)
    my_q = normalize_math(question)
    scored = []
    for qid, c in cards.items():
        if qid == exclude:
            continue
        s_topic = jaccard(my_tok, tokenize_topic(c["topic"]))
        s_chap = 1.0 if chapter and chapter == c["chapter"] else 0.0
        s_q = 0.0
        if my_q and c["question"]:
            other = normalize_math(c["question"])
            if other:
                s_q = difflib.SequenceMatcher(None, my_q, other).ratio()
        total = W_TOPIC * s_topic + W_CHAPTER * s_chap + W_QUESTION * s_q
        if total < MIN_SCORE:
            continue
        bits = []
        if s_topic > 0.15:
            bits.append(f"考点词重叠 {s_topic:.2f}")
        if s_chap:
            bits.append("同章节")
        if s_q > 0.55:
            bits.append(f"题面近亲 {s_q:.2f}")
        scored.append({
            "qid": qid, "stem": c["stem"], "topic": c["topic"],
            "reason": "·".join(bits) or "弱相关",
            "relation": "predicted",
            "score": round(total, 3),
        })
    scored.sort(key=lambda x: -x["score"])
    top = scored[:limit]

    # 推荐加入哪个簇：看 top 命中最多的簇
    q2c = build_qid_to_cluster(index)
    votes = {}
    for r in top:
        c = q2c.get(r["qid"])
        if c:
            votes.setdefault(c["id"], {"cluster": c, "n": 0, "w": 0.0})
            votes[c["id"]]["n"] += 1
            votes[c["id"]]["w"] += r["score"]
    suggest = None
    if votes:
        best = max(votes.values(), key=lambda v: (v["w"], v["n"]))
        suggest = {
            "cluster_id": best["cluster"]["id"],
            "skill": best["cluster"]["skill"],
            "family": best["cluster"].get("family"),
            "votes": best["n"],
        }
    return {"related": top, "suggest_cluster": suggest}


def render_section(related: list) -> str:
    lines = [SECTION_TITLE]
    for r in related:
        lines.append(f"- [[{r['stem']}]]")
        lines.append(f"\t— {r['reason']}")
    return "\n".join(lines) + "\n"


def inject_section(path: Path, related: list) -> bool:
    """把 ### 相关题目 写进卡片；已存在则整段替换。幂等。"""
    if not related:
        return False
    text = path.read_text(encoding="utf-8")
    block = render_section(related)
    if SECTION_TITLE in text:
        new = re.sub(
            rf"{re.escape(SECTION_TITLE)}\s*\n.*?(?=\n###|\Z)",
            block.rstrip() + "\n",
            text, count=1, flags=re.S,
        )
    elif HISTORY_TITLE in text:
        new = text.replace(HISTORY_TITLE, block + "\n" + HISTORY_TITLE, 1)
    else:
        new = text.rstrip() + "\n\n" + block
    if new == text:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main():
    p = argparse.ArgumentParser(description="查找错题卡的相关题目并可回写 wikilink")
    p.add_argument("obsidian_root", nargs="?", default=None)
    p.add_argument("--question-id", dest="question_id", default="")
    p.add_argument("--topic", default="")
    p.add_argument("--chapter", default="")
    p.add_argument("--question", default="")
    p.add_argument("--limit", type=int, default=4)
    p.add_argument("--write", action="store_true", help="把结果回写进该卡")
    p.add_argument("--backfill", action="store_true", help="回填索引中全部卡片")
    p.add_argument("--dry-run", action="store_true", help="配合 --backfill 只预览")
    args = p.parse_args()

    root = resolve_obsidian_root(args.obsidian_root)
    index = load_index(root)
    cards = scan_cards(root)
    qid = args.question_id.replace("qid-", "").strip()

    if args.backfill:
        q2c = build_qid_to_cluster(index)
        written, skipped = 0, 0
        for q in list(q2c):
            if q not in cards:
                continue
            rel = lookup_related(q, index, cards, args.limit)
            if not rel:
                skipped += 1
                continue
            if args.dry_run:
                written += 1
            elif inject_section(cards[q]["path"], rel):
                written += 1
            else:
                skipped += 1
        print(json.dumps({
            "mode": "backfill", "dry_run": args.dry_run,
            "cards_in_index": len(q2c), "written": written, "skipped": skipped,
        }, ensure_ascii=False, indent=2))
        return

    if qid and qid in build_qid_to_cluster(index):
        rel = lookup_related(qid, index, cards, args.limit)
        out = {"mode": "lookup", "question_id": qid, "related": rel,
               "cluster_id": rel[0]["cluster_id"] if rel else None}
    else:
        topic = args.topic or (cards.get(qid, {}).get("topic", ""))
        chapter = args.chapter or (cards.get(qid, {}).get("chapter", ""))
        question = args.question or (cards.get(qid, {}).get("question", ""))
        res = predict_related(topic, chapter, question, cards, index, qid, args.limit)
        out = {"mode": "predict", "question_id": qid or None, **res}
        rel = res["related"]

    if args.write and qid and qid in cards:
        out["written"] = inject_section(cards[qid]["path"], rel)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
