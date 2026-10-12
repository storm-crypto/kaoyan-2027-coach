"""整卷模块分与得分率；不把缺少的分数当成零。"""
import math
from paper_wrong_questions import objective_max_score


# 数学题型满分共用卷型/年份判定；408 四科满分见清华大学出版社考试结构：
# https://www.tup.tsinghua.edu.cn/bookscenter/bookpreface?id=08987801
FOUR_OH_EIGHT_MAX = {"ds": 45, "co": 45, "os": 35, "cn": 25}


def number(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def module_scores(record):
    modules = {}
    if record["subject"] == "数学一":
        objective_maximum = objective_max_score(record['paper'], record['paper_type'])
        maxima = {'objective': objective_maximum}
        if record.get('section') != '选填':
            maxima['big'] = 150 - objective_maximum
        for name, maximum in maxima.items():
            score = record.get(f"score_{name}")
            if number(score):
                modules[name] = {"score": score, "max_score": maximum, "accuracy": score / maximum}
    elif record["subject"] == "408":
        for name, maximum in FOUR_OH_EIGHT_MAX.items():
            choice, big = record.get(f"score_choice_{name}"), record.get(f"score_big_{name}")
            parts = {key: value for key, value in (("choice", choice), ("big", big)) if number(value)}
            if not parts:
                continue
            parts["max_score"] = maximum
            if number(choice) and number(big):
                total = choice + big
                parts.update(score=total, accuracy=total / maximum)
            modules[name.upper()] = parts
    return modules
