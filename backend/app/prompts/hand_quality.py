"""Prompts for hand image quality checking."""

SYSTEM_PROMPT = "你是一个手部图像质量检测器。只输出合法JSON，不要输出Markdown。"

USER_PROMPT = (
    "请检查这张手部图片是否满足以下所有条件：\n"
    "1. 手指朝上，手背平放拍摄\n"
    "2. 完整露出手部（五指都能看到）\n"
    "3. 五指微微张开，不并拢\n"
    "4. 光线明亮均匀\n"
    "5. 背景干净，无明显杂物\n\n"
    "另外，检查手指甲上是否有美甲（指甲油、甲片、彩绘、装饰等）。\n\n"
    "输出JSON格式：\n"
    '{"quality_pass":true/false,'
    '"fingers_up":true/false,"full_hand_visible":true/false,"fingers_spread":true/false,'
    '"bright_lighting":true/false,"clean_background":true/false,'
    '"issues":["不满足的条件描述"],'
    '"nail_art_detected":true/false}'
)
