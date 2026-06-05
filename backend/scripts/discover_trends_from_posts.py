#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.trend_agent import discover_trends_from_posts


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover cross-post trend clusters from cleaned UGC posts")
    parser.add_argument("--input", required=True, help="Input cleaned UGC JSON path")
    parser.add_argument("--output", required=True, help="Output trend JSON path")
    parser.add_argument("--min-support", type=int, default=2, help="Minimum posts per trend cluster")
    parser.add_argument("--max-trends", type=int, default=20, help="Maximum trends to keep")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    posts = raw.get("posts")
    if not isinstance(posts, list):
        raise SystemExit("Input JSON must contain a top-level 'posts' array")

    payload = discover_trends_from_posts(posts, min_support=args.min_support, max_trends=args.max_trends)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"written: {output_path} source_posts={payload['source_post_count']} "
        f"candidates={payload['candidate_post_count']} trends={payload['trend_count']}"
    )


if __name__ == "__main__":
    main()
