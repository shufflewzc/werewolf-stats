from __future__ import annotations

from pathlib import Path
from shutil import copyfile
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets" / "templates"
LEGACY_OUTPUT_FILE = OUTPUT_DIR / "match-result-upload-template.xlsx"

RECORD_HEADERS = [
    "competition_name",
    "season_name",
    "stage",
    "game_no",
    "score_model",
    "played_on",
    "group_label",
    "room_label",
    "format",
    "duration_minutes",
    "winning_camp",
    "mvp_player_name",
    "svp_player_name",
    "scapegoat_player_name",
    "seat",
    "team_name",
    "player_name",
    "role",
    "camp",
    "result",
    "result_points",
    "vote_points",
    "behavior_points",
    "special_points",
    "adjustment_points",
    "points_earned",
    "stance_result",
    "notes",
]


def build_sample_rows(competition_name: str, season_name: str, score_model: str) -> list[list[object]]:
    common = {
        "competition_name": competition_name,
        "season_name": season_name,
        "stage": "regular_season",
        "game_no": 1,
        "score_model": score_model,
        "played_on": "2026-04-10",
        "group_label": "A组",
        "room_label": "1号房",
        "format": "经典十二人局",
        "duration_minutes": 60,
        "winning_camp": "villagers",
        "mvp_player_name": "悟空",
        "svp_player_name": "宇白",
        "scapegoat_player_name": "",
        "notes": "一行就是一个选手在这一局里的数据；系统会优先按赛事、赛季、日期和局次定位比赛，如同日同局次重复则继续参考赛段、分组和房间。",
    }
    player_rows = [
        {
            "seat": 1,
            "team_name": "罗生门",
            "player_name": "悟空",
            "role": "预言家",
            "camp": "villagers",
            "result": "win",
            "result_points": 5,
            "vote_points": 0.5,
            "behavior_points": 0,
            "special_points": 0,
            "adjustment_points": 0,
            "points_earned": 5.5,
            "stance_result": "correct",
            "notes": "",
        },
        {
            "seat": 2,
            "team_name": "颜杀",
            "player_name": "宇白",
            "role": "女巫",
            "camp": "villagers",
            "result": "win",
            "result_points": 5,
            "vote_points": 0,
            "behavior_points": 0.5,
            "special_points": 0,
            "adjustment_points": 0,
            "points_earned": 5.5,
            "stance_result": "correct",
            "notes": "",
        },
        {
            "seat": 3,
            "team_name": "玛卡巴卡",
            "player_name": "铁柱伦",
            "role": "狼人",
            "camp": "werewolves",
            "result": "loss",
            "result_points": 0,
            "vote_points": 0,
            "behavior_points": 0,
            "special_points": 0,
            "adjustment_points": 0,
            "points_earned": 0,
            "stance_result": "incorrect",
            "notes": "",
        },
    ]
    rows: list[list[object]] = []
    for player_row in player_rows:
        merged = {**common, **player_row}
        rows.append([merged.get(header, "") for header in RECORD_HEADERS])
    return rows


TEMPLATE_CONFIGS = [
    ("generic", "通用", "示例公开赛", "2026春季联赛", "standard"),
    ("lal", "LAL", "LAL广州公开赛", "2026春季联赛", "standard"),
    ("jcds", "京城大师赛", "京城大师赛广州公开赛", "2026春季联赛", "jingcheng_daily"),
]


def excel_column_name(index: int) -> str:
    name = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name


def cell_xml(cell_ref: str, value: object, style_id: int = 0) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{cell_ref}" s="{style_id}"><v>{value}</v></c>'
    text = escape("" if value is None else str(value))
    return f'<c r="{cell_ref}" s="{style_id}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def auto_widths(rows: list[list[object]]) -> list[int]:
    column_count = max((len(row) for row in rows), default=0)
    widths: list[int] = []
    for column_index in range(column_count):
        max_length = 10
        for row in rows:
            if column_index >= len(row):
                continue
            max_length = max(max_length, len(str(row[column_index] or "")) + 2)
        widths.append(min(max_length, 24))
    return widths


def build_sheet_xml(rows: list[list[object]]) -> str:
    all_rows = [RECORD_HEADERS, *rows]
    widths = auto_widths(all_rows)
    max_col = max((len(row) for row in all_rows), default=1)
    last_cell = f"{excel_column_name(max_col)}{len(all_rows)}"
    row_xml: list[str] = []
    for row_index, row in enumerate(all_rows, start=1):
        cells: list[str] = []
        for column_index, value in enumerate(row, start=1):
            style_id = 1 if row_index == 1 else 0
            cells.append(cell_xml(f"{excel_column_name(column_index)}{row_index}", value, style_id))
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    cols_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:{last_cell}"/>
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols>{cols_xml}</cols>
  <sheetData>{"".join(row_xml)}</sheetData>
</worksheet>
"""


def workbook_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="records" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""


def workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
"""


def root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""


def content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
"""


def styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""


def build_output_path(slug: str, suffix: str = "") -> Path:
    return OUTPUT_DIR / f"match-result-upload-template-{slug}{suffix}.xlsx"


def write_workbook(slug: str, competition_name: str, season_name: str, score_model: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sample_rows = build_sample_rows(competition_name, season_name, score_model)
    for suffix in ("", "-v2"):
        output_file = build_output_path(slug, suffix)
        try:
            with ZipFile(output_file, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", content_types_xml())
                archive.writestr("_rels/.rels", root_rels_xml())
                archive.writestr("xl/workbook.xml", workbook_xml())
                archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml())
                archive.writestr("xl/styles.xml", styles_xml())
                archive.writestr("xl/worksheets/sheet1.xml", build_sheet_xml(sample_rows))
            return output_file
        except PermissionError:
            if suffix == "-v2":
                raise
    raise RuntimeError(f"无法写入模板文件：{slug}")


def write_all_workbooks() -> list[Path]:
    outputs: list[Path] = []
    for slug, _label, competition_name, season_name, score_model in TEMPLATE_CONFIGS:
        outputs.append(write_workbook(slug, competition_name, season_name, score_model))
    if outputs:
        copyfile(outputs[0], LEGACY_OUTPUT_FILE)
        outputs.append(LEGACY_OUTPUT_FILE)
    return outputs


if __name__ == "__main__":
    for output in write_all_workbooks():
        print(output)
