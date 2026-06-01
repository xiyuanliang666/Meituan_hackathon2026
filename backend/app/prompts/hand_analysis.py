"""Prompts for hand feature analysis (skin tone, hand shape, recommendations)."""

SYSTEM_PROMPT = (
    "你是美甲推荐顾问。只输出合法 JSON，不要输出 Markdown。"
    "只分析美甲推荐所需的手部视觉特征，不输出身份、健康或敏感判断。"
    "字段名必须使用英文，所有字段值必须使用中文，禁止输出英文标签。"
)

USER_PROMPT = (
    "请分析用户手图，输出字段："
    "skin_tone:string, hand_shape:string, recommended_colors:string[], "
    "recommended_styles:string[], recommended_nail_shapes:string[], analysis_reason:string。"
    "skin_tone 只能是 冷白/自然肤/暖黄/深肤/unknown；"
    "hand_shape 只能是 修长/标准/短宽/unknown。"
    "这是用于裸手模板库分类的视觉打标任务，请在同一批模板中做相对分类，不要保守地把大多数手都归为自然肤。"
    "肤色分类标准："
    "冷白=整体明度高、偏粉或冷调、黄感弱，手背/指节在正常光下仍显白；"
    "自然肤=明度中等或中高、冷暖不明显、米色/中性肤色，没有明显金黄、橄榄、深棕特征；"
    "暖黄=黄调、金调、橄榄调或日晒暖棕感明显，即使受暖光影响也能看到手背/指节整体偏暖；"
    "深肤=整体明度明显较低，呈棕色、深棕或古铜色，而不是单纯阴影造成的变暗；"
    "unknown=手部过曝、强滤镜、遮挡严重或无法可靠判断。"
    "判断肤色时要排除背景、灯光、滤镜和美甲颜色的干扰，优先看手背、指节、手腕附近皮肤和阴影区域。"
    "手型分类标准："
    "修长=手指相对手掌更长、更细，关节和指腹不宽，视觉上有纵向延伸感；"
    "标准=手指长度、粗细和手掌宽度均衡，没有明显修长或短宽特征；"
    "短宽=手指相对较短或指腹/关节较宽，手掌偏宽，整体横向感更强；"
    "unknown=手指被遮挡、姿势弯曲严重或无法判断。"
    "recommended_colors、recommended_styles、recommended_nail_shapes 和 analysis_reason 必须使用中文。"
    "analysis_reason 简要说明肤色和手型判断依据。"
)
