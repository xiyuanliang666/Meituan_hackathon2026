#!/usr/bin/env python3
"""CLI entry point: batch extract v2 taxonomy tags for the competition evaluation dataset.

Usage:
    cd backend
    python scripts/batch_tag_extract.py          # process all styles
    python scripts/batch_tag_extract.py --limit 5 # process first 5 styles only
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.tag_extractor import batch_extract_dataset_tags


def main():
    parser = argparse.ArgumentParser(description="Batch extract v2 taxonomy tags from competition dataset")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of styles to process")
    args = parser.parse_args()

    print(f"Starting batch tag extraction (limit={args.limit or 'all'})...")
    result = batch_extract_dataset_tags(limit=args.limit)

    print(f"\nDone.")
    print(f"  Total styles:   {result['total_styles']}")
    print(f"  Updated:        {result['updated_styles']}")
    print(f"  Failed:         {result['failed_styles']}")
    print(f"  Analysis modes: {result['analysis_modes']}")


if __name__ == "__main__":
    main()
