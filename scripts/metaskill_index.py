#!/usr/bin/env python3
"""元技能索引的共享读取与分组逻辑。

数据源: `错题本/_元技能索引.json`（由 /wrong 持续追加，qid → 簇的唯一事实源）

被以下脚本复用:
- scan_due_reviews.py --by-cluster : /review 按簇成串复习
- build_daily_plan.py              : /plan_today 的复习时段按簇排

为什么要按簇而不按卡：逐卡复习 N 张要 N 次检索，且只学到 N 道题的解法；
按簇复习一次检索就拿到一个可迁移的决策。考场上的题不在错题本里，只有决策能迁移。
"""
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

INDEX_RELPATH = Path("错题本") / "_元技能索引.json"
QID_RE = re.compile(r"qid-([0-9a-f]{12})")

# 档案/周复盘反复点名的标杆弱项，排序时加权
LANDMARK_BOOST = 1.6
UNCLUSTERED_ID = "unclustered"


def load_index(obsidian_root: Path) -> Dict[str, Any]:
    """读取元技能索引；不存在时返回空结构（调用方应优雅退化为扁平模式）。"""
    path = Path(obsidian_root) / INDEX_RELPATH
    if not path.exists():
        return {"clusters": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"clusters": []}


def qid_from_text(text: str) -> Optional[str]:
    """从文件名或路径里抽出 12 位 qid 后缀。"""
    m = QID_RE.search(str(text))
    return m.group(1) if m else None


def build_qid_to_cluster(index: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """qid → 簇。`qids` 是主归属，`also` 是次归属（不覆盖已有主归属）。"""
    out: Dict[str, Dict[str, Any]] = {}
    for cluster in index.get("clusters", []):
        for qid in cluster.get("qids", []):
            out[qid] = cluster
        for qid in cluster.get("also", []):
            out.setdefault(qid, cluster)
    return out


def is_landmark(cluster: Dict[str, Any]) -> bool:
    note = cluster.get("note") or ""
    return "标杆" in note


def cluster_efficiency(cluster: Dict[str, Any], due_n: int) -> float:
    """每小时能清掉几张**到期**卡。注意用 due_n 而非簇总卡数——只有到期的才算收益。"""
    minutes = cluster.get("min") or 30
    eff = due_n / (minutes / 60.0)
    if is_landmark(cluster):
        eff *= LANDMARK_BOOST
    return eff


def group_due_by_cluster(
    cards: Sequence[Any],
    index: Dict[str, Any],
    key: Callable[[Any], str] = lambda c: c.get("path", ""),
) -> List[Dict[str, Any]]:
    """把到期卡按所属簇分组，并按「每小时清卡数」降序排。

    未在索引中的卡统一落到 `unclustered` 桶，永远排在最后——它提示索引该补了。
    """
    q2c = build_qid_to_cluster(index)
    buckets: Dict[str, Dict[str, Any]] = {}

    for card in cards:
        qid = qid_from_text(key(card))
        cluster = q2c.get(qid) if qid else None
        if cluster is None:
            bucket = buckets.setdefault(UNCLUSTERED_ID, {
                "cluster_id": UNCLUSTERED_ID,
                "skill": "（尚未归入元技能簇）",
                "ch": "", "family": None, "min": None,
                "landmark": False, "cards": [],
            })
        else:
            cid = cluster["id"]
            bucket = buckets.setdefault(cid, {
                "cluster_id": cid,
                "skill": cluster.get("skill", ""),
                "ch": cluster.get("ch", ""),
                "family": cluster.get("family"),
                "min": cluster.get("min"),
                "landmark": is_landmark(cluster),
                "note": cluster.get("note"),
                "cluster_total": len(cluster.get("qids", [])),
                "cards": [],
            })
        bucket["cards"].append(card)

    groups = []
    for bucket in buckets.values():
        bucket["due_count"] = len(bucket["cards"])
        if bucket["cluster_id"] == UNCLUSTERED_ID:
            bucket["efficiency"] = -1.0
            bucket["min"] = bucket["due_count"] * 15
        else:
            bucket["efficiency"] = round(
                cluster_efficiency({"min": bucket["min"], "note": bucket.get("note")},
                                   bucket["due_count"]), 2)
        groups.append(bucket)

    groups.sort(key=lambda g: (-g["efficiency"], -g["due_count"], g["cluster_id"]))
    return groups


def pick_clusters_for_session(
    groups: Sequence[Dict[str, Any]],
    target_cards: int,
    max_clusters: int = 3,
) -> List[Dict[str, Any]]:
    """从已排序的分组里挑够一次复习时段的簇。

    宁可略微超出 target_cards 也不要把一个簇拆开——拆开就退化成逐卡复习，
    失去了「同一动作换不同外衣」的检验作用。
    """
    picked: List[Dict[str, Any]] = []
    total = 0
    for group in groups:
        if picked and (total >= target_cards or len(picked) >= max_clusters):
            break
        picked.append(group)
        total += group["due_count"]
    return picked


def dominant_subject(group: Dict[str, Any], default: str = "数学一") -> str:
    """一个簇里出现最多的科目，用于把复习任务挂到对应科目时段。"""
    counts: Dict[str, int] = {}
    for card in group.get("cards", []):
        subj = card.get("subject") if isinstance(card, dict) else None
        if subj:
            counts[subj] = counts.get(subj, 0) + 1
    if not counts:
        return default
    return max(counts.items(), key=lambda kv: kv[1])[0]
