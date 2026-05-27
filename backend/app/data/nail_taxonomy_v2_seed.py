"""Canonical v2 taxonomy seed — aligned with docs/nail_style_taxonomy_v2.md."""

TAXONOMY_V2_FIELDS: list[dict[str, str | int]] = [
    {"field_key": "color_system", "label_cn": "颜色体系", "value_type": "array", "dimension": "营销", "sort_order": 1},
    {"field_key": "style_tags", "label_cn": "风格标签", "value_type": "array", "dimension": "营销", "sort_order": 2},
    {"field_key": "scene_tags", "label_cn": "适用场景", "value_type": "array", "dimension": "营销", "sort_order": 3},
    {"field_key": "season_tags", "label_cn": "季节/节日", "value_type": "array", "dimension": "营销", "sort_order": 4},
    {
        "field_key": "skin_tone_suitability",
        "label_cn": "肤色适配",
        "value_type": "array",
        "dimension": "营销",
        "sort_order": 5,
    },
    {"field_key": "nail_technique", "label_cn": "工艺手法", "value_type": "array", "dimension": "工艺", "sort_order": 6},
    {"field_key": "nail_decoration", "label_cn": "装饰类型", "value_type": "array", "dimension": "工艺", "sort_order": 7},
    {"field_key": "nail_finish", "label_cn": "表面效果/封层", "value_type": "enum", "dimension": "工艺", "sort_order": 8},
    {"field_key": "nail_shape", "label_cn": "甲型", "value_type": "enum", "dimension": "工艺", "sort_order": 9},
    {"field_key": "nail_length", "label_cn": "甲长", "value_type": "enum", "dimension": "工艺", "sort_order": 10},
    {"field_key": "finger_shape", "label_cn": "手指形态", "value_type": "enum", "dimension": "手型", "sort_order": 11},
    {"field_key": "nail_bed_shape", "label_cn": "甲床形态", "value_type": "enum", "dimension": "手型", "sort_order": 12},
]

TAXONOMY_V2_OPTIONS: dict[str, list[str]] = {
    "color_system": [
        "裸色系",
        "白色系",
        "黑色系",
        "粉色系",
        "红色系",
        "橙色系",
        "黄色系",
        "绿色系",
        "蓝色系",
        "紫色系",
        "棕色系",
        "大地色系",
        "莫兰迪色系",
        "金色系",
        "银色系",
        "撞色系",
        "渐变色系",
        "透明色系",
        "糖果色系",
    ],
    "style_tags": [
        "简约",
        "精致",
        "优雅",
        "气质",
        "轻奢",
        "甜美",
        "温柔",
        "清新",
        "时尚",
        "百搭",
        "辣妹",
        "欧美风",
        "法式",
        "甜酷",
        "酷飒",
        "个性",
        "复古",
    ],
    "scene_tags": ["日常通勤", "职场", "约会", "婚礼", "派对/夜店", "度假", "学生日常"],
    "season_tags": [
        "春",
        "夏",
        "秋",
        "冬",
        "四季通用",
        "情人节",
        "新年/春节",
        "圣诞",
        "婚礼季",
    ],
    "skin_tone_suitability": ["冷白皮", "自然肤色", "暖黄皮", "深肤色", "全肤色通用"],
    "nail_technique": ["纯色", "法式", "渐变", "猫眼", "彩绘", "镭射/极光", "镜面", "晕染"],
    "nail_decoration": [
        "无装饰",
        "碎钻/小钻",
        "异形钻/大钻",
        "珍珠",
        "亮片/闪粉",
        "3D立体饰品",
        "金属箔/金线",
        "彩绘图案",
    ],
    "nail_finish": ["亮面", "磨砂", "镜面光", "猫眼光", "珠光", "unknown"],
    "nail_shape": ["圆形", "方圆形", "椭圆形", "杏仁形", "尖形", "棺材形", "芭蕾形", "unknown"],
    "nail_length": ["短甲", "中甲", "长甲", "超长甲", "unknown"],
    "finger_shape": ["修长", "标准", "短粗", "unknown"],
    "nail_bed_shape": ["窄甲床", "标准甲床", "宽甲床", "unknown"],
}

ARRAY_FIELD_KEYS = [f["field_key"] for f in TAXONOMY_V2_FIELDS if f["value_type"] == "array"]
ENUM_FIELD_KEYS = [f["field_key"] for f in TAXONOMY_V2_FIELDS if f["value_type"] == "enum"]
STYLE_TAG_FIELD_KEYS = [f["field_key"] for f in TAXONOMY_V2_FIELDS]

# Hand analyzer output -> taxonomy field values for recommendation
SKIN_TONE_PROFILE_MAP: dict[str, str] = {
    "冷白": "冷白皮",
    "自然肤": "自然肤色",
    "暖黄": "暖黄皮",
    "深肤": "深肤色",
}

HAND_SHAPE_PROFILE_MAP: dict[str, str] = {
    "修长": "修长",
    "标准": "标准",
    "短宽": "短粗",
}
