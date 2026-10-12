"""选填范围、独立归档与整卷趋势隔离。所有操作使用临时 vault。"""
import json
from pathlib import Path

import pytest

from helpers import run_script
from archive_ops import extract_heading_block, parse_subject_score_rows, replace_heading_block
from dashboard_payload import build_score_trends_payload
from score_record_lib import collect_score_records, parse_score_record
from test_paper_workflow import make_card


DAY = '2026-10-12'
SPECIAL_HEADING = '数学一选填专项成绩追踪'
FULL_HEADING = '数学一模拟成绩追踪'


def score(root, paper='2010真题', paper_type='真题', section='选填', total='40', extra=(), subject='数学一'):
    return run_script('record_paper_score.py', [str(root), subject, '--paper', paper,
        '--paper-type', paper_type, '--section', section, '--total', total, '--date', DAY, *extra])


def successful_score(root, **kwargs):
    rc, out, err = score(root, **kwargs)
    assert rc == 0, out + err
    result = json.loads(out)
    return parse_score_record(Path(result['record_path'])), result


def test_objective_smoke_fields_and_independent_archive(sample_archive, vault_root):
    full_before = extract_heading_block(sample_archive.read_text(), FULL_HEADING)
    stored, output = successful_score(vault_root, extra=['--wrong-questions', '3:不会'])
    text = Path(output['record_path']).read_text()
    assert stored['section'] == '选填' and stored['max_score'] == 56
    assert stored['total_score'] == stored['score_objective'] == 40
    assert stored['score_big'] is None and 'score_big:' not in text and '大题' not in stored['body']
    assert stored['wrong_questions'][0]['question_number'] == 3
    assert 'section: 选填' in text
    archive = sample_archive.read_text()
    assert extract_heading_block(archive, FULL_HEADING) == full_before
    assert '| 日期 | 卷型 | 卷子 | 选填得分 | 满分 | 主要问题 | 备注 |' in archive
    assert '| 2026-10-12 | 真题 | 2010真题 | 40 | 56 |' in extract_heading_block(archive, SPECIAL_HEADING)


@pytest.mark.parametrize('paper,paper_type,limit,maximum', [
    ('2010真题', '真题', 14, 56), ('2020真题', '真题', 14, 56),
    ('2021真题', '真题', 16, 80), ('未标年份真题', '真题', 16, 80),
    ('李林预测卷一', '模拟', 16, 80), ('2010模拟卷', '模拟', 16, 80),
])
def test_objective_question_and_score_boundaries(sample_archive, vault_root, paper, paper_type, limit, maximum):
    stored, _ = successful_score(vault_root, paper=paper, paper_type=paper_type, total=str(maximum),
        extra=['--wrong-questions', f'{limit}:不会', '--question-topics', f'{limit}:函数极限'])
    assert stored['max_score'] == maximum and stored['wrong_questions'][0]['question_number'] == limit
    before = {path: path.read_bytes() for path in vault_root.rglob('*.md')}
    rc, out, _ = score(vault_root, paper=paper, paper_type=paper_type,
                      extra=['--wrong-questions', f'{limit + 1}:不会'])
    assert rc == 1 and f'1–{limit}' in json.loads(out)['message']
    rc, out, _ = score(vault_root, paper=paper, paper_type=paper_type, total=str(maximum + 1))
    assert rc == 1 and f'0–{maximum}' in json.loads(out)['message']
    assert {path: path.read_bytes() for path in vault_root.rglob('*.md')} == before


def test_old_objective_question_15_rejected_without_writes(sample_archive, vault_root):
    before = sample_archive.read_bytes()
    rc, out, _ = score(vault_root, extra=['--wrong-questions', '15:不会'])
    assert rc == 1 and '1–14' in json.loads(out)['message']
    assert not (vault_root / '成绩记录').exists() and sample_archive.read_bytes() == before


@pytest.mark.parametrize('subject', ['408', '英语一'])
def test_objective_only_supports_math(sample_archive, vault_root, subject):
    before = sample_archive.read_bytes()
    rc, out, _ = score(vault_root, subject=subject)
    assert rc == 1 and '只支持数学一' in json.loads(out)['message']
    assert not (vault_root / '成绩记录').exists() and sample_archive.read_bytes() == before


def test_objective_forces_objective_score_and_omits_big_score(sample_archive, vault_root):
    stored, output = successful_score(vault_root, extra=['--score-objective', '10', '--score-big', '100'])
    assert stored['score_objective'] == 40 and 'score_big:' not in Path(output['record_path']).read_text()


def test_auto_links_objective_source_alias_and_limits_questions(sample_archive, vault_root):
    base_paper = '2010 数学一真题'
    make_card(vault_root, 3, paper=base_paper)
    make_card(vault_root, 14, paper=base_paper + '选填')
    make_card(vault_root, 15, paper=base_paper + '选填')
    stored, output = successful_score(vault_root, paper=base_paper)
    assert [question['question_number'] for question in stored['wrong_questions']] == [3, 14]
    assert output['linked_question_count'] == 2 and '1–14' in output['link_warnings'][0]['reason']


def test_full_and_objective_same_day_coexist_and_do_not_pollute_trends(sample_archive, vault_root):
    _, full_output = successful_score(vault_root, section='整卷', total='110',
                                         extra=['--score-objective', '40', '--score-big', '70'])
    full_record_before = Path(full_output['record_path']).read_bytes()
    full_table_before = extract_heading_block(sample_archive.read_text(), FULL_HEADING)
    trend_before = build_score_trends_payload(vault_root, sample_archive.read_text())
    _, objective_output = successful_score(vault_root)
    successful_score(vault_root, total='44')  # 同范围重试覆盖，不重复追加。
    assert objective_output['record_path'] != full_output['record_path']
    assert Path(full_output['record_path']).read_bytes() == full_record_before
    archive = sample_archive.read_text()
    assert extract_heading_block(archive, FULL_HEADING) == full_table_before
    special_table = extract_heading_block(archive, SPECIAL_HEADING)
    assert special_table.count('| 2026-10-12 | 真题 | 2010真题 |') == 1
    assert '| 44 | 56 |' in special_table
    assert len(collect_score_records(vault_root)) == 1
    assert len(collect_score_records(vault_root, section=None)) == 2
    assert collect_score_records(vault_root, section='选填')[0]['total_score'] == 44
    rc, out, err = run_script('analyze_paper.py', [str(vault_root), '--subject', '数学一'])
    assert rc == 0, out + err
    assert [paper['total_score'] for paper in json.loads(out)['papers']] == [110]
    rc, out, err = run_script('analyze_paper.py', [str(vault_root), '--subject', '数学一', '--section', '选填'])
    assert rc == 0, out + err
    result = json.loads(out)
    assert result['section'] == '选填' and result['papers'][0]['total_score'] == 44
    assert result['papers'][0]['modules']['objective']['accuracy'] == 44 / 56
    trend = build_score_trends_payload(vault_root, archive)
    assert trend['math1']['latest']['total_score'] == 110
    assert trend['math1']['recent_rows'] == trend_before['math1']['recent_rows']
    assert any(row['paper'] == '2010真题' and row['total'] == '110'
               for row in parse_subject_score_rows(archive, '数学一'))


def test_objective_entry_does_not_migrate_legacy_full_score_table(sample_archive, vault_root):
    legacy = '| 日期 | 卷子 | 总分 | 主要问题 | 备注 |\n|------|------|------|------|------|\n| 2026-10-11 | 旧卷 | 100 | 保留 | 原样 |'
    sample_archive.write_text(replace_heading_block(sample_archive.read_text(), FULL_HEADING, legacy))
    successful_score(vault_root)
    assert extract_heading_block(sample_archive.read_text(), FULL_HEADING) == legacy


def test_wrong_events_cross_sections_deduplicate_and_new_objective_rate_is_80(sample_archive, vault_root):
    make_card(vault_root, 3, paper='2021真题选填')
    successful_score(vault_root, paper='2021真题', section='整卷', total='100')
    successful_score(vault_root, paper='2021真题', total='40', extra=['--wrong-questions', '3:不会'])
    rc, out, err = run_script('check_breakthrough_triggers.py', [str(vault_root), '--today', DAY])
    assert rc == 0, out + err
    result = json.loads(out)
    assert result['triggered'] == []  # 一次错误不能被两份成绩摘要和一张卡扩成三次。
    module_signals = [entry for entry in result['strong_signals'] if entry['reason'] == 'module_accuracy']
    assert len(module_signals) == 1 and module_signals[0]['accuracy'] == 0.5
    assert module_signals[0]['max_score'] == 80


@pytest.mark.parametrize('paper,paper_type,objective_max,big_max', [
    ('2010真题', '真题', 56, 94), ('2020真题', '真题', 56, 94),
    ('2021真题', '真题', 80, 70), ('未注明年份真题', '真题', 80, 70),
    ('李林预测卷一', '模拟', 80, 70), ('2010模拟卷', '模拟', 80, 70),
])
def test_analysis_full_module_maxima_follow_paper_year_and_type(
        sample_archive, vault_root, paper, paper_type, objective_max, big_max):
    successful_score(vault_root, paper=paper, paper_type=paper_type, section='整卷', total='90',
                     extra=['--score-objective', '48', '--score-big', '42'])
    rc, out, err = run_script('analyze_paper.py', [str(vault_root), '--subject', '数学一'])
    assert rc == 0, out + err
    modules = json.loads(out)['papers'][0]['modules']
    assert modules['objective']['max_score'] == objective_max
    assert modules['big']['max_score'] == big_max
    assert modules['objective']['accuracy'] == pytest.approx(48 / objective_max)
    assert modules['big']['accuracy'] == pytest.approx(42 / big_max)


def test_modern_trigger_uses_same_module_denominators_as_analysis(sample_archive, vault_root):
    # 48/80 与 42/70 正好 60%；旧分母会把大题误报为低于 60%。
    successful_score(vault_root, paper='2021边界卷', section='整卷', total='90',
                     extra=['--score-objective', '48', '--score-big', '42'])
    successful_score(vault_root, paper='2021低分卷', section='整卷', total='90',
                     extra=['--score-objective', '47', '--score-big', '43'])
    rc, out, err = run_script('check_breakthrough_triggers.py', [str(vault_root), '--today', DAY])
    assert rc == 0, out + err
    signals = [entry for entry in json.loads(out)['strong_signals'] if entry['reason'] == 'module_accuracy']
    assert [(entry['paper'], entry['module']) for entry in signals] == [('2021低分卷', 'objective')]
    assert signals[0]['max_score'] == 80 and signals[0]['accuracy'] == pytest.approx(47 / 80)
