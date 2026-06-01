"""
Tagging prompts for nail style image analysis.

The system prompt is a fixed instruction template.
The user prompt is built dynamically from the approved taxonomy values in the database.
"""

SYSTEM_PROMPT = (
    "你是美甲款式图结构化打标助手。只输出合法 JSON，不要输出 Markdown。"
    "必须对全部 12 个字段完成打标；数组字段只能从值域中选一个或多个；"
    "枚举字段只能选一个值；无法判断时数组填 []，枚举填 unknown。"
    "禁止自造值域外标签；若确有合适但值域没有的新词，写入 candidate_tags，格式为「字段名: 建议值」。"
    "字段名使用英文，字段值使用中文。"
)

USER_PROMPT_PREFIX = "请分析这张美甲款式图，输出 JSON，包含以下字段：\n"
USER_PROMPT_SUFFIX = (
    "- candidate_tags（数组，无溢出时填 []）\n"
    "打标原则：season_tags 若选「四季通用」则不再叠加其他季节；"
    "nail_decoration 若选「无装饰」则不再叠加其他装饰；"
    "skin_tone_suitability 若选「全肤色通用」则不再叠加其他肤色。"
)


def build_value_domain_lines(approved: dict[str, set[str]], field_defs: list[dict]) -> list[str]:
    """Build the value-domain lines for each taxonomy field from the approved DB values."""
    lines: list[str] = []
    for field in field_defs:
        key = str(field["field_key"])
        label = str(field["label_cn"])
        vtype = str(field["value_type"])
        values = sorted(approved.get(key, set()))
        if vtype == "array":
            lines.append(f"- {key}（{label}，数组，可多选）: {', '.join(values)}")
        else:
            lines.append(f"- {key}（{label}，枚举，单选）: {', '.join(values)}")
    return lines
