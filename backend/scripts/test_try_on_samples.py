import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.style import TryOnRequest
from app.services.dataset_loader import load_evaluation_pairs
from app.services.image_generation import generate_try_on_image


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a small random AI try-on sample test.")
    parser.add_argument("--count", type=int, default=3, help="Number of pairs to test.")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed.")
    parser.add_argument("--out", default="../docs/AI试戴抽样测试.md", help="Markdown report path.")
    args = parser.parse_args()

    pairs = load_evaluation_pairs()
    rng = random.Random(args.seed)
    samples = rng.sample(pairs, min(args.count, len(pairs)))

    rows = []
    for index, pair in enumerate(samples, start=1):
        print(f"[{index}/{len(samples)}] try-on {pair.pair_id}", flush=True)
        response = generate_try_on_image(
            TryOnRequest(
                user_id="sample-test",
                hand_image_url=pair.hand_image_url,
                style_image_url=pair.style_image_url,
                style_id=pair.pair_id,
            )
        )
        rows.append(
            {
                "pair_id": pair.pair_id,
                "hand_image_url": pair.hand_image_url,
                "style_image_url": pair.style_image_url,
                "result_image_url": response.result_image_url,
                "generation_mode": response.generation_mode,
                "warnings": "；".join(response.warnings),
            }
        )

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_report(rows), encoding="utf-8")
    print(f"report written: {output_path}", flush=True)


def _render_report(rows: list[dict[str, str]]) -> str:
    lines = [
        "# AI 试戴抽样测试",
        "",
        f"- 抽样数量：{len(rows)}",
        "- 说明：只随机测试少量官方手图和美甲图，不做全量生成。",
        "",
        "| 样本 | 生成模式 | 手部图片 | 美甲图片 | 试戴结果 | 备注 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row['pair_id']} | "
            f"{row['generation_mode']} | "
            f"[hand]({row['hand_image_url']}) | "
            f"[style]({row['style_image_url']}) | "
            f"[result]({row['result_image_url']}) | "
            f"{row['warnings'] or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
