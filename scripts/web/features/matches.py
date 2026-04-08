from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import web_app as legacy

CAMP_OPTIONS = legacy.CAMP_OPTIONS
RequestContext = legacy.RequestContext
UploadedFile = legacy.UploadedFile
RESULT_OPTIONS = legacy.RESULT_OPTIONS
STAGE_OPTIONS = legacy.STAGE_OPTIONS
STANCE_OPTIONS = legacy.STANCE_OPTIONS
WINNING_CAMP_OPTIONS = legacy.WINNING_CAMP_OPTIONS
append_alert_query = legacy.append_alert_query
build_empty_match = legacy.build_empty_match
build_match_award_select = legacy.build_match_award_select
build_scoped_path = legacy.build_scoped_path
can_manage_matches = legacy.can_manage_matches
canonicalize_match_ids = legacy.canonicalize_match_ids
ensure_placeholder_players_for_matches = legacy.ensure_placeholder_players_for_matches
ensure_placeholder_users_for_player_ids = legacy.ensure_placeholder_users_for_player_ids
file_value = legacy.file_value
form_value = legacy.form_value
get_match_by_id = legacy.get_match_by_id
get_match_competition_name = legacy.get_match_competition_name
layout = legacy.layout
list_seasons = legacy.list_seasons
load_series_catalog = legacy.load_series_catalog
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
normalize_stance_result = legacy.normalize_stance_result
option_tags = legacy.option_tags
parse_match_form = legacy.parse_match_form
redirect = legacy.redirect
replace_match_path_id = legacy.replace_match_path_id
require_competition_manager = legacy.require_competition_manager
save_repository_state = legacy.save_repository_state
start_response_html = legacy.start_response_html
validate_match_awards = legacy.validate_match_awards
validate_match_competition_selection = legacy.validate_match_competition_selection
validate_match_season_selection = legacy.validate_match_season_selection

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DOWNLOAD_PATH = "/assets/templates/match-result-upload-template.xlsx"
EXCEL_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def parse_date_input(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        return None


def format_table_label(game_no: int) -> str:
    return f"{game_no}号桌"


def build_placeholder_match(
    competition_name: str,
    season_name: str,
    stage: str,
    round_no: int,
    game_no: int,
    played_on: str,
) -> dict[str, object]:
    match = build_empty_match(competition_name, season_name)
    match["match_id"] = "pending-new-match"
    match["stage"] = stage
    match["round"] = round_no
    match["game_no"] = game_no
    match["played_on"] = played_on
    match["table_label"] = format_table_label(game_no)
    match["format"] = "待补录"
    match["duration_minutes"] = 0
    match["winning_camp"] = "draw"
    match["mvp_player_id"] = ""
    match["svp_player_id"] = ""
    match["scapegoat_player_id"] = ""
    match["notes"] = "批量创建的待补录比赛，请稍后完善比赛详情。"
    return match


def build_batch_create_form(
    ctx: RequestContext,
    values: dict[str, str] | None = None,
) -> str:
    current = values or {
        "competition_name": form_value(ctx.query, "competition").strip(),
        "season": form_value(ctx.query, "season").strip(),
        "stage": "regular_season",
        "start_date": legacy.china_today_label(),
        "end_date": legacy.china_today_label(),
        "matches_per_day": "3",
        "round_start": "1",
    }
    competition_field_html = build_match_competition_field(
        current["competition_name"],
        ctx.current_user,
    )
    season_field_html = build_match_season_field(
        current["competition_name"],
        current["season"],
    )
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-4">
        <div>
          <h2 class="section-title mb-2">批量创建待补录比赛</h2>
          <p class="section-copy mb-0">先在指定赛季下批量生成赛程壳子，后续再逐场补录版型、时长、阵容和结果。适合一次创建整月赛程。</p>
        </div>
      </div>
      <form method="post" action="/matches/new">
        <input type="hidden" name="action" value="batch_create_matches">
        <div class="row g-3">
          <div class="col-12 col-xl-4">
            <label class="form-label">地区赛事页</label>
            {competition_field_html}
          </div>
          <div class="col-12 col-xl-3">
            <label class="form-label">赛季</label>
            {season_field_html}
          </div>
          <div class="col-12 col-md-6 col-xl-2">
            <label class="form-label">阶段</label>
            <select class="form-select" name="stage">
              {option_tags(STAGE_OPTIONS, current["stage"])}
            </select>
          </div>
          <div class="col-6 col-md-3 col-xl-1">
            <label class="form-label">起始轮次</label>
            <input class="form-control" name="round_start" type="number" min="1" value="{escape(current['round_start'])}">
          </div>
          <div class="col-6 col-md-3 col-xl-2">
            <label class="form-label">每天场数</label>
            <input class="form-control" name="matches_per_day" type="number" min="1" max="12" value="{escape(current['matches_per_day'])}">
          </div>
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">开始日期</label>
            <input class="form-control" name="start_date" type="date" value="{escape(current['start_date'])}">
          </div>
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">结束日期</label>
            <input class="form-control" name="end_date" type="date" value="{escape(current['end_date'])}">
          </div>
        </div>
        <div class="d-flex flex-wrap gap-2 mt-4">
          <button type="submit" class="btn btn-dark">批量创建比赛</button>
        </div>
      </form>
    </section>
    """


def build_excel_import_panel() -> str:
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-4">
        <div>
          <h2 class="section-title mb-2">Excel 批量补录比赛详情</h2>
          <p class="section-copy mb-0">支持一次上传多场比赛详情。你可以先批量创建待补录比赛，再用 Excel 通过 match_id 批量更新。</p>
        </div>
        <a class="btn btn-outline-dark" href="{escape(TEMPLATE_DOWNLOAD_PATH)}">下载上传模板</a>
      </div>
      <form method="post" action="/matches/new" enctype="multipart/form-data">
        <input type="hidden" name="action" value="import_match_excel">
        <div class="mb-3">
          <label class="form-label">选择 Excel 文件</label>
          <input class="form-control" type="file" name="match_excel_file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet">
        </div>
        <div class="small text-secondary">模板包含 `matches`、`players`、`instructions` 三张工作表。更新已有比赛时把 `import_mode` 设为 `update` 并填写 `match_id`。</div>
        <div class="d-flex flex-wrap gap-2 mt-4">
          <button type="submit" class="btn btn-dark">上传并导入</button>
        </div>
      </form>
    </section>
    """


def read_excel_sheet_rows(upload: UploadedFile, sheet_name: str) -> list[dict[str, str]]:
    with ZipFile(BytesIO(upload.data)) as archive:
        workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_target_by_id = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels_xml.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
        }
        target = ""
        for sheet in workbook_xml.findall("main:sheets/main:sheet", EXCEL_NS):
            if sheet.attrib.get("name") == sheet_name:
                relation_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
                target = rel_target_by_id.get(relation_id, "")
                break
        if not target:
            return []
        sheet_path = "xl/" + target.lstrip("/")
        sheet_xml = ET.fromstring(archive.read(sheet_path))

    rows: list[list[str]] = []
    for row in sheet_xml.findall("main:sheetData/main:row", EXCEL_NS):
        values: list[str] = []
        for cell in row.findall("main:c", EXCEL_NS):
            text = ""
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                text = "".join(node.text or "" for node in cell.findall(".//main:t", EXCEL_NS))
            else:
                value_node = cell.find("main:v", EXCEL_NS)
                text = value_node.text if value_node is not None and value_node.text is not None else ""
            values.append(text)
        rows.append(values)
    if not rows:
        return []
    headers = [str(item or "").strip() for item in rows[0]]
    return [
        {
            headers[index]: (row[index].strip() if index < len(row) else "")
            for index in range(len(headers))
            if headers[index]
        }
        for row in rows[1:]
        if any(str(value or "").strip() for value in row)
    ]


def validate_excel_upload(upload: UploadedFile | None) -> str:
    if upload is None or not upload.filename:
        return "请先选择要上传的 Excel 文件。"
    if Path(upload.filename).suffix.lower() != ".xlsx":
        return "目前只支持上传 .xlsx 格式的比赛模板。"
    if not upload.data:
        return "上传的 Excel 文件为空，请重新选择。"
    return ""


def parse_excel_int(value: str, field_label: str) -> int:
    try:
        return int(float(value.strip()))
    except ValueError as exc:
        raise ValueError(f"{field_label} 需要填写整数。") from exc


def parse_excel_float(value: str, field_label: str) -> float:
    try:
        return float(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field_label} 需要填写数字。") from exc


def build_match_from_excel_rows(
    match_row: dict[str, str],
    player_rows: list[dict[str, str]],
) -> dict[str, object]:
    match = build_empty_match(
        match_row.get("competition_name", "").strip(),
        match_row.get("season_name", "").strip(),
    )
    match["match_id"] = match_row.get("match_id", "").strip() or "pending-new-match"
    match["competition_name"] = match_row.get("competition_name", "").strip()
    match["season"] = match_row.get("season_name", "").strip()
    match["stage"] = match_row.get("stage", "").strip()
    match["round"] = parse_excel_int(match_row.get("round", ""), "round")
    match["game_no"] = parse_excel_int(match_row.get("game_no", ""), "game_no")
    match["played_on"] = match_row.get("played_on", "").strip()
    match["table_label"] = match_row.get("table_label", "").strip()
    match["format"] = match_row.get("format", "").strip()
    match["duration_minutes"] = parse_excel_int(match_row.get("duration_minutes", ""), "duration_minutes")
    match["winning_camp"] = match_row.get("winning_camp", "").strip()
    match["mvp_player_id"] = match_row.get("mvp_player_id", "").strip()
    match["svp_player_id"] = match_row.get("svp_player_id", "").strip()
    match["scapegoat_player_id"] = match_row.get("scapegoat_player_id", "").strip()
    match["notes"] = match_row.get("notes", "").strip()
    participants = []
    for player_row in sorted(player_rows, key=lambda item: parse_excel_int(item.get("seat", ""), "seat")):
        participants.append(
            {
                "player_id": player_row.get("player_id", "").strip(),
                "team_id": player_row.get("team_id", "").strip(),
                "seat": parse_excel_int(player_row.get("seat", ""), "seat"),
                "role": player_row.get("role", "").strip(),
                "camp": player_row.get("camp", "").strip(),
                "result": player_row.get("result", "").strip(),
                "points_earned": parse_excel_float(player_row.get("points_earned", ""), "points_earned"),
                "stance_result": player_row.get("stance_result", "").strip() or "none",
                "notes": player_row.get("notes", "").strip(),
            }
        )
    match["players"] = participants
    return match


def import_matches_from_excel(
    ctx: RequestContext,
    data: dict[str, object],
    upload: UploadedFile,
) -> tuple[list[dict[str, object]] | None, str]:
    try:
        match_rows = read_excel_sheet_rows(upload, "matches")
        player_rows = read_excel_sheet_rows(upload, "players")
    except Exception as exc:
        return None, f"解析 Excel 失败：{exc}"
    if not match_rows:
        return None, "Excel 中没有读取到 matches 工作表数据。"

    players_by_key: dict[str, list[dict[str, str]]] = {}
    for row in player_rows:
        match_key = row.get("match_key", "").strip()
        if match_key:
            players_by_key.setdefault(match_key, []).append(row)

    next_matches = [dict(match) for match in data["matches"]]
    existing_by_id = {match["match_id"]: match for match in next_matches}
    created_count = 0
    updated_count = 0

    for row in match_rows:
        match_key = row.get("match_key", "").strip()
        import_mode = (row.get("import_mode", "").strip() or "create").lower()
        match_id = row.get("match_id", "").strip()
        if import_mode not in {"create", "update"}:
            return None, f"match_key={match_key or '未填写'} 的 import_mode 只能是 create 或 update。"
        if import_mode == "update" and not match_id:
            return None, f"match_key={match_key or '未填写'} 更新已有比赛时必须填写 match_id。"
        if import_mode == "update" and match_id not in existing_by_id:
            return None, f"没有找到要更新的比赛：{match_id}。"
        if not match_key:
            return None, "matches 工作表中的每一行都必须填写 match_key。"

        current_match = build_match_from_excel_rows(row, players_by_key.get(match_key, []))
        competition_name = str(current_match["competition_name"] or "").strip()
        season_name = str(current_match["season"] or "").strip()
        if not can_manage_matches(ctx.current_user, data, competition_name):
            return None, f"你没有权限导入 {competition_name} 下的比赛。"
        competition_error = validate_match_competition_selection(data, competition_name)
        if competition_error:
            return None, competition_error
        season_error = validate_match_season_selection(data, competition_name, season_name)
        if season_error:
            return None, season_error
        award_error = validate_match_awards(current_match)
        if award_error:
            return None, f"{match_key} 导入失败：{award_error}"

        if import_mode == "update":
            for index, existing_match in enumerate(next_matches):
                if existing_match["match_id"] == match_id:
                    next_matches[index] = current_match
                    break
            updated_count += 1
        else:
            next_matches.append(current_match)
            created_count += 1

    summary = f"Excel 导入完成：新增 {created_count} 场，更新 {updated_count} 场。"
    return next_matches, summary


def batch_create_matches(
    competition_name: str,
    season_name: str,
    stage: str,
    start_date: str,
    end_date: str,
    round_start: int,
    matches_per_day: int,
) -> list[dict[str, object]]:
    start_dt = parse_date_input(start_date)
    end_dt = parse_date_input(end_date)
    if start_dt is None or end_dt is None:
        raise ValueError("请填写有效的开始日期和结束日期。")
    if end_dt < start_dt:
        raise ValueError("结束日期不能早于开始日期。")
    if round_start <= 0:
        raise ValueError("起始轮次必须大于 0。")
    if matches_per_day <= 0:
        raise ValueError("每天场数必须大于 0。")

    matches: list[dict[str, object]] = []
    current_dt = start_dt
    round_no = round_start
    while current_dt <= end_dt:
        played_on = current_dt.strftime("%Y-%m-%d")
        for game_no in range(1, matches_per_day + 1):
            matches.append(
                build_placeholder_match(
                    competition_name,
                    season_name,
                    stage,
                    round_no,
                    game_no,
                    played_on,
                )
            )
        current_dt += timedelta(days=1)
        round_no += 1
    return matches


def build_match_competition_field(
    current_competition_name: str,
    current_user: dict[str, object] | None = None,
) -> str:
    try:
        data = load_validated_data()
        catalog = load_series_catalog(data)
    except Exception:
        data = {"matches": []}
        catalog = []
    if current_user and not legacy.is_admin_user(current_user):
        catalog = [
            entry
            for entry in catalog
            if legacy.can_manage_matches(current_user, data, entry["competition_name"])
        ]

    if not catalog:
        return (
            f'<input class="form-control" name="competition_name" required value="{escape(current_competition_name)}">'
            '<div class="small text-secondary mt-2">当前没有你可管理的地区赛事页，请先联系管理员分配赛事负责人范围。</div>'
        )

    grouped_entries: dict[str, list[dict[str, object]]] = {}
    for entry in catalog:
        grouped_entries.setdefault(entry["region_name"], []).append(entry)

    option_groups: list[str] = []
    known_competitions = {entry["competition_name"] for entry in catalog}
    if current_competition_name and current_competition_name not in known_competitions:
        option_groups.append(
            f'<option value="{escape(current_competition_name)}" selected>{escape(current_competition_name)}（历史赛事）</option>'
        )
    for region_name, entries in grouped_entries.items():
        option_tags_html = []
        for entry in sorted(entries, key=lambda item: (item["series_name"], item["competition_name"])):
            selected = " selected" if entry["competition_name"] == current_competition_name else ""
            option_tags_html.append(
                f'<option value="{escape(entry["competition_name"])}"{selected}>{escape(entry["series_name"])} · {escape(entry["competition_name"])}</option>'
            )
        option_groups.append(
            f'<optgroup label="{escape(region_name)}">{"".join(option_tags_html)}</optgroup>'
        )

    return (
        f'<select class="form-select" id="match-competition-select" data-match-competition-select name="competition_name" required>{"".join(option_groups)}</select>'
        '<div class="small text-secondary mt-2">比赛会挂到已创建的地区赛事页下；如果没有对应赛事，请先去“系列赛管理”里创建。</div>'
    )


def build_match_season_field(
    current_competition_name: str,
    current_season_name: str,
) -> str:
    try:
        data = load_validated_data()
        catalog = load_series_catalog(data)
    except Exception:
        data = {"matches": []}
        catalog = []

    if not catalog:
        return (
            f'<input class="form-control" name="season" required value="{escape(current_season_name)}">'
            '<div class="small text-secondary mt-2">还没有系列赛目录时，可先手动输入赛季名称。</div>'
        )

    season_map: dict[str, list[str]] = {}
    for entry in catalog:
        season_names = list_seasons(
            data,
            entry["competition_name"],
            selected_season=current_season_name if entry["competition_name"] == current_competition_name else "",
        )
        if season_names:
            season_map[entry["competition_name"]] = season_names
    if current_competition_name and current_competition_name not in season_map and current_season_name:
        season_map[current_competition_name] = [current_season_name]
    selected_json = escape(json.dumps(season_map, ensure_ascii=False))
    return f"""
    <div class="match-season-picker" data-season-map='{selected_json}'>
      <select class="form-select" name="season" required data-match-season-select data-selected="{escape(current_season_name)}"></select>
      <div class="small text-secondary mt-2" data-match-season-helper>只显示当前正在进行中的赛季；赛季需要先在系列赛管理里配置起止时间。</div>
    </div>
    <script>
      (function() {{
        const scope = document.currentScript.previousElementSibling;
        if (!scope) return;
        const seasonMap = JSON.parse(scope.getAttribute("data-season-map") || "{{}}");
        const seasonSelect = scope.querySelector("[data-match-season-select]");
        const helper = scope.querySelector("[data-match-season-helper]");
        const competitionSelect = document.querySelector("[data-match-competition-select]");
        if (!seasonSelect || !competitionSelect) return;
        function renderSeasons() {{
          const seasons = seasonMap[competitionSelect.value] || [];
          const selected = seasonSelect.getAttribute("data-selected") || "";
          seasonSelect.innerHTML = seasons.map((season) => {{
            const isSelected = season === selected ? " selected" : "";
            return `<option value="${{season}}"${{isSelected}}>${{season}}</option>`;
          }}).join("");
          if (!seasonSelect.value && seasons.length) {{
            seasonSelect.value = seasons[0];
          }}
          if (!seasons.length) {{
            seasonSelect.innerHTML = '<option value="">暂无进行中赛季</option>';
          }}
          if (helper) {{
            helper.textContent = seasons.length
              ? '只显示当前正在进行中的赛季；赛季需要先在系列赛管理里配置起止时间。'
              : '当前地区赛事页所属系列赛还没有进行中的赛季，请先到系列赛管理里配置。';
          }}
          seasonSelect.setAttribute("data-selected", seasonSelect.value || selected);
        }}
        competitionSelect.addEventListener("change", function() {{
          seasonSelect.setAttribute("data-selected", "");
          renderSeasons();
        }});
        renderSeasons();
      }})();
    </script>
    """


def render_match_form_page(
    ctx: RequestContext,
    current: dict[str, object],
    action_url: str,
    page_title: str,
    heading: str,
    submit_label: str,
    next_path: str,
    match_code_hint: str,
    alert: str = "",
) -> str:
    competition_field_html = build_match_competition_field(
        str(current.get("competition_name", "")),
        ctx.current_user,
    )
    season_field_html = build_match_season_field(
        str(current.get("competition_name", "")),
        str(current.get("season", "")),
    )
    scapegoat_hidden_attr = (
        ' style="display:none;"'
        if str(current.get("winning_camp")) == "villagers"
        else ""
    )
    participant_rows = []
    for index, player in enumerate(current["players"]):
        participant_rows.append(
            f"""
            <tr>
              <td><input class="form-control form-control-sm" data-award-player-id name="player_id_{index}" value="{escape(str(player['player_id']))}"></td>
              <td><input class="form-control form-control-sm" name="team_id_{index}" value="{escape(str(player['team_id']))}"></td>
              <td><input class="form-control form-control-sm" data-award-seat name="seat_{index}" type="number" value="{escape(str(player['seat']))}"></td>
              <td><input class="form-control form-control-sm" data-award-role name="role_{index}" value="{escape(str(player['role']))}"></td>
              <td>
                <select class="form-select form-select-sm" data-award-camp name="camp_{index}">
                  {option_tags({k: v for k, v in CAMP_OPTIONS.items() if k != 'draw'}, str(player['camp']))}
                </select>
              </td>
              <td>
                <select class="form-select form-select-sm" name="result_{index}">
                  {option_tags(RESULT_OPTIONS, str(player['result']))}
                </select>
              </td>
              <td><input class="form-control form-control-sm" name="points_earned_{index}" type="number" step="0.1" value="{escape(str(player['points_earned']))}"></td>
              <td>
                <select class="form-select form-select-sm" name="stance_result_{index}">
                  {option_tags(STANCE_OPTIONS, str(player.get('stance_result', normalize_stance_result(player))))}
                </select>
              </td>
              <td><input class="form-control form-control-sm" name="notes_{index}" value="{escape(str(player['notes']))}"></td>
            </tr>
            """
        )

    body = f"""
    <section class="form-panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-4">
        <div>
          <h1 class="section-title mb-2">{escape(heading)}</h1>
          <p class="section-copy mb-0">这里可以录入或修改一场比赛的基础信息和全部上场选手数据。比赛编号会按“城市缩写-赛季缩写-六位日期-局序号”自动生成，赛季为必填项。</p>
        </div>
        <div class="d-flex gap-2">
          <a class="btn btn-outline-dark" href="{escape(next_path)}">返回上一页</a>
        </div>
      </div>
      <form method="post" action="{escape(action_url)}">
        <div class="row g-3 mb-4">
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">比赛编号</label>
            <input class="form-control" value="{escape(str(match_code_hint))}" readonly>
            <div class="small text-secondary mt-2">保存后会根据城市、赛季、日期自动重算编号。</div>
          </div>
          <div class="col-12 col-md-6 col-xl-4">
            <label class="form-label">系列赛名称</label>
            {competition_field_html}
          </div>
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">赛季</label>
            {season_field_html}
          </div>
          <div class="col-12 col-md-6 col-xl-2">
            <label class="form-label">阶段</label>
            <select class="form-select" name="stage">
              {option_tags(STAGE_OPTIONS, str(current['stage']))}
            </select>
          </div>
          <div class="col-6 col-md-3 col-xl-1">
            <label class="form-label">轮次</label>
            <input class="form-control" name="round" type="number" value="{escape(str(current['round']))}">
          </div>
          <div class="col-6 col-md-3 col-xl-1">
            <label class="form-label">局次</label>
            <input class="form-control" name="game_no" type="number" value="{escape(str(current['game_no']))}">
          </div>
          <div class="col-12 col-md-6 col-xl-2">
            <label class="form-label">日期</label>
            <input class="form-control" name="played_on" type="date" value="{escape(str(current['played_on']))}">
          </div>
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">桌号</label>
            <input class="form-control" name="table_label" value="{escape(str(current['table_label']))}">
          </div>
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">板型</label>
            <input class="form-control" name="format" value="{escape(str(current['format']))}">
          </div>
          <div class="col-12 col-md-3 col-xl-2">
            <label class="form-label">时长</label>
            <input class="form-control" name="duration_minutes" type="number" value="{escape(str(current['duration_minutes']))}">
          </div>
          <div class="col-12 col-md-3 col-xl-4">
            <label class="form-label">胜利阵营</label>
            <select class="form-select" data-winning-camp-select name="winning_camp">
              {option_tags(WINNING_CAMP_OPTIONS, str(current['winning_camp']))}
            </select>
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label">MVP</label>
            <select class="form-select" data-award-select="mvp" data-selected="{escape(str(current.get('mvp_player_id', '')))}" name="mvp_player_id">
              {build_match_award_select('mvp_player_id', str(current.get('mvp_player_id', '')), current['players'], '请选择 MVP')}
            </select>
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label">SVP</label>
            <select class="form-select" data-award-select="svp" data-selected="{escape(str(current.get('svp_player_id', '')))}" name="svp_player_id">
              {build_match_award_select('svp_player_id', str(current.get('svp_player_id', '')), current['players'], '请选择 SVP')}
            </select>
          </div>
          <div class="col-12 col-md-4" data-scapegoat-field{scapegoat_hidden_attr}>
            <label class="form-label">背锅</label>
            <select class="form-select" data-award-select="scapegoat" data-selected="{escape(str(current.get('scapegoat_player_id', '')))}" name="scapegoat_player_id">
              {build_match_award_select('scapegoat_player_id', str(current.get('scapegoat_player_id', '')), current['players'], '请选择背锅选手', str(current.get('winning_camp', '')), True)}
            </select>
            <div class="small text-secondary mt-2">仅在狼人胜利时设置背锅选手。</div>
          </div>
          <div class="col-12">
            <label class="form-label">比赛备注</label>
            <textarea class="form-control" name="notes" rows="3">{escape(str(current['notes']))}</textarea>
          </div>
        </div>

        <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-3">
          <div>
            <h2 class="h5 mb-1">上场选手数据</h2>
            <div class="small text-secondary">这里按当前顺序编辑所有参赛选手信息。</div>
          </div>
        </div>

        <div class="table-responsive mb-4">
          <table class="table align-middle">
            <thead>
              <tr>
                <th>队员编号</th>
                <th>战队编号</th>
                <th>座位</th>
                <th>角色</th>
                <th>阵营</th>
                <th>结果</th>
                <th>得分</th>
                <th>站边结果</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              {''.join(participant_rows)}
            </tbody>
          </table>
        </div>

        <div class="d-flex flex-wrap gap-2">
          <button type="submit" class="btn btn-dark">{escape(submit_label)}</button>
          <a class="btn btn-outline-dark" href="{escape(next_path)}">取消</a>
        </div>
      </form>
    </section>
    <script>
      (function() {{
        const form = document.currentScript.previousElementSibling.querySelector("form");
        if (!form) return;
        const winningCampSelect = form.querySelector("[data-winning-camp-select]");
        const mvpSelect = form.querySelector('[data-award-select="mvp"]');
        const svpSelect = form.querySelector('[data-award-select="svp"]');
        const scapegoatSelect = form.querySelector('[data-award-select="scapegoat"]');
        const scapegoatField = form.querySelector("[data-scapegoat-field]");
        const playerInputs = Array.from(form.querySelectorAll("[data-award-player-id]"));
        const seatInputs = Array.from(form.querySelectorAll("[data-award-seat]"));
        const roleInputs = Array.from(form.querySelectorAll("[data-award-role]"));
        const campInputs = Array.from(form.querySelectorAll("[data-award-camp]"));
        function collectParticipants() {{
          return playerInputs.map((input, index) => {{
            const playerId = (input.value || "").trim();
            const seat = (seatInputs[index] && seatInputs[index].value) || "";
            const role = (roleInputs[index] && roleInputs[index].value) || "";
            const camp = (campInputs[index] && campInputs[index].value) || "";
            return {{ playerId, seat, role, camp }};
          }}).filter((item) => item.playerId);
        }}
        function buildOptions(select, participants, placeholder, losingOnly) {{
          if (!select) return;
          const selectedValue = select.value || select.getAttribute("data-selected") || "";
          const winningCamp = winningCampSelect ? winningCampSelect.value : "";
          const filtered = losingOnly
            ? participants.filter((item) => item.camp && item.camp !== winningCamp)
            : participants;
          const options = [`<option value="">${{placeholder}}</option>`].concat(
            filtered.map((item) => {{
              const pieces = [`${{item.seat}}号`, item.playerId];
              if (item.role) pieces.push(item.role);
              const selected = item.playerId === selectedValue ? " selected" : "";
              return `<option value="${{item.playerId}}"${{selected}}>${{pieces.join(" · ")}}</option>`;
            }})
          );
          select.innerHTML = options.join("");
          if (selectedValue && !filtered.some((item) => item.playerId === selectedValue)) {{
            select.value = "";
          }}
          select.setAttribute("data-selected", select.value || "");
        }}
        function renderAwards() {{
          const participants = collectParticipants();
          buildOptions(mvpSelect, participants, "请选择 MVP", false);
          buildOptions(svpSelect, participants, "请选择 SVP", false);
          if (winningCampSelect && winningCampSelect.value === "villagers") {{
            if (scapegoatField) scapegoatField.style.display = "none";
            if (scapegoatSelect) {{
              scapegoatSelect.value = "";
              scapegoatSelect.setAttribute("data-selected", "");
            }}
          }} else {{
            if (scapegoatField) scapegoatField.style.display = "";
            buildOptions(scapegoatSelect, participants, "请选择背锅选手", true);
          }}
        }}
        [winningCampSelect, ...playerInputs, ...seatInputs, ...roleInputs, ...campInputs]
          .filter(Boolean)
          .forEach((element) => element.addEventListener("input", renderAwards));
        [winningCampSelect, ...campInputs]
          .filter(Boolean)
          .forEach((element) => element.addEventListener("change", renderAwards));
        renderAwards();
      }})();
    </script>
    """
    return layout(page_title, body, ctx, alert=alert)


def get_batch_create_form_values(
    ctx: RequestContext,
    form_values: dict[str, str] | None = None,
) -> dict[str, str]:
    return form_values or {
        "competition_name": form_value(ctx.query, "competition").strip(),
        "season": form_value(ctx.query, "season").strip(),
        "stage": "regular_season",
        "start_date": legacy.china_today_label(),
        "end_date": legacy.china_today_label(),
        "matches_per_day": "3",
        "round_start": "1",
    }


def get_match_edit_page(
    ctx: RequestContext,
    match_id: str,
    alert: str = "",
    field_values: dict[str, object] | None = None,
) -> str:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return layout("未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>', ctx)
    if ctx.current_user and not can_manage_matches(
        ctx.current_user,
        data,
        get_match_competition_name(match),
    ):
        return layout("没有权限", '<div class="alert alert-danger">你不能编辑这个地区系列赛下的比赛。</div>', ctx)

    current = field_values or match
    next_path = form_value(ctx.query, "next", "/dashboard")
    match_code_hint = current.get("match_id", match_id)
    return render_match_form_page(
        ctx,
        current,
        f"/matches/{match_id}/edit?next={quote(next_path)}",
        "编辑比赛",
        "编辑比赛",
        "保存修改",
        next_path,
        match_code_hint,
        alert=alert,
    )


def get_match_create_page(
    ctx: RequestContext,
    alert: str = "",
    field_values: dict[str, object] | None = None,
    batch_form_values: dict[str, str] | None = None,
) -> str:
    current = field_values or build_empty_match(
        form_value(ctx.query, "competition").strip(),
        form_value(ctx.query, "season").strip(),
    )
    if current.get("competition_name"):
        data = load_validated_data()
        if ctx.current_user and not can_manage_matches(
            ctx.current_user,
            data,
            str(current.get("competition_name") or ""),
        ):
            return layout("没有权限", '<div class="alert alert-danger">你不能在这个地区系列赛下创建比赛。</div>', ctx)
    next_path = form_value(ctx.query, "next").strip() or build_scoped_path(
        "/competitions",
        current.get("competition_name") or None,
        current.get("season") or None,
    ) or "/competitions"
    manual_form_html = render_match_form_page(
        ctx,
        current,
        f"/matches/new?next={quote(next_path)}",
        "录入比赛",
        "录入比赛结果",
        "创建比赛",
        next_path,
        "保存后自动生成",
        alert=alert,
    )
    batch_panel_html = build_batch_create_form(ctx, get_batch_create_form_values(ctx, batch_form_values))
    excel_panel_html = build_excel_import_panel()
    body_start = manual_form_html.find('<section class="form-panel')
    if body_start == -1:
        return manual_form_html
    combined_body = manual_form_html.replace(
        '<section class="form-panel',
        f"{batch_panel_html}{excel_panel_html}<section class=\"form-panel",
        1,
    )
    return combined_body


def handle_match_edit(ctx: RequestContext, start_response, match_id: str):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_match_edit_page(ctx, match_id))

    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return start_response_html(
            start_response,
            "404 Not Found",
            layout("未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>', ctx),
        )
    permission_guard = require_competition_manager(
        ctx,
        start_response,
        data,
        get_match_competition_name(match),
        "你不能编辑这个地区系列赛下的比赛。",
    )
    if permission_guard is not None:
        return permission_guard

    updated_match = parse_match_form(ctx.form, match)
    permission_guard = require_competition_manager(
        ctx,
        start_response,
        data,
        updated_match["competition_name"],
        "你不能把比赛保存到未授权的地区系列赛下。",
    )
    if permission_guard is not None:
        return permission_guard
    competition_error = validate_match_competition_selection(
        data,
        updated_match["competition_name"],
    )
    if competition_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_edit_page(ctx, match_id, alert=competition_error, field_values=updated_match),
        )
    season_error = validate_match_season_selection(
        data,
        updated_match["competition_name"],
        updated_match["season"],
        existing_season_name=(match.get("season") or "").strip(),
    )
    if season_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_edit_page(ctx, match_id, alert=season_error, field_values=updated_match),
        )
    award_error = validate_match_awards(updated_match)
    if award_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_edit_page(ctx, match_id, alert=award_error, field_values=updated_match),
        )
    matches = []
    for item in data["matches"]:
        if item["match_id"] == match_id:
            matches.append(updated_match)
        else:
            matches.append(item)

    normalized_matches, resolved_match_id = legacy.canonicalize_match_ids(
        matches,
        target_original_id=match_id,
    )
    users = load_users()
    data["matches"] = normalized_matches
    created_player_ids = ensure_placeholder_players_for_matches(data, normalized_matches)
    users = ensure_placeholder_users_for_player_ids(data, users, created_player_ids)
    errors = save_repository_state(data, users)
    if errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_edit_page(ctx, match_id, alert="保存失败：" + "；".join(errors[:3]), field_values=updated_match),
        )

    next_path = form_value(ctx.query, "next").strip() or f"/matches/{resolved_match_id}"
    next_path = replace_match_path_id(next_path, match_id, resolved_match_id or match_id)
    if created_player_ids and next_path.startswith("/matches/"):
        next_path = append_alert_query(next_path, "placeholder-created")
    return redirect(start_response, next_path)


def handle_match_create(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_match_create_page(ctx))

    data = load_validated_data()
    action = form_value(ctx.form, "action").strip()
    if action == "batch_create_matches":
        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season").strip()
        stage = form_value(ctx.form, "stage").strip()
        start_date = form_value(ctx.form, "start_date").strip()
        end_date = form_value(ctx.form, "end_date").strip()
        round_start_raw = form_value(ctx.form, "round_start", "1").strip()
        matches_per_day_raw = form_value(ctx.form, "matches_per_day", "1").strip()
        batch_form_values = {
            "competition_name": competition_name,
            "season": season_name,
            "stage": stage,
            "start_date": start_date,
            "end_date": end_date,
            "round_start": round_start_raw or "1",
            "matches_per_day": matches_per_day_raw or "1",
        }
        permission_guard = require_competition_manager(
            ctx,
            start_response,
            data,
            competition_name,
            "你不能在这个地区系列赛下批量创建比赛。",
        )
        if permission_guard is not None:
            return permission_guard
        competition_error = validate_match_competition_selection(data, competition_name)
        if competition_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=competition_error, batch_form_values=batch_form_values),
            )
        season_error = validate_match_season_selection(data, competition_name, season_name)
        if season_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=season_error, batch_form_values=batch_form_values),
            )
        try:
            new_matches = batch_create_matches(
                competition_name,
                season_name,
                stage,
                start_date,
                end_date,
                int(round_start_raw or "0"),
                int(matches_per_day_raw or "0"),
            )
        except ValueError as exc:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=str(exc), batch_form_values=batch_form_values),
            )
        normalized_matches, _ = canonicalize_match_ids([*data["matches"], *new_matches])
        users = load_users()
        data["matches"] = normalized_matches
        users = ensure_placeholder_users_for_player_ids(data, users, [])
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="批量创建失败：" + "；".join(errors[:3]), batch_form_values=batch_form_values),
            )
        next_path = form_value(ctx.query, "next").strip() or build_scoped_path(
            "/competitions",
            competition_name,
            season_name,
        )
        return redirect(
            start_response,
            append_alert_query(next_path or "/competitions", f"已批量创建 {len(new_matches)} 场待补录比赛。"),
        )
    if action == "import_match_excel":
        upload = file_value(ctx.files, "match_excel_file")
        upload_error = validate_excel_upload(upload)
        if upload_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=upload_error),
            )
        next_matches, import_message = import_matches_from_excel(ctx, data, upload)
        if next_matches is None:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=import_message),
            )
        users = load_users()
        normalized_matches, _ = canonicalize_match_ids(next_matches)
        data["matches"] = normalized_matches
        created_player_ids = ensure_placeholder_players_for_matches(data, normalized_matches)
        users = ensure_placeholder_users_for_player_ids(data, users, created_player_ids)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="Excel 导入保存失败：" + "；".join(errors[:3])),
            )
        next_path = form_value(ctx.query, "next").strip() or "/competitions"
        alert_message = import_message
        if created_player_ids:
            alert_message += " 系统还为模板里不存在的参赛 ID 自动创建了占位档案。"
        return redirect(start_response, append_alert_query(next_path, alert_message))

    new_match = parse_match_form(ctx.form, build_empty_match())
    permission_guard = require_competition_manager(
        ctx,
        start_response,
        data,
        new_match["competition_name"],
        "你不能在这个地区系列赛下创建比赛。",
    )
    if permission_guard is not None:
        return permission_guard
    competition_error = validate_match_competition_selection(
        data,
        new_match["competition_name"],
    )
    if competition_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_create_page(
                ctx,
                alert=competition_error,
                field_values=new_match,
            ),
        )
    season_error = validate_match_season_selection(
        data,
        new_match["competition_name"],
        new_match["season"],
    )
    if season_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_create_page(
                ctx,
                alert=season_error,
                field_values=new_match,
            ),
        )
    award_error = validate_match_awards(new_match)
    if award_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_create_page(
                ctx,
                alert=award_error,
                field_values=new_match,
            ),
        )
    normalized_matches, resolved_match_id = canonicalize_match_ids(
        [*data["matches"], new_match],
        target_original_id=new_match["match_id"],
    )
    users = load_users()
    data["matches"] = normalized_matches
    created_player_ids = ensure_placeholder_players_for_matches(data, normalized_matches)
    users = ensure_placeholder_users_for_player_ids(data, users, created_player_ids)
    errors = save_repository_state(data, users)
    if errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_create_page(
                ctx,
                alert="保存失败：" + "；".join(errors[:3]),
                field_values=new_match,
            ),
        )

    next_path = form_value(ctx.query, "next").strip()
    if next_path:
        if created_player_ids and next_path.startswith("/matches/"):
            next_path = append_alert_query(next_path, "placeholder-created")
        return redirect(start_response, next_path)
    redirect_path = f"/matches/{resolved_match_id}"
    if created_player_ids:
        redirect_path = append_alert_query(redirect_path, "placeholder-created")
    return redirect(start_response, redirect_path)
