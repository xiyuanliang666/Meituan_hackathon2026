from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app.config import get_settings
from app.schemas.dataset import EvaluationDataset, EvaluationPair, EvaluationStyle

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@lru_cache
def load_evaluation_dataset() -> EvaluationDataset:
    """Load the competition xlsx as seed data without introducing a DB."""
    path = _resolve_dataset_path(get_settings().eval_dataset_path)
    sheet_rows = _read_workbook_rows(path)
    hand_rows = sheet_rows.get("xl/worksheets/sheet1.xml", [])
    style_rows = sheet_rows.get("xl/worksheets/sheet2.xml", [])

    paired_rows = [
        row
        for row in hand_rows[1:]
        if len(row) >= 2 and _is_url(row[0]) and _is_url(row[1])
    ]
    hand_templates = [row[0] for row in paired_rows]

    pairs: list[EvaluationPair] = []
    for row in paired_rows:
        index = len(pairs) + 1
        pairs.append(
            EvaluationPair(
                pair_id=f"pair-{index:03d}",
                hand_image_url=row[0],
                style_image_url=row[1],
            )
        )

    styles: list[EvaluationStyle] = []
    for row in style_rows[1:]:
        style = _style_from_row(row, len(styles) + 1)
        if style:
            styles.append(style)

    return EvaluationDataset(hand_templates=hand_templates, styles=styles, pairs=pairs)


def load_evaluation_pairs() -> list[EvaluationPair]:
    return load_evaluation_dataset().pairs


def _resolve_dataset_path(configured_path: str) -> Path:
    path = Path(configured_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    if not path.exists():
        raise FileNotFoundError(f"evaluation dataset not found: {path}")
    return path


def _read_workbook_rows(path: Path) -> dict[str, list[list[str]]]:
    with ZipFile(path) as archive:
        names = archive.namelist()
        shared_strings = _read_shared_strings(archive, names)
        sheet_names = sorted(
            name
            for name in names
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
        workbook_rows: dict[str, list[list[str]]] = {}
        for sheet_name in sheet_names:
            root = ET.fromstring(archive.read(sheet_name))
            workbook_rows[sheet_name] = _read_sheet_rows(root, shared_strings)
        return workbook_rows


def _read_sheet_rows(root: ET.Element, shared_strings: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in root.findall(".//a:sheetData/a:row", NS):
        cells: dict[int, str] = {}
        for cell in row.findall("a:c", NS):
            cell_type = cell.attrib.get("t")
            value_node = cell.find("a:v", NS)
            value = "" if value_node is None else value_node.text or ""
            if cell_type == "s" and value:
                value = shared_strings[int(value)]
            cells[_column_index(cell.attrib.get("r", ""))] = value
        width = max(cells.keys(), default=-1) + 1
        values = [cells.get(index, "") for index in range(width)]
        rows.append(values)
    return rows


def _read_shared_strings(archive: ZipFile, names: list[str]) -> list[str]:
    if "xl/sharedStrings.xml" not in names:
        return []

    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("a:si", NS):
        texts = [node.text or "" for node in item.findall(".//a:t", NS)]
        values.append("".join(texts))
    return values


def _style_from_row(row: list[str], index: int) -> EvaluationStyle | None:
    urls = [value for value in row if value.startswith("http")]
    if len(urls) >= 2:
        return EvaluationStyle(
            style_id=f"style-seed-{index:03d}",
            original_style_image_url=urls[0],
            enhanced_style_image_url=urls[1],
        )
    if urls:
        return EvaluationStyle(style_id=f"style-seed-{index:03d}", enhanced_style_image_url=urls[0])
    return None


def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return max(index - 1, 0)


def _is_url(value: str) -> bool:
    return value.startswith("http")
