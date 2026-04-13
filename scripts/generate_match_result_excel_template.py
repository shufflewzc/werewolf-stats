from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "assets" / "templates"
LEGACY_OUTPUT_FILE = OUTPUT_DIR / "match-result-upload-template.xlsx"
PREPARED_FORMULA_ROWS = 1000
WEREWOLF_ROLE_KEYWORDS = (
    "狼",
    "石像鬼",
    "恶灵骑士",
    "黑蝙蝠",
    "血月使徒",
)

RECORD_HEADERS = [
    "competition_name",
    "season_name",
    "match_id",
    "score_model",
    "played_on",
    "format",
    "winning_camp",
    "mvp_player_name",
    "svp_player_name",
    "scapegoat_player_name",
    "seat",
    "team_name",
    "player_name",
    "role",
    "camp",
    "result_points",
    "result",
    "vote_points",
    "behavior_points",
    "special_points",
    "adjustment_points",
    "points_earned",
    "notes",
]

DEFAULT_TEMPLATE_COLUMNS = [(header, header) for header in RECORD_HEADERS]
JCDS_TEMPLATE_COLUMNS = [
    ("seat", "座位号"),
    ("team_name", "战队名"),
    ("player_name", "选手"),
    ("match_id", "局号"),
    ("role", "身份"),
    ("result_points", "胜负分"),
    ("vote_points", "投票分"),
    ("behavior_points", "行为分"),
    ("special_points", "特殊分"),
    ("adjustment_points", "违规分"),
    ("points_earned", "单局积分"),
    ("camp", "阵营"),
    ("result", "结果"),
    ("competition_name", "赛事名称"),
    ("season_name", "赛季"),
    ("played_on", "日期"),
    ("format", "板型"),
    ("winning_camp", "胜利阵营"),
    ("score_model", "积分模型"),
    ("mvp_player_name", "MVP"),
    ("svp_player_name", "SVP"),
    ("scapegoat_player_name", "背锅"),
    ("notes", "备注"),
]


@dataclass(frozen=True)
class FormulaCell:
    formula: str
    cached_value: str | None = None


def build_sample_rows(
    competition_name: str,
    season_name: str,
    score_model: str,
) -> list[dict[str, object]]:
    common = {
        "competition_name": competition_name,
        "season_name": season_name,
        "stage": "regular_season",
        "match_id": "gz-s-260410-01",
        "score_model": score_model,
        "played_on": "2026-04-10",
        "format": "经典十二人局",
        "duration_minutes": 60,
        "winning_camp": "villagers",
        "mvp_player_name": "",
        "svp_player_name": "",
        "scapegoat_player_name": "",
        "notes": "一行就是一个选手在这一局里的数据；系统会优先按比赛编号定位比赛。战队分组、赛段、房间都沿用预创建比赛，这里不需要填写。MVP/SVP/背锅列填“是”或留空即可。",
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
            "mvp_player_name": "是",
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
            "svp_player_name": "是",
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
            "notes": "",
        },
    ]
    return [{**common, **player_row} for player_row in player_rows]


TEMPLATE_CONFIGS = [
    ("generic", "通用", "示例公开赛", "2026春季联赛", "standard", DEFAULT_TEMPLATE_COLUMNS),
    ("lal", "LAL", "LAL广州公开赛", "2026春季联赛", "standard", DEFAULT_TEMPLATE_COLUMNS),
    ("jcds", "京城大师赛", "京城大师赛广州公开赛", "2026春季联赛", "jingcheng_daily", JCDS_TEMPLATE_COLUMNS),
]


def excel_column_name(index: int) -> str:
    name = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name


def cell_xml(cell_ref: str, value: object, style_id: int = 0) -> str:
    if isinstance(value, FormulaCell):
        formula = escape(value.formula)
        if value.cached_value is None:
            return f'<c r="{cell_ref}" s="{style_id}"><f>{formula}</f></c>'
        cached_value = escape(value.cached_value)
        return f'<c r="{cell_ref}" s="{style_id}" t="str"><f>{formula}</f><v>{cached_value}</v></c>'
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
            value = row[column_index]
            if isinstance(value, FormulaCell):
                value = value.cached_value or ""
            max_length = max(max_length, len(str(value or "")) + 2)
        widths.append(min(max_length, 24))
    return widths


def build_formula_cell(
    field_name: str,
    row_number: int,
    column_refs: dict[str, str],
    max_row_number: int,
    cached_value: object = None,
) -> FormulaCell | None:
    role_ref = f"{column_refs['role']}{row_number}"
    match_ref = f"{column_refs['match_id']}{row_number}"
    result_points_ref = f"{column_refs['result_points']}{row_number}"
    camp_ref = f"{column_refs['camp']}{row_number}"
    camp_range = f"${column_refs['camp']}$2:${column_refs['camp']}${max_row_number}"
    result_range = f"${column_refs['result']}$2:${column_refs['result']}${max_row_number}"
    match_range = f"${column_refs['match_id']}$2:${column_refs['match_id']}${max_row_number}"
    if field_name == "camp":
        keyword_checks = ",".join(
            f'ISNUMBER(SEARCH("{keyword}",{role_ref}))'
            for keyword in WEREWOLF_ROLE_KEYWORDS
        )
        formula = f'IF({role_ref}="","",IF(OR({keyword_checks}),"werewolves","villagers"))'
        cached_text = None if cached_value in (None, "") else str(cached_value)
        return FormulaCell(formula=formula, cached_value=cached_text)
    if field_name == "result":
        formula = f'IF({result_points_ref}="","",IF(ROUND({result_points_ref},2)=5,"win","loss"))'
        cached_text = None if cached_value in (None, "") else str(cached_value)
        return FormulaCell(formula=formula, cached_value=cached_text)
    if field_name == "winning_camp":
        formula = (
            f'IF({match_ref}="","",'
            f'IFERROR(LOOKUP(2,1/(({match_range}={match_ref})*({result_range}="win")),{camp_range}),""))'
        )
        cached_text = None if cached_value in (None, "") else str(cached_value)
        return FormulaCell(formula=formula, cached_value=cached_text)
    return None


def build_sheet_rows(
    columns: list[tuple[str, str]],
    sample_rows: list[dict[str, object]],
) -> list[list[object]]:
    column_refs = {
        field_name: excel_column_name(index)
        for index, (field_name, _label) in enumerate(columns, start=1)
    }
    max_row_number = PREPARED_FORMULA_ROWS + 1
    rows: list[list[object]] = []
    for row_offset in range(PREPARED_FORMULA_ROWS):
        row_number = row_offset + 2
        source_row = sample_rows[row_offset] if row_offset < len(sample_rows) else {}
        row_values: list[object] = []
        for field_name, _label in columns:
            formula_cell = None
            if {"match_id", "role", "result_points", "camp", "result"}.issubset(column_refs):
                formula_cell = build_formula_cell(
                    field_name,
                    row_number,
                    column_refs,
                    max_row_number,
                    source_row.get(field_name),
                )
            row_values.append(formula_cell if formula_cell is not None else source_row.get(field_name, ""))
        rows.append(row_values)
    return rows


def build_sheet_xml(columns: list[tuple[str, str]], rows: list[list[object]]) -> str:
    preview_rows = [[label for _, label in columns], *rows[: max(3, len(rows[:3]))]]
    widths = auto_widths(preview_rows)
    max_col = max((len(row) for row in preview_rows), default=1)
    last_cell = f"{excel_column_name(max_col)}{len(rows) + 1}"
    row_xml: list[str] = []
    for row_index, row in enumerate([[label for _, label in columns], *rows], start=1):
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
  <calcPr calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>
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


def write_workbook(
    slug: str,
    competition_name: str,
    season_name: str,
    score_model: str,
    columns: list[tuple[str, str]],
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sample_rows = build_sample_rows(competition_name, season_name, score_model)
    sheet_rows = build_sheet_rows(columns, sample_rows)
    for suffix in ("", "-v2"):
        output_file = build_output_path(slug, suffix)
        try:
            with ZipFile(output_file, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", content_types_xml())
                archive.writestr("_rels/.rels", root_rels_xml())
                archive.writestr("xl/workbook.xml", workbook_xml())
                archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml())
                archive.writestr("xl/styles.xml", styles_xml())
                archive.writestr("xl/worksheets/sheet1.xml", build_sheet_xml(columns, sheet_rows))
            return output_file
        except PermissionError:
            if suffix == "-v2":
                raise
    raise RuntimeError(f"无法写入模板文件：{slug}")


def write_all_workbooks() -> list[Path]:
    outputs: list[Path] = []
    for slug, _label, competition_name, season_name, score_model, columns in TEMPLATE_CONFIGS:
        outputs.append(write_workbook(slug, competition_name, season_name, score_model, columns))
    if outputs:
        copyfile(outputs[0], LEGACY_OUTPUT_FILE)
        outputs.append(LEGACY_OUTPUT_FILE)
    return outputs


if __name__ == "__main__":
    for output in write_all_workbooks():
        print(output)
