#!/usr/bin/env python3
"""将变式反馈和最终记忆卡写回同一张 408 卡；不记录一次 SRS 复习。

用法：python3 update_408_reflection.py CARD --feedback TEXT
  [--memory-point TEXT --memory-trap TEXT --core-rule TEXT --exam-action TEXT]

四个记忆字段需同时提供，且只在判卷确认核心理解后使用。
只更新五模块题卡的模块4/5，兼容旧模块标题和折叠正文。
"""
import argparse
import json
import re

from archive_ops import extract_heading_block
from create_wrong_card import find_unwrapped_math_excerpt, has_inline_display_math_text, prose_outside_code
from cs_card_layout import SOP, VARIANT, extract_module, module_span, replace_module, unfold_callout
from env_util import atomic_write, json_error
from frontmatter import parse_frontmatter
from update_card import resolve_card_path

FEEDBACK_TITLE = '验收反馈（本次结论、推理与前提）'
MEMORY_TITLE = '错题记忆卡（沉淀已验证的规则）'
STATE_RE = re.compile(r'^\*\*变式状态：\*\*[^\n]*(?:\n|$)')


def validate_content(name, value):
    if not value.strip():
        raise ValueError(f'{name} 不能为空')
    if re.search(r'^#{1,3} ', prose_outside_code(value), re.M):
        raise ValueError(f'{name} 内部只使用四级或更深标题，避免覆盖题卡模块')
    if find_unwrapped_math_excerpt(value) or has_inline_display_math_text(value):
        raise ValueError(f'{name} 的公式须用 $...$ 或独立成行的 $$...$$')
    if '待补充' in value:
        raise ValueError(f'{name} 不能包含待补充占位符')


def upsert_subsection(text, name, title, content):
    if module_span(text, name, 4):
        return replace_module(text, name, content, 4).strip()
    return text.rstrip() + f'\n\n#### {title}\n\n' + content.strip()


def update_reflection(text, feedback, memory=None):
    """纯正文转换，调用者负责真实判卷；不得以格式修改推断掌握度。"""
    validate_content('--feedback', feedback)
    if memory is not None and len(memory) != 4:
        raise ValueError('最终记忆卡必须包含考点、核心陷阱、正确规则、考场动作四个字段')
    variant = extract_module(text, VARIANT)
    sop = extract_module(text, SOP)
    if not variant or not sop:
        raise ValueError('需要唯一的提炼 SOP 和变式拷问模块；旧八栏题卡须先按原题证据整理')
    variant = STATE_RE.sub('', unfold_callout(variant), count=1).strip()
    variant = upsert_subsection(variant, '验收反馈', FEEDBACK_TITLE, feedback)
    state = '已验收（仅指本次变式）' if memory else '已作答'
    result = replace_module(text, VARIANT, f'**变式状态：** {state}\n\n{variant}')
    if memory:
        names = ['考点', '核心陷阱', '正确规则', '考场动作']
        for name, value in zip(names, memory):
            validate_content(name, value)
        sop = unfold_callout(sop)
        # 初归档的一句话规则由最终记忆卡收敛，保留前面的完整 SOP 和口令。
        span = module_span(sop, '正确规则', 4)
        if span:
            sop = sop[:span[0]] + sop[span[2]:]
        block = '\n\n'.join(f'**{name}：** {value.strip()}' for name, value in zip(names, memory))
        sop = upsert_subsection(sop, '错题记忆卡', MEMORY_TITLE, block)
        result = replace_module(result, SOP, sop)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('card_path')
    parser.add_argument('--feedback', required=True)
    for name in ['memory-point', 'memory-trap', 'core-rule', 'exam-action']:
        parser.add_argument('--' + name, default='')
    args = parser.parse_args()
    values = [args.memory_point, args.memory_trap, args.core_rule, args.exam_action]
    if any(values) and not all(v.strip() for v in values):
        json_error('最终记忆卡需要同时提供 --memory-point、--memory-trap、--core-rule、--exam-action')
    try:
        path, wrongbook = resolve_card_path(args.card_path)
        if path.relative_to(wrongbook).parts[0] != '408':
            raise ValueError('该命令只更新错题本/408/ 内的题卡')
        text = path.read_text(encoding='utf-8')
        fm, body, _ = parse_frontmatter(text)
        if not fm.get('question_id') or not body:
            raise ValueError('题卡缺少 question_id 或正文')
        updated_body = update_reflection(body, args.feedback, values if all(values) else None)
        for heading in ['题目', '所属元技能', '相关题目', '历史记录']:
            if extract_heading_block(body, heading, 3) != extract_heading_block(updated_body, heading, 3):
                raise ValueError(f'检测到受保护区块变化：{heading}')
        # 原封保留 YAML 字节，包括扩展属性、引号、注释与字段顺序。
        updated = text[:-len(body)] + updated_body
        if parse_frontmatter(updated)[0] != fm:
            raise ValueError('检测到属性变化，停止写入')
        changed = updated != text
        if changed:
            atomic_write(path, updated)
    except (ValueError, FileNotFoundError, OSError) as exc:
        json_error(str(exc))
    print(json.dumps({'path': str(path), 'changed': changed, 'memory_card_updated': all(values),
                      'review_record_added': False, 'attributes_preserved': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
