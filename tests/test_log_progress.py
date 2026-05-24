"""test log_progress.py"""
import json
from pathlib import Path

from helpers import log_path as log_file, run_script


def test_log_progress_writes_log(sample_archive, vault_root):
    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-03-23",
        "--topic", "数学二重积分 + 408 操作系统复习",
        "--hours", "5",
        "--mode", "错题解析 / 复习",
        "--learned", "二重积分换元前先画区域",
        "--blocker", "OS 调度题里周转时间还是容易算乱",
        "--mastered", "积分区域判断|中高",
        "--review", "回看一遍 OS 调度指标",
        "--score", "数学一|真题|2025 数学一真题|145|150|后两道大题还不够稳",
        "--score", "408|套卷|王道八套卷 03|118|150|OS 和计网丢分偏多",
        "--coach-note", "今天的主线比较清楚，明天继续收口最卡的那一块。",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["archive_updated"] is False
    assert data["score_count"] == 2
    log_path_obj = log_file(vault_root, "2026-03-23")
    assert log_path_obj.exists()
    content = log_path_obj.read_text(encoding="utf-8")
    assert "数学二重积分 + 408 操作系统复习" in content
    assert "积分区域判断 - 信心：中高" in content
    assert "## 训练成绩记录" in content
    assert "| 数学一 | 真题 | 2025 数学一真题 | 145 | 150 | 96.7% | 后两道大题还不够稳 |" in content
    assert "| 408 | 套卷 | 王道八套卷 03 | 118 | 150 | 78.7% | OS 和计网丢分偏多 |" in content


def test_log_progress_updates_archive(sample_archive, vault_root):
    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-03-23",
        "--topic", "数学错题收尾",
        "--learned", "极坐标换元时先确定角度范围",
        "--weakness", "二重积分极坐标切换|数学一|高|最近三次都卡在画区域|待攻坚|明晚做一次专题复盘",
        "--error-pattern", "积分上下限混乱|数学一|4 次|2026-03-23|极坐标切换仍不稳",
        "--archive-next-step", "先把数学二重积分专题打穿",
        "--archive-next-step", "安排一次 408 OS 调度计时训练",
        "--archive-next-step", "英语阅读继续保速",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["archive_updated"] is True
    assert "短板雷达" in data["updated_sections"]
    archive_text = sample_archive.read_text(encoding="utf-8")
    assert "二重积分极坐标切换 | 数学一 | 高" in archive_text
    assert "积分上下限混乱 | 数学一 | 4 次 | 2026-03-23" in archive_text
    assert "1. 先把数学二重积分专题打穿" in archive_text


def test_log_progress_rejects_invalid_score_format(vault_root):
    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-03-23",
        "--topic", "数学错题收尾",
        "--score", "数学一|真题|2025 数学一真题|145",
    ])

    assert rc == 1
    data = json.loads(out)
    assert "score 参数格式错误" in data["message"]


def test_log_progress_stops_when_existing_log_is_unreadable(vault_root):
    log_path_obj = log_file(vault_root, "2026-03-23")
    original_bytes = b"\xff\xfe\xfd"
    log_path_obj.write_bytes(original_bytes)

    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-03-23",
        "--topic", "数学错题收尾",
    ])

    assert rc == 1
    data = json.loads(out)
    assert "已有日志读取失败" in data["message"]
    assert log_path_obj.read_bytes() == original_bytes


def test_log_progress_subject_score_syncs_archive_and_log(sample_archive, vault_root):
    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-03-23",
        "--topic", "数学和 408 各做了一套模拟",
        "--score", "数学一|真题训练|李林6套卷2|118|150|主要问题：级数、矩阵对角化、积分不等式；细节会崩但比上周稳",
        "--score", "408|真题训练|2024 真题|120|150|模块错题：DS 3 / CO 2 / OS 1 / CN 3；主要问题：DS 排序综合、CN 运输层；真题二刷依然有盲区",
        "--subject-score", "数学一|李林6套卷2|118|级数、矩阵对角化、积分不等式|细节会崩但比上周稳",
        "--subject-score", "408|2024 真题|3|2|1|3|120|DS 排序综合、CN 运输层|真题二刷依然有盲区",
    ])

    assert rc == 0
    data = json.loads(out)
    assert data["archive_updated"] is True
    assert "数学一模拟成绩追踪" in data["updated_sections"]
    assert "408模拟成绩追踪" in data["updated_sections"]
    assert data["score_count"] == 2
    log_text = log_file(vault_root, "2026-03-23").read_text(encoding="utf-8")
    assert "| 数学一 | 真题训练 | 李林6套卷2 | 118 | 150 | 78.7% | 主要问题：级数、矩阵对角化、积分不等式；细节会崩但比上周稳 |" in log_text
    assert "| 408 | 真题训练 | 2024 真题 | 120 | 150 | 80.0% | 模块错题：DS 3 / CO 2 / OS 1 / CN 3；主要问题：DS 排序综合、CN 运输层；真题二刷依然有盲区 |" in log_text
    assert "| 数学一 | 模拟 | 李林6套卷2 | 118 | 150 | 78.7% |" not in log_text
    assert "| 408 | 模拟 | 2024 真题 | 120 | 150 | 80.0% |" not in log_text
    archive_text = sample_archive.read_text(encoding="utf-8")
    assert "| 2026-03-23 | 模拟 | 李林6套卷2 | 118 | 级数、矩阵对角化、积分不等式 | 细节会崩但比上周稳 |" in archive_text
    assert "| 2026-03-23 | 真题 | 2024 真题 | 3 | 2 | 1 | 3 | 120 | DS 排序综合、CN 运输层 | 真题二刷依然有盲区 |" in archive_text


def test_log_progress_subject_score_requires_complete_fields(sample_archive, vault_root):
    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-03-23",
        "--topic", "408 模拟",
        "--subject-score", "408|2024 真题|3|2|1",
    ])

    assert rc == 1
    data = json.loads(out)
    assert "408 subject-score 参数格式错误" in data["message"]


def test_log_progress_includes_today_notes_section(vault_root):
    # 预置两篇今日笔记 + 一篇昨日笔记
    notes_dir = vault_root / "知识笔记" / "数学一" / "高数"
    (notes_dir / "ch1 函数 极限 连续").mkdir(parents=True, exist_ok=True)
    (notes_dir / "ch3 微分中值定理与泰勒公式").mkdir(parents=True, exist_ok=True)
    (notes_dir / "ch1 函数 极限 连续" / "Stolz 定理.md").write_text(
        "---\ncreated: 2026-05-24\n---\n正文\n", encoding="utf-8",
    )
    (notes_dir / "ch3 微分中值定理与泰勒公式" / "双中值.md").write_text(
        "---\ncreated: 2026-05-24\n---\n正文\n", encoding="utf-8",
    )
    (notes_dir / "ch1 函数 极限 连续" / "昨日.md").write_text(
        "---\ncreated: 2026-05-23\n---\n正文\n", encoding="utf-8",
    )

    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-05-24",
        "--topic", "高数复习",
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["notes_today"]["count"] == 2
    assert data["notes_today"]["missing_created"] == 0
    titles = sorted(e["title"] for e in data["notes_today"]["entries"])
    assert titles == ["Stolz 定理", "双中值"]

    log_text = log_file(vault_root, "2026-05-24").read_text(encoding="utf-8")
    assert "## 今日新增笔记" in log_text
    assert "Stolz 定理" in log_text
    assert "双中值" in log_text
    assert "今日合计 2 篇" in log_text
    # 不能错误地把昨日的拉进来
    assert "昨日" not in log_text


def test_log_progress_auto_fills_missing_created(vault_root):
    note = vault_root / "知识笔记" / "数学一" / "高数" / "ch1" / "无 frontmatter.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("纯正文笔记，没有 frontmatter。\n", encoding="utf-8")
    # 设置 mtime 为今天，让自动补 created = 今天
    import os
    import time
    today_ts = time.mktime((2026, 5, 24, 12, 0, 0, 0, 0, -1))
    os.utime(note, (today_ts, today_ts))

    rc, out, _ = run_script("log_progress.py", [
        str(vault_root),
        "--date", "2026-05-24",
        "--topic", "扫描测试",
    ])
    assert rc == 0
    data = json.loads(out)
    assert data["notes_today"]["frontmatter_filled"] == 1
    assert data["notes_today"]["count"] == 1
    text = note.read_text(encoding="utf-8")
    assert "created: 2026-05-24" in text


def test_log_progress_notes_section_regenerated_on_rerun(vault_root):
    note_dir = vault_root / "知识笔记" / "数学一" / "高数" / "ch1"
    note_dir.mkdir(parents=True, exist_ok=True)
    (note_dir / "A.md").write_text("---\ncreated: 2026-05-24\n---\n", encoding="utf-8")

    run_script("log_progress.py", [str(vault_root), "--date", "2026-05-24", "--topic", "首跑"])
    log_path_obj = log_file(vault_root, "2026-05-24")
    assert "A" in log_path_obj.read_text(encoding="utf-8")

    # 新增一篇，重跑应反映新内容
    (note_dir / "B.md").write_text("---\ncreated: 2026-05-24\n---\n", encoding="utf-8")
    run_script("log_progress.py", [str(vault_root), "--date", "2026-05-24", "--topic", "重跑"])
    text = log_path_obj.read_text(encoding="utf-8")
    assert "A" in text
    assert "B" in text
    assert "今日合计 2 篇" in text
