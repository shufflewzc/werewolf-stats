from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets" / "templates"
OUTPUT_FILE = OUTPUT_DIR / "match-result-upload-template.xlsx"


MATCH_HEADERS = [
    "match_key",
    "import_mode",
    "match_id",
    "competition_name",
    "season_name",
    "stage",
    "round",
    "game_no",
    "played_on",
    "table_label",
    "format",
    "duration_minutes",
    "winning_camp",
    "mvp_player_id",
    "svp_player_id",
    "scapegoat_player_id",
    "notes",
]

MATCH_ROWS = [
    [
        "SAMPLE-001",
        "create",
        "",
        "LAL广州公开赛",
        "2026春季联赛",
        "regular_season",
        1,
        1,
        "2026-04-08",
        "A桌",
        "经典十二人局",
        60,
        "villagers",
        "GZ-2026S-001",
        "GZ-2026S-007",
        "",
        "示例行，可直接覆盖；如果是编辑已有比赛，可将 import_mode 改为 update 并填写 match_id。",
    ]
]

PLAYER_HEADERS = [
    "match_key",
    "seat",
    "player_id",
    "team_id",
    "role",
    "camp",
    "result",
    "points_earned",
    "stance_result",
    "notes",
]

PLAYER_ROWS = [
    ["SAMPLE-001", 1, "GZ-2026S-001", "LAL-GZ-2026S-001", "预言家", "villagers", "win", 3.0, "correct", ""],
    ["SAMPLE-001", 2, "GZ-2026S-002", "LAL-GZ-2026S-001", "女巫", "villagers", "win", 2.5, "correct", ""],
    ["SAMPLE-001", 3, "GZ-2026S-003", "LAL-GZ-2026S-001", "猎人", "villagers", "win", 2.0, "none", ""],
    ["SAMPLE-001", 4, "GZ-2026S-004", "LAL-GZ-2026S-001", "守卫", "villagers", "win", 1.5, "none", ""],
    ["SAMPLE-001", 5, "GZ-2026S-005", "LAL-GZ-2026S-002", "平民", "villagers", "win", 1.0, "incorrect", ""],
    ["SAMPLE-001", 6, "GZ-2026S-006", "LAL-GZ-2026S-002", "平民", "villagers", "win", 1.0, "none", ""],
    ["SAMPLE-001", 7, "GZ-2026S-007", "LAL-GZ-2026S-002", "平民", "villagers", "win", 2.8, "correct", "示例 SVP"],
    ["SAMPLE-001", 8, "GZ-2026S-008", "LAL-GZ-2026S-002", "平民", "villagers", "win", 0.8, "none", ""],
    ["SAMPLE-001", 9, "GZ-2026S-009", "LAL-GZ-2026S-003", "狼人", "werewolves", "loss", -0.5, "incorrect", ""],
    ["SAMPLE-001", 10, "GZ-2026S-010", "LAL-GZ-2026S-003", "狼人", "werewolves", "loss", -1.0, "incorrect", ""],
    ["SAMPLE-001", 11, "GZ-2026S-011", "LAL-GZ-2026S-003", "狼人", "werewolves", "loss", -1.5, "none", ""],
    ["SAMPLE-001", 12, "GZ-2026S-012", "LAL-GZ-2026S-003", "狼王", "werewolves", "loss", -2.0, "incorrect", ""],
]

INSTRUCTION_HEADERS = ["section", "rule", "details"]

INSTRUCTION_ROWS = [
    ["整体", "一个文件可以导入多场比赛", "用 match_key 关联 matches 和 players 两张表；同一场比赛的 12 行选手数据必须使用同一个 match_key。"],
    ["matches", "import_mode", "create 表示新增比赛；update 表示编辑已有比赛。新增时 match_id 留空，编辑时必须填写已有 match_id。"],
    ["matches", "必填字段", "competition_name、season_name、stage、round、game_no、played_on、table_label、format、duration_minutes、winning_camp、mvp_player_id、svp_player_id。"],
    ["matches", "winning_camp 取值", "只能填写 villagers 或 werewolves。"],
    ["matches", "背锅规则", "好人胜利时 scapegoat_player_id 留空；狼人胜利时必须填写，且要选失败阵营的选手。"],
    ["players", "每场比赛需要 12 行", "seat 建议填写 1 到 12；player_id 使用该赛季内的参赛 ID。数据库里不存在时，后续可以先按占位参赛 ID 录入。"],
    ["players", "camp 取值", "当前模板按业务规则只保留 villagers / werewolves。"],
    ["players", "result 取值", "只能填写 win 或 loss。"],
    ["players", "stance_result 取值", "填写 correct、incorrect 或 none；这个字段不是必填，不填时建议写 none。"],
    ["players", "points_earned", "支持整数或小数，模板示例使用一位小数。"],
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
    return (
        f'<c r="{cell_ref}" s="{style_id}" t="inlineStr">'
        f'<is><t xml:space="preserve">{text}</t></is>'
        "</c>"
    )


def auto_widths(rows: list[list[object]]) -> list[int]:
    column_count = max((len(row) for row in rows), default=0)
    widths: list[int] = []
    for column_index in range(column_count):
        max_length = 10
        for row in rows:
            if column_index >= len(row):
                continue
            value = row[column_index]
            display = "" if value is None else str(value)
            max_length = max(max_length, len(display) + 2)
        widths.append(min(max_length, 40))
    return widths


def build_sheet_xml(headers: list[object], rows: list[list[object]]) -> str:
    all_rows = [headers, *rows]
    if not all_rows:
        all_rows = [[]]
    widths = auto_widths(all_rows)
    max_col = max((len(row) for row in all_rows), default=1)
    max_col = max(max_col, 1)
    last_cell = f"{excel_column_name(max_col)}{len(all_rows)}"

    sheet_rows: list[str] = []
    for row_index, row in enumerate(all_rows, start=1):
        cells: list[str] = []
        for column_index, value in enumerate(row, start=1):
            cell_ref = f"{excel_column_name(column_index)}{row_index}"
            style_id = 1 if row_index == 1 else 0
            cells.append(cell_xml(cell_ref, value, style_id))
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    cols_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:{last_cell}"/>
  <sheetViews>
    <sheetView workbookViewId="0">
      <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
    </sheetView>
  </sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <cols>{cols_xml}</cols>
  <sheetData>{"".join(sheet_rows)}</sheetData>
</worksheet>
"""


def workbook_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="matches" sheetId="1" r:id="rId1"/>
    <sheet name="players" sheetId="2" r:id="rId2"/>
    <sheet name="instructions" sheetId="3" r:id="rId3"/>
  </sheets>
</workbook>
"""


def workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
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
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>
"""


def styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font>
      <sz val="11"/>
      <name val="Calibri"/>
      <family val="2"/>
    </font>
    <font>
      <b/>
      <sz val="11"/>
      <name val="Calibri"/>
      <family val="2"/>
    </font>
  </fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1">
    <border><left/><right/><top/><bottom/><diagonal/></border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
</styleSheet>
"""


def write_workbook() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUTPUT_FILE, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml())
        archive.writestr("_rels/.rels", root_rels_xml())
        archive.writestr("xl/workbook.xml", workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml())
        archive.writestr("xl/styles.xml", styles_xml())
        archive.writestr("xl/worksheets/sheet1.xml", build_sheet_xml(MATCH_HEADERS, MATCH_ROWS))
        archive.writestr("xl/worksheets/sheet2.xml", build_sheet_xml(PLAYER_HEADERS, PLAYER_ROWS))
        archive.writestr("xl/worksheets/sheet3.xml", build_sheet_xml(INSTRUCTION_HEADERS, INSTRUCTION_ROWS))
    return OUTPUT_FILE


if __name__ == "__main__":
    output = write_workbook()
    print(output)
