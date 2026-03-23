"""test log_progress.py"""
import json

from helpers import run_script


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
    log_path = vault_root / "学习日志" / "2026-03-23.md"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
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
