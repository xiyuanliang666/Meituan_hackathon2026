"""Deduplicate xhs_links.txt — O(n) single pass, preserves order, keeps first occurrence."""
from pathlib import Path

INPUT = Path(__file__).resolve().parent.parent / "mock_data" / "xhs_links.txt"


def dedup(lines: list[str]) -> tuple[list[str], int]:
    seen = set()
    result: list[str] = []
    dupes = 0
    for line in lines:
        stripped = line.strip()
        # keep comments and blank lines as-is
        if not stripped or stripped.startswith("#"):
            result.append(line)
            continue
        if stripped in seen:
            dupes += 1
            continue
        seen.add(stripped)
        result.append(line)
    return result, dupes


def main() -> None:
    original = INPUT.read_text(encoding="utf-8").splitlines(keepends=True)
    deduped, dupes = dedup(original)
    INPUT.write_text("".join(deduped), encoding="utf-8")
    print(f"Done. {dupes} duplicate(s) removed, {len(original)} → {len(deduped)} lines.")


if __name__ == "__main__":
    main()
