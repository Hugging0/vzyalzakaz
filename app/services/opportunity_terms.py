"""Conservative normalization shared by ingestion and legacy fact repair."""

import re


def work_type(value: str | None) -> str:
    key = re.sub(r"[\s_-]+", "", (value or "").lower())
    return {
        "fulltime": "full_time",
        "parttime": "part_time",
        "полнаязанятость": "full_time",
        "частичнаязанятость": "part_time",
        "fixed": "project",
        "fixedprice": "project",
        "freelance": "project",
        "contractor": "contract",
        "contract": "contract",
        "project": "project",
        "hourly": "hourly",
        "remote": "unknown",
        "": "unknown",
    }.get(key, value or "unknown")


def contains_capability(text: str, alias: str) -> bool:
    # Russian stems intentionally match endings; English names must be whole tokens.
    ending = "" if re.search(r"[а-яё]", alias) else r"(?!\w)"
    return bool(re.search(r"(?<!\w)" + re.escape(alias) + ending, text, re.I))


def budget_unit(text: str, employment_type: str | None = None) -> str:
    if work_type(employment_type) == "hourly" or re.search(
        r"(?:/\s*(?:h(?:ou)?r|час)|в час|за час|per hour|hourly)", text, re.I
    ):
        return "hour"
    if re.search(r"(?:/\s*(?:mo(?:nth)?|мес)|в месяц|per month|monthly)", text, re.I):
        return "month"
    if re.search(r"(?:/\s*(?:год|year)|в год|per year|annually)", text, re.I):
        return "year"
    if work_type(employment_type) == "project" or re.search(
        r"за (?:проект|заказ|ролик|видео)|/\s*заказ|разов|fixed.price", text, re.I
    ):
        return "project"
    return "unknown"


def is_recurring(text: str) -> bool | None:
    if re.search(
        r"(?:кажд\w* (?:день|недел|месяц)|ежедневн|еженедельн|ежемесячн|"
        r"на постоянной основе|постоянного сотрудничества|останется с нами надолго|"
        r"график\s*5/2|долгосрочн|per week|each week|every week|"
        r"reels in a month|ongoing weekly|регулярно публиковать|ведение и развитие|"
        r"\d+(?:\s*[-–]\s*\d+)?\s+(?:видео|ролик\w*|пост\w*|публикац\w*)"
        r"\s+в (?:месяц|день|недел\w*))",
        text,
        re.I,
    ):
        return True
    return None


def alternative_tools(text: str) -> list[list[str]]:
    names = {
        "Adobe Premiere Pro": r"premiere(?: pro)?",
        "Final Cut Pro": r"final cut(?: pro)?",
        "DaVinci Resolve": r"davinci(?: resolve)?",
        "CapCut": r"capcut",
    }
    result = []
    for line in re.split(r"[\n.!?]", text):
        if not re.search(r"\b(?:or|или|либо|whichever|choice)\b|на выбор", line, re.I):
            continue
        found = [name for name, pattern in names.items() if re.search(pattern, line, re.I)]
        if len(found) > 1:
            result.append(found)
    return result


def language_key(value: str) -> str:
    text = value.strip().casefold()
    for key, pattern in {
        "en": r"^(?:en(?:glish)?|англ(?:ийск\w*)?)(?:\b|[_-])",
        "ru": r"^(?:ru(?:ssian)?|рус(?:ский)?)(?:\b|[_-])",
    }.items():
        if re.search(pattern, text):
            return key
    return text.split("-")[0]


def explicit_english_requirement(text: str) -> bool:
    for line in text.splitlines():
        if re.search(r"не\s*(?:обязател|требуется)|not required|optional|не нужен", line, re.I):
            continue
        if re.search(
            r"(?:английск\w*|english)[\s:—–-]*"
            r"(?:(?:язык|уровень|уровня|на уровне|от|не ниже)\s+)?[abc][12]\b|"
            r"(?:знать|знание|владение)\s+английск\w*|(?:fluent|proficient)\s+(?:in\s+)?english",
            line,
            re.I,
        ):
            return True
    return False
