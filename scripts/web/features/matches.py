from __future__ import annotations

import csv
from datetime import datetime, timedelta
from html import escape
from io import BytesIO
from io import StringIO
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import secrets
from urllib.parse import quote, urlencode
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

import web_app as legacy
from generate_match_result_excel_template import build_dynamic_match_template_bytes
from sqlite_store import (
    clear_season_dimension_stats,
    clear_season_dimension_stats_for_day,
    save_season_dimension_stats,
)

CAMP_OPTIONS = legacy.CAMP_OPTIONS
RequestContext = legacy.RequestContext
UploadedFile = legacy.UploadedFile
RESULT_OPTIONS = legacy.RESULT_OPTIONS
STAGE_OPTIONS = legacy.STAGE_OPTIONS
STANCE_OPTIONS = legacy.STANCE_OPTIONS
WINNING_CAMP_OPTIONS = legacy.WINNING_CAMP_OPTIONS
append_alert_query = legacy.append_alert_query
audit_action = legacy.audit_action
build_empty_match = legacy.build_empty_match
build_empty_score_breakdown = legacy.build_empty_score_breakdown
build_match_award_select = legacy.build_match_award_select
build_scoped_path = legacy.build_scoped_path
calculate_score_breakdown_total = legacy.calculate_score_breakdown_total
can_manage_matches = legacy.can_manage_matches
canonicalize_match_ids = legacy.canonicalize_match_ids
create_import_batch = legacy.create_import_batch
default_scoring_rule = legacy.default_scoring_rule
ensure_placeholder_players_for_matches = legacy.ensure_placeholder_players_for_matches
ensure_placeholder_users_for_player_ids = legacy.ensure_placeholder_users_for_player_ids
file_value = legacy.file_value
form_value = legacy.form_value
get_match_by_id = legacy.get_match_by_id
get_match_competition_name = legacy.get_match_competition_name
get_match_score_model_label = legacy.get_match_score_model_label
layout = legacy.layout
list_seasons = legacy.list_seasons
load_import_batches = legacy.load_import_batches
load_series_catalog = legacy.load_series_catalog
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
invalidate_validated_data_cache = legacy.invalidate_validated_data_cache
is_admin_user = legacy.is_admin_user
MATCH_SCORE_COMPONENT_FIELDS = legacy.MATCH_SCORE_COMPONENT_FIELDS
MATCH_SCORE_MODEL_OPTIONS = legacy.MATCH_SCORE_MODEL_OPTIONS
PARTICIPATION_MODE_INDIVIDUAL = legacy.PARTICIPATION_MODE_INDIVIDUAL
normalize_stance_result = legacy.normalize_stance_result
normalize_match_score_model = legacy.normalize_match_score_model
normalize_scoring_rule = legacy.normalize_scoring_rule
normalize_score_breakdown = legacy.normalize_score_breakdown
option_tags = legacy.option_tags
parse_match_form = legacy.parse_match_form
parse_float_value = legacy.parse_float_value
build_placeholder_team = legacy.build_placeholder_team
build_team_serial = legacy.build_team_serial
redirect = legacy.redirect
replace_match_path_id = legacy.replace_match_path_id
require_competition_manager = legacy.require_competition_manager
resolve_match_entities = legacy.resolve_match_entities
rollback_import_batch = legacy.rollback_import_batch
save_repository_state = legacy.save_repository_state
resolve_scoring_rule_for_scope = legacy.resolve_scoring_rule_for_scope
resolve_participation_mode_for_scope = legacy.resolve_participation_mode_for_scope
safe_asset_path = legacy.safe_asset_path
scoring_rule_component_fields = legacy.scoring_rule_component_fields
ensure_team_asset_dirs = legacy.ensure_team_asset_dirs
TEAM_UPLOAD_DIR = legacy.TEAM_UPLOAD_DIR
ROOT_DIR = legacy.ROOT
ALLOWED_IMAGE_EXTENSIONS = legacy.ALLOWED_IMAGE_EXTENSIONS
MAX_UPLOAD_BYTES = legacy.MAX_UPLOAD_BYTES
MAX_EXCEL_UPLOAD_BYTES = int(os.getenv("MAX_EXCEL_UPLOAD_BYTES", str(10 * 1024 * 1024)))
MAX_EXCEL_SHEET_ROWS = int(os.getenv("MAX_EXCEL_SHEET_ROWS", "2000"))
MAX_ZIP_UPLOAD_BYTES = int(os.getenv("MAX_ZIP_UPLOAD_BYTES", str(50 * 1024 * 1024)))
MAX_ZIP_IMAGE_COUNT = int(os.getenv("MAX_ZIP_IMAGE_COUNT", "300"))
PLAYER_PHOTO_PENDING_DIR = legacy.PLAYER_UPLOAD_DIR.parent / "import-pending"
start_response_html = legacy.start_response_html
update_import_batch = legacy.update_import_batch
uses_structured_score_model = legacy.uses_structured_score_model
validate_match_awards = legacy.validate_match_awards
validate_match_competition_selection = legacy.validate_match_competition_selection
validate_match_season_selection = legacy.validate_match_season_selection
STAGE_LABELS = STAGE_OPTIONS

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DOWNLOAD_PATH = "/assets/templates/match-result-upload-template-generic.xlsx"
EXCEL_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
XDR_NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
WPS_CELLIMAGE_NS = {
    "etc": "http://www.wps.cn/officeDocument/2017/etCustomData",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MATCH_SEQUENCE_PATTERN = re.compile(r"-(\d{2})$")
WPS_DISPIMG_PATTERN = re.compile(r'DISPIMG\("(?P<image_id>ID_[A-F0-9]+)"', re.IGNORECASE)
TRUTHY_EXCEL_VALUES = {"1", "true", "yes", "y", "是", "对", "抽局", "不计", "不计战队总分"}
EXCEL_HEADER_ALIASES = {
    "比赛编号": "match_id",
    "局号": "match_id",
    "赛事名称": "competition_name",
    "赛季": "season_name",
    "日期": "played_on",
    "局次": "game_no",
    "赛段": "stage",
    "分组": "group_label",
    "房间": "room_label",
    "板型": "format",
    "时长": "duration_minutes",
    "胜利阵营": "winning_camp",
    "MVP": "mvp_player_name",
    "SVP": "svp_player_name",
    "背锅": "scapegoat_player_name",
    "座位号": "seat",
    "战队": "team_name",
    "战队名": "team_name",
    "战队名称": "team_name",
    "战队logo": "logo",
    "战队Logo": "logo",
    "logo": "logo",
    "Logo": "logo",
    "选手姓名": "player_name",
    "选手头像": "photo",
    "选手照片": "photo",
    "photo": "photo",
    "Photo": "photo",
    "选手": "player_name",
    "身份": "role",
    "阵营": "camp",
    "结果": "result",
    "胜负分": "result_points",
    "投票分": "vote_points",
    "行为分": "behavior_points",
    "特殊分": "special_points",
    "违规分": "adjustment_points",
    "单局积分": "points_earned",
    "当日总分": "daily_total",
    "站边": "stance_result",
    "积分模型": "score_model",
    "不计战队总分": "exclude_from_team_scores",
    "抽局": "exclude_from_team_scores",
    "备注": "notes",
}
PLAYER_DIMENSION_SHEET_NAMES = ["单日选手个人维度数据"]
TEAM_DIMENSION_SHEET_NAMES = ["单日选手战队维度数据 ", "单日选手战队维度数据"]
TEAM_LOGO_SHEET_NAMES = ["赛季战队图标数据", "records"]
PLAYER_PHOTO_SHEET_NAMES = ["赛季队员头像数据", "records"]
PLAYER_DIMENSION_FIELD_MAP = {
    "当日积分": "daily_points",
    "局数": "games_played",
    "胜场数": "wins",
    "狼人局数": "werewolf_games",
    "狼人胜局数": "werewolf_wins",
    "好人局数": "villager_games",
    "好人胜局数": "villager_wins",
    "投票次数": "vote_count",
    "投狼次数": "vote_wolf_count",
    "悍跳次数": "jump_count",
    "悍跳成功次数": "jump_success_count",
    "MVP次数": "mvp_count",
    "SVP次数": "svp_count",
    "背锅次数": "scapegoat_count",
}
TEAM_DIMENSION_FIELD_MAP = {
    "当日积分": "daily_points",
    "局数": "games_played",
    "胜场数": "wins",
    "狼人局数": "werewolf_games",
    "狼人胜局数": "werewolf_wins",
    "好人局数": "villager_games",
    "好人胜局数": "villager_wins",
    "投票次数": "vote_count",
    "投狼次数": "vote_wolf_count",
    "悍跳次数": "jump_count",
    "悍跳成功次数": "jump_success_count",
    "MVP次数": "mvp_count",
    "SVP次数": "svp_count",
    "背锅次数": "scapegoat_count",
    "首日投对": "first_vote_correct",
    "第一局胜": "game_1_win",
    "第二局胜": "game_2_win",
    "第三局胜": "game_3_win",
    "第一局阵营": "game_1_camp",
    "第二局阵营": "game_2_camp",
    "第三局阵营": "game_3_camp",
    "第一局狼胜": "game_1_werewolf_win",
    "第二局狼胜": "game_2_werewolf_win",
    "第三局狼胜": "game_3_werewolf_win",
    "第一局好胜": "game_1_villager_win",
    "第二局好人胜": "game_2_villager_win",
    "第三局好人胜": "game_3_villager_win",
    "首日投错": "first_vote_incorrect",
    "好人得分": "villager_points",
    "狼人得分": "werewolf_points",
    "自刀次数": "self_elimination_count",
    "开毒次数": "poison_used_count",
    "毒狼次数": "poisoned_werewolf_count",
}


def parse_truthy_excel_value(value: object) -> bool:
    return str(value or "").strip().lower() in TRUTHY_EXCEL_VALUES


def parse_date_input(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        return None


def format_room_label(game_no: int) -> str:
    return f"{game_no}号房"


def danger_confirmation_error(actual: str, expected: str, action_label: str) -> str:
    if str(actual or "").strip() == expected:
        return ""
    return f"{action_label}前，请在确认框输入：{expected}"


def resolve_match_template_download_name(series_slug: str) -> str:
    candidate_names = [
        f"match-result-upload-template-{series_slug}.xlsx",
        f"match-result-upload-template-{series_slug}-v2.xlsx",
    ]
    for file_name in candidate_names:
        template_file = ROOT / "assets" / "templates" / file_name
        if not template_file.is_file():
            continue
        try:
            with ZipFile(template_file) as archive:
                archive.getinfo("xl/worksheets/sheet1.xml")
        except Exception:
            continue
        return file_name
    return ""


def excel_column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    index = 0
    for letter in letters:
        index = index * 26 + (ord(letter) - 64)
    return index


def build_placeholder_match(
    competition_name: str,
    season_name: str,
    stage: str,
    round_no: int,
    game_no: int,
    played_on: str,
    group_label: str,
    room_label: str,
) -> dict[str, object]:
    match = build_empty_match(competition_name, season_name)
    match["match_id"] = "pending-new-match"
    match["stage"] = stage
    match["round"] = round_no
    match["game_no"] = game_no
    match["played_on"] = played_on
    match["group_label"] = group_label
    match["table_label"] = room_label
    match["format"] = "待补录"
    match["duration_minutes"] = 0
    match["winning_camp"] = "draw"
    match["mvp_player_id"] = ""
    match["svp_player_id"] = ""
    match["scapegoat_player_id"] = ""
    match["mvp_player_name"] = ""
    match["svp_player_name"] = ""
    match["scapegoat_player_name"] = ""
    match["notes"] = "批量创建的待补录比赛，请稍后完善比赛详情。"
    match["players"] = []
    return match


def ensure_match_form_players(current: dict[str, object]) -> dict[str, object]:
    participants = current.get("players")
    if isinstance(participants, list) and participants:
        return current
    editable_match = build_empty_match(
        str(current.get("competition_name") or ""),
        str(current.get("season") or ""),
    )
    return {
        **editable_match,
        **current,
        "players": editable_match["players"],
    }


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
        "room_label": "1号房",
    }
    competition_field_html = build_match_competition_field(
        current["competition_name"],
        ctx.current_user,
        prioritize_active=True,
    )
    season_field_html = build_match_season_field(
        current["competition_name"],
        current["season"],
        include_non_ongoing=True,
    )
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-4">
        <div>
          <h2 class="section-title mb-2">批量创建待补录比赛</h2>
          <p class="section-copy mb-0">先在指定赛季下批量生成赛程壳子，后续再逐场补录版型、时长、阵容、分组和结果。适合一次创建整月赛程。</p>
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
            <label class="form-label">房间</label>
            <input class="form-control" name="room_label" value="{escape(current['room_label'])}">
            <div class="small text-secondary mt-2">这里只先批量生成赛程壳子；如果常规赛需要分组，后续可以在 Excel 批量补录时选填。</div>
          </div>
          <div class="col-12 col-md-6 col-xl-2">
            <label class="form-label">开始日期</label>
            <input class="form-control" name="start_date" type="date" value="{escape(current['start_date'])}">
          </div>
          <div class="col-12 col-md-6 col-xl-2">
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


def build_excel_import_panel(
    ctx: RequestContext,
    values: dict[str, str] | None = None,
) -> str:
    current = values or {
        "group_label": "",
        "competition_name": form_value(ctx.query, "competition").strip(),
        "season": form_value(ctx.query, "season").strip(),
    }
    current.setdefault("competition_name", form_value(ctx.query, "competition").strip())
    current.setdefault("season", form_value(ctx.query, "season").strip())
    try:
        data = load_validated_data()
        series_catalog = load_series_catalog(data)
    except Exception:
        series_catalog = []

    generic_template_name = (
        resolve_match_template_download_name("generic")
        or "match-result-upload-template-generic.xlsx"
    )
    template_links = [
        f'<a class="btn btn-outline-dark" href="/assets/templates/{escape(generic_template_name)}">通用模板</a>'
    ]
    dynamic_competition_field = build_match_competition_field(
        current["competition_name"],
        ctx.current_user,
        prioritize_active=True,
    )
    dynamic_season_field = build_match_season_field(
        current["competition_name"],
        current["season"],
        include_non_ongoing=True,
    )
    seen_series_slugs: set[str] = set()
    for entry in series_catalog:
        series_slug = str(entry.get("series_slug") or "").strip()
        series_name = str(entry.get("series_name") or "").strip()
        if not series_slug or not series_name or series_slug in seen_series_slugs:
            continue
        template_name = resolve_match_template_download_name(series_slug)
        if not template_name:
            continue
        seen_series_slugs.add(series_slug)
        template_links.append(
            f'<a class="btn btn-outline-dark" href="/assets/templates/{escape(template_name)}">{escape(series_name)} 模板</a>'
        )
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-4">
        <div>
          <h2 class="section-title mb-2">Excel 批量补录比赛详情</h2>
          <p class="section-copy mb-0">支持一次上传多场比赛详情。模板为单工作表，单行就是一个选手在一局里的记录；系统按唯一比赛编号定位已预创建比赛。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">{''.join(template_links)}</div>
      </div>
      <form method="get" action="/matches/new" class="team-link-card shadow-sm p-3 mb-4">
        <input type="hidden" name="action" value="download_scoring_template">
        <div class="row g-3 align-items-end">
          <div class="col-12 col-lg-5">
            <label class="form-label">模板所属赛事</label>
            {dynamic_competition_field}
          </div>
          <div class="col-12 col-lg-4">
            <label class="form-label">模板所属赛季</label>
            {dynamic_season_field}
          </div>
          <div class="col-12 col-lg-3">
            <button type="submit" class="btn btn-dark w-100">生成当前规则模板</button>
          </div>
        </div>
        <div class="small text-secondary mt-2">模板会锁定当前赛季计分规则版本，并按启用维度生成列和单局积分公式。</div>
      </form>
      <form method="post" action="/matches/new" enctype="multipart/form-data">
        <input type="hidden" name="action" value="import_match_excel">
        <div class="row g-3">
          <div class="col-12 col-lg-4">
            <label class="form-label">本次上传分组（选填）</label>
            <input class="form-control" name="group_label" value="{escape(current['group_label'])}" placeholder="如 A组 / B组">
            <div class="small text-secondary mt-2">只有常规赛这类需要分组时再填；留空也可以正常上传。</div>
          </div>
          <div class="col-12 col-lg-8">
            <label class="form-label">选择 Excel 文件</label>
            <input class="form-control" type="file" name="match_excel_file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet">
          </div>
        </div>
        <div class="small text-secondary mt-3">模板只用于补录已经批量创建好的比赛。Excel 只需填写唯一比赛编号，系统会自动读取对应赛事、赛季、日期和赛段。这里的分组如果填写，会统一写入本次上传的每场比赛；如果留空，系统才会读取 Excel 里的 `分组` 列。MVP/SVP/背锅列填“是”或留空即可，每局每种最多一位。</div>
        <div class="d-flex flex-wrap gap-2 mt-4">
          <button type="submit" class="btn btn-dark">上传并导入</button>
        </div>
      </form>
    </section>
    """


def build_dimension_import_panel(
    ctx: RequestContext,
    values: dict[str, str] | None = None,
) -> str:
    current = values or {
        "competition_name": form_value(ctx.query, "competition").strip(),
        "season": form_value(ctx.query, "season").strip(),
    }
    competition_field_html = build_match_competition_field(
        current["competition_name"],
        ctx.current_user,
        prioritize_active=True,
    )
    season_field_html = build_match_season_field(
        current["competition_name"],
        current["season"],
        include_non_ongoing=True,
    )
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-4">
        <div>
          <h2 class="section-title mb-2">Excel 批量导入赛季维度数据</h2>
          <p class="section-copy mb-0">用于导入比赛日报里的选手维度和战队维度补充数据。系统会把数据绑定到当前赛事赛季下已有的选手、战队档案中。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <a class="btn btn-outline-dark" href="/assets/templates/dimension-stats-upload-template-jcds.xlsx">下载京城大师赛维度模板</a>
          <a class="btn btn-outline-dark" href="/dimension-stats">管理已导入维度数据</a>
        </div>
      </div>
      <form method="post" action="/matches/new" enctype="multipart/form-data">
        <input type="hidden" name="action" value="import_dimension_excel">
        <div class="row g-3">
          <div class="col-12 col-xl-4">
            <label class="form-label">地区赛事页</label>
            {competition_field_html}
          </div>
          <div class="col-12 col-xl-3">
            <label class="form-label">赛季</label>
            {season_field_html}
          </div>
          <div class="col-12 col-xl-5">
            <label class="form-label">选择 Excel 文件</label>
            <input class="form-control" type="file" name="dimension_excel_file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet">
          </div>
        </div>
        <div class="small text-secondary mt-3">目前识别工作表 `单日选手个人维度数据` 和 `单日选手战队维度数据`。定级赛的个人维度允许所属战队留空，战队维度表也可以不提供；组队后的记录填写战队并提供战队维度表后，会按当时归属正常统计。系统不会用后来加入的战队反向改写定级赛记录。重复上传只按同一赛事、赛季、日期和主键逐条新增或更新。</div>
        <div class="d-flex flex-wrap gap-2 mt-4">
          <button type="submit" class="btn btn-dark">上传并导入维度数据</button>
        </div>
      </form>
      <div class="border-top mt-4 pt-4">
        <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
          <div>
            <h3 class="h5 mb-2">清空当前赛季维度数据</h3>
            <p class="section-copy mb-0">只会删除当前赛事 + 赛季下已导入的选手维度和战队维度数据，不会删除比赛、战队、队员主档，也不会影响其他赛季。</p>
          </div>
        </div>
        <form method="post" action="/matches/new" onsubmit="return confirm('确认清空当前赛事赛季下的全部维度数据吗？清空后需要重新上传。');">
          <input type="hidden" name="action" value="clear_dimension_stats">
          <div class="row g-3">
            <div class="col-12 col-xl-4">
              <label class="form-label">地区赛事页</label>
              {competition_field_html}
            </div>
            <div class="col-12 col-xl-3">
              <label class="form-label">赛季</label>
              {season_field_html}
            </div>
            <div class="col-12 col-xl-5">
              <label class="form-label">危险操作确认</label>
              <input class="form-control" name="danger_confirmation" placeholder="输入 清空维度 确认">
              <div class="small text-secondary mt-2">会删除当前赛事赛季下全部已导入维度数据，不能撤销。</div>
            </div>
          </div>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <button type="submit" class="btn btn-outline-danger">清空这个赛季的维度数据</button>
          </div>
        </form>
      </div>
    </section>
    """


def build_dimension_stats_day_rows(data: dict[str, object]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    player_names = {
        str(player.get("player_id") or ""): str(player.get("display_name") or player.get("player_id") or "")
        for player in data.get("players", [])
        if isinstance(player, dict)
    }
    team_names = {
        str(team.get("team_id") or ""): str(team.get("name") or team.get("team_id") or "")
        for team in data.get("teams", [])
        if isinstance(team, dict)
    }
    for row in data.get("season_player_dimension_stats", []):
        if not isinstance(row, dict):
            continue
        key = (
            str(row.get("competition_name") or "").strip(),
            str(row.get("season_name") or "").strip(),
            str(row.get("played_on") or "").strip(),
        )
        if not all(key):
            continue
        item = grouped.setdefault(
            key,
            {
                "competition_name": key[0],
                "season_name": key[1],
                "played_on": key[2],
                "player_count": 0,
                "team_count": 0,
                "players": set(),
                "teams": set(),
            },
        )
        item["player_count"] = int(item["player_count"] or 0) + 1
        player_name = player_names.get(str(row.get("player_id") or "").strip())
        if player_name:
            item["players"].add(player_name)
        team_name = team_names.get(str(row.get("team_id") or "").strip())
        if team_name:
            item["teams"].add(team_name)
    for row in data.get("season_team_dimension_stats", []):
        if not isinstance(row, dict):
            continue
        key = (
            str(row.get("competition_name") or "").strip(),
            str(row.get("season_name") or "").strip(),
            str(row.get("played_on") or "").strip(),
        )
        if not all(key):
            continue
        item = grouped.setdefault(
            key,
            {
                "competition_name": key[0],
                "season_name": key[1],
                "played_on": key[2],
                "player_count": 0,
                "team_count": 0,
                "players": set(),
                "teams": set(),
            },
        )
        item["team_count"] = int(item["team_count"] or 0) + 1
        team_name = team_names.get(str(row.get("team_id") or "").strip())
        if team_name:
            item["teams"].add(team_name)
    rows = []
    for item in grouped.values():
        rows.append(
            {
                **item,
                "players": sorted(item["players"]),
                "teams": sorted(item["teams"]),
            }
        )
    rows.sort(
        key=lambda item: (
            str(item["played_on"]),
            str(item["competition_name"]),
            str(item["season_name"]),
        ),
        reverse=True,
    )
    return rows


def build_dimension_stats_chart_panel(rows: list[dict[str, object]]) -> str:
    total_player_count = sum(int(row.get("player_count") or 0) for row in rows)
    total_team_count = sum(int(row.get("team_count") or 0) for row in rows)
    total_day_count = len(rows)
    unique_player_count = len(
        {
            player_name
            for row in rows
            for player_name in row.get("players", [])
            if str(player_name or "").strip()
        }
    )
    unique_team_count = len(
        {
            team_name
            for row in rows
            for team_name in row.get("teams", [])
            if str(team_name or "").strip()
        }
    )
    max_daily_total = max(
        [int(row.get("player_count") or 0) + int(row.get("team_count") or 0) for row in rows]
        or [0]
    )
    chart_svg = ""
    radar_items = [
        {"label": "比赛日", "value": total_day_count},
        {"label": "选手维度", "value": total_player_count},
        {"label": "战队维度", "value": total_team_count},
        {"label": "涉及选手", "value": unique_player_count},
        {"label": "涉及战队", "value": unique_team_count},
        {"label": "单日峰值", "value": max_daily_total},
    ]
    max_radar_value = max([int(item["value"] or 0) for item in radar_items] or [0])
    if rows and max_radar_value > 0:
        import math

        center_x = 250
        center_y = 225
        radius = 132

        def point_for(index: int, ratio: float, base_radius: float = radius) -> tuple[float, float]:
            angle = -math.pi / 2 + index * 2 * math.pi / len(radar_items)
            return (
                center_x + math.cos(angle) * base_radius * ratio,
                center_y + math.sin(angle) * base_radius * ratio,
            )

        grid_polygons = []
        for step in range(1, 5):
            ratio = step / 4
            points = " ".join(
                f"{point_for(index, ratio)[0]:.1f},{point_for(index, ratio)[1]:.1f}"
                for index in range(len(radar_items))
            )
            grid_polygons.append(
                f'<polygon points="{points}" fill="none" stroke="rgba(17, 24, 39, 0.10)" stroke-width="1"/>'
            )
        axis_lines = []
        label_nodes = []
        data_points = []
        for index, item in enumerate(radar_items):
            outer_x, outer_y = point_for(index, 1)
            label_x, label_y = point_for(index, 1.28)
            ratio = min(float(item["value"] or 0) / max_radar_value, 1.0)
            data_x, data_y = point_for(index, ratio)
            axis_lines.append(
                f'<line x1="{center_x}" y1="{center_y}" x2="{outer_x:.1f}" y2="{outer_y:.1f}" stroke="rgba(17, 24, 39, 0.10)"/>'
            )
            label_nodes.append(
                f"""
                <g>
                  <text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="13" font-weight="700" fill="#111827">{escape(str(item['label']))}</text>
                  <text x="{label_x:.1f}" y="{label_y + 17:.1f}" text-anchor="middle" font-size="12" fill="#64748b">{item['value']}</text>
                </g>
                """
            )
            data_points.append((data_x, data_y, item))
        polygon_points = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in data_points)
        point_nodes = "".join(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#2563eb"><title>{escape(str(item["label"]))}：{item["value"]}</title></circle>'
            for x, y, item in data_points
        )
        chart_svg = f"""
        <div class="dimension-chart-wrap" style="overflow-x:auto;">
          <svg viewBox="0 0 500 450" role="img" aria-label="赛季维度数据六边形图" style="max-width:680px;width:100%;height:auto;display:block;margin:0 auto;">
            <rect x="0" y="0" width="500" height="450" rx="28" fill="#f8fafc"/>
            {''.join(grid_polygons)}
            {''.join(axis_lines)}
            <polygon points="{polygon_points}" fill="rgba(37, 99, 235, 0.22)" stroke="#2563eb" stroke-width="3"/>
            {point_nodes}
            {''.join(label_nodes)}
          </svg>
        </div>
        """
    else:
        chart_svg = '<div class="alert alert-secondary mb-0">当前筛选范围内还没有可绘制的六边形维度数据。</div>'
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">维度数据六边形图</h2>
          <p class="section-copy mb-0">按当前筛选范围汇总比赛日、选手维度、战队维度、涉及选手、涉及战队和单日峰值。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <span class="badge rounded-pill text-bg-primary">六维画像</span>
          <span class="badge rounded-pill text-bg-light">按最大值归一</span>
        </div>
      </div>
      <div class="row g-3 mb-3">
        <div class="col-6 col-lg-3"><div class="stat-card h-100 p-3 border-0 shadow-sm"><div class="stat-label">比赛日</div><div class="stat-value mt-2">{total_day_count}</div></div></div>
        <div class="col-6 col-lg-3"><div class="stat-card h-100 p-3 border-0 shadow-sm"><div class="stat-label">选手维度</div><div class="stat-value mt-2">{total_player_count}</div></div></div>
        <div class="col-6 col-lg-3"><div class="stat-card h-100 p-3 border-0 shadow-sm"><div class="stat-label">战队维度</div><div class="stat-value mt-2">{total_team_count}</div></div></div>
        <div class="col-6 col-lg-3"><div class="stat-card h-100 p-3 border-0 shadow-sm"><div class="stat-label">单日峰值</div><div class="stat-value mt-2">{max_daily_total}</div></div></div>
      </div>
      {chart_svg}
    </section>
    """


def get_dimension_stats_manage_page(ctx: RequestContext, alert: str = "") -> str:
    data = load_validated_data()
    selected_competition = form_value(ctx.query, "competition").strip()
    selected_season = form_value(ctx.query, "season").strip()
    selected_played_on = form_value(ctx.query, "played_on").strip()
    all_rows = build_dimension_stats_day_rows(data)
    all_rows = [
        row
        for row in all_rows
        if ctx.current_user and can_manage_matches(ctx.current_user, data, str(row["competition_name"]))
    ]
    visible_rows = [
        row
        for row in all_rows
        if (not selected_competition or row["competition_name"] == selected_competition)
        and (not selected_season or row["season_name"] == selected_season)
        and (not selected_played_on or row["played_on"] == selected_played_on)
    ]
    chart_panel_html = build_dimension_stats_chart_panel(visible_rows)
    competition_options = sorted({str(row["competition_name"]) for row in all_rows})
    season_options = sorted(
        {
            str(row["season_name"])
            for row in all_rows
            if not selected_competition or row["competition_name"] == selected_competition
        }
    )
    day_options = sorted(
        {
            str(row["played_on"])
            for row in all_rows
            if (not selected_competition or row["competition_name"] == selected_competition)
            and (not selected_season or row["season_name"] == selected_season)
        },
        reverse=True,
    )
    rows_html = []
    for row in visible_rows:
        can_manage = bool(ctx.current_user and can_manage_matches(ctx.current_user, data, str(row["competition_name"])))
        players_preview = "、".join(row["players"][:6]) + (" 等" if len(row["players"]) > 6 else "")
        teams_preview = "、".join(row["teams"][:6]) + (" 等" if len(row["teams"]) > 6 else "")
        delete_action = (
            f"""
            <form method="post" action="/dimension-stats" class="m-0" onsubmit="return confirm('确认删除 {escape(str(row['competition_name']))} / {escape(str(row['season_name']))} / {escape(str(row['played_on']))} 这一天的赛季维度数据吗？');">
              <input type="hidden" name="action" value="delete_dimension_day">
              <input type="hidden" name="competition_name" value="{escape(str(row['competition_name']))}">
              <input type="hidden" name="season" value="{escape(str(row['season_name']))}">
              <input type="hidden" name="played_on" value="{escape(str(row['played_on']))}">
              <input class="form-control form-control-sm mb-1" name="danger_confirmation" placeholder="输入 删除维度 确认">
              <button type="submit" class="btn btn-sm btn-outline-danger">删除这一天</button>
            </form>
            """
            if can_manage
            else '<span class="text-secondary small">无管理权限</span>'
        )
        rows_html.append(
            f"""
            <tr>
              <td>{escape(str(row['played_on']))}</td>
              <td>{escape(str(row['competition_name']))}</td>
              <td>{escape(str(row['season_name']))}</td>
              <td>{row['player_count']} 条</td>
              <td>{row['team_count']} 条</td>
              <td class="small text-secondary">{escape(players_preview or '-')}</td>
              <td class="small text-secondary">{escape(teams_preview or '-')}</td>
              <td>{delete_action}</td>
            </tr>
            """
        )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">Dimension Stats Admin</div>
      <h1 class="mb-3">赛季维度数据管理</h1>
      <p class="hero-copy mb-0">按比赛日查看系统内已导入的赛季维度补充数据，并可按天删除后重新上传。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <form method="get" action="/dimension-stats" class="row g-3 align-items-end">
        <div class="col-12 col-lg-4">
          <label class="form-label">赛事</label>
          <select class="form-select" name="competition" onchange="this.form.submit()">
            <option value="">全部赛事</option>
            {''.join(f'<option value="{escape(item)}"{" selected" if item == selected_competition else ""}>{escape(item)}</option>' for item in competition_options)}
          </select>
        </div>
        <div class="col-12 col-lg-3">
          <label class="form-label">赛季</label>
          <select class="form-select" name="season" onchange="this.form.submit()">
            <option value="">全部赛季</option>
            {''.join(f'<option value="{escape(item)}"{" selected" if item == selected_season else ""}>{escape(item)}</option>' for item in season_options)}
          </select>
        </div>
        <div class="col-12 col-lg-3">
          <label class="form-label">比赛日</label>
          <select class="form-select" name="played_on" onchange="this.form.submit()">
            <option value="">全部比赛日</option>
            {''.join(f'<option value="{escape(item)}"{" selected" if item == selected_played_on else ""}>{escape(item)}</option>' for item in day_options)}
          </select>
        </div>
        <div class="col-12 col-lg-2">
          <a class="btn btn-outline-dark w-100" href="/dimension-stats">重置</a>
        </div>
      </form>
    </section>
    {chart_panel_html}
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">已导入比赛日</h2>
          <p class="section-copy mb-0">共 {len(visible_rows)} 个比赛日；删除只影响这一天的赛季维度补充数据，不会删除比赛记录、队员或战队档案。</p>
        </div>
        <a class="btn btn-dark" href="/matches/new">返回批量导入</a>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr><th>比赛日</th><th>赛事</th><th>赛季</th><th>选手维度</th><th>战队维度</th><th>涉及选手</th><th>涉及战队</th><th>操作</th></tr>
          </thead>
          <tbody>{''.join(rows_html) or '<tr><td colspan="8" class="text-secondary">当前没有符合条件的赛季维度数据。</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    """
    return layout("赛季维度数据管理", body, ctx, alert=alert or form_value(ctx.query, "alert").strip())


def handle_dimension_stats_manage(ctx: RequestContext, start_response):
    if not ctx.current_user:
        return redirect(start_response, f"/login?next={quote('/dimension-stats')}")
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_dimension_stats_manage_page(ctx))
    action = form_value(ctx.form, "action").strip()
    if action != "delete_dimension_day":
        return start_response_html(start_response, "405 Method Not Allowed", layout("请求无效", '<div class="alert alert-danger">请求无效。</div>', ctx))
    data = load_validated_data()
    competition_name = form_value(ctx.form, "competition_name").strip()
    season_name = form_value(ctx.form, "season").strip()
    played_on = form_value(ctx.form, "played_on").strip()
    if not competition_name or not season_name or not played_on:
        return start_response_html(start_response, "200 OK", get_dimension_stats_manage_page(ctx, "请先选择要删除的赛事、赛季和比赛日。"))
    if not can_manage_matches(ctx.current_user, data, competition_name):
        return start_response_html(start_response, "200 OK", get_dimension_stats_manage_page(ctx, f"你没有权限管理 {competition_name} 的维度数据。"))
    confirmation_error = danger_confirmation_error(
        form_value(ctx.form, "danger_confirmation"),
        "删除维度",
        "删除单日维度数据",
    )
    if confirmation_error:
        return start_response_html(start_response, "200 OK", get_dimension_stats_manage_page(ctx, confirmation_error))
    try:
        deleted_player_count, deleted_team_count = clear_season_dimension_stats_for_day(
            competition_name,
            season_name,
            played_on,
        )
        invalidate_validated_data_cache()
    except Exception as exc:
        return start_response_html(start_response, "200 OK", get_dimension_stats_manage_page(ctx, f"删除维度数据失败：{exc}"))
    audit_action(
        ctx,
        "dimension.delete_day",
        target_type="competition",
        target_id=competition_name,
        summary=f"删除 {competition_name} / {season_name} / {played_on} 维度数据",
        metadata={
            "competition_name": competition_name,
            "season_name": season_name,
            "played_on": played_on,
            "deleted_player_count": deleted_player_count,
            "deleted_team_count": deleted_team_count,
        },
    )
    next_path = build_scoped_path("/dimension-stats", competition_name, season_name)
    next_path = append_alert_query(
        f"{next_path}&played_on={quote(played_on)}" if "?" in next_path else f"{next_path}?played_on={quote(played_on)}",
        f"已删除 {played_on} 维度数据：选手 {deleted_player_count} 条，战队 {deleted_team_count} 条。",
    )
    return redirect(start_response, next_path)


def build_team_logo_import_panel(
    ctx: RequestContext,
    values: dict[str, str] | None = None,
) -> str:
    current = values or {
        "competition_name": form_value(ctx.query, "competition").strip(),
        "season": form_value(ctx.query, "season").strip(),
    }
    competition_field_html = build_match_competition_field(
        current["competition_name"],
        ctx.current_user,
    )
    season_field_html = build_match_season_field(
        current["competition_name"],
        current["season"],
        include_non_ongoing=True,
    )
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-4">
        <div>
          <h2 class="section-title mb-2">Excel 批量导入赛季战队图标</h2>
          <p class="section-copy mb-0">只识别 `战队名称`、`战队logo` 两列。会按你当前选择的赛事和赛季批量更新队标；如果这个赛季下还没有该战队，也会先自动创建赛季战队档案。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <a class="btn btn-outline-dark" href="/assets/templates/team-logo-upload-template.xlsx">下载战队图标模板</a>
        </div>
      </div>
      <form method="post" action="/matches/new" enctype="multipart/form-data">
        <input type="hidden" name="action" value="import_team_logo_excel">
        <div class="row g-3">
          <div class="col-12 col-xl-4">
            <label class="form-label">地区赛事页</label>
            {competition_field_html}
          </div>
          <div class="col-12 col-xl-3">
            <label class="form-label">赛季</label>
            {season_field_html}
          </div>
          <div class="col-12 col-xl-5">
            <label class="form-label">选择 Excel 文件</label>
            <input class="form-control" type="file" name="team_logo_excel_file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet">
          </div>
        </div>
        <div class="small text-secondary mt-3">`战队logo` 列优先识别你直接插入到 Excel 单元格里的图片；如果这一格没有嵌图，也支持填写站内资源路径，例如 `assets/teams/logo.png`，或 `https://...` 外链地址。这个导入只会创建或更新赛季战队档案的图标，不会改成员、负责人和比赛数据。</div>
        <div class="d-flex flex-wrap gap-2 mt-4">
          <button type="submit" class="btn btn-dark">上传并导入战队图标</button>
        </div>
      </form>
    </section>
    """


def build_player_photo_import_panel(
    ctx: RequestContext,
    values: dict[str, str] | None = None,
) -> str:
    current = values or {
        "competition_name": form_value(ctx.query, "competition").strip(),
        "season": form_value(ctx.query, "season").strip(),
    }
    competition_field_html = build_match_competition_field(
        current["competition_name"],
        ctx.current_user,
    )
    season_field_html = build_match_season_field(
        current["competition_name"],
        current["season"],
        include_non_ongoing=True,
    )
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-4">
        <div>
          <h2 class="section-title mb-2">压缩包批量导入赛季队员头像</h2>
          <p class="section-copy mb-0">上传包含头像图片的 zip 压缩包。系统会按文件名里的参赛 ID 自动匹配当前赛事赛季中已有比赛记录的队员，未匹配到的文件会跳过。</p>
        </div>
      </div>
      <form method="post" action="/matches/new" enctype="multipart/form-data">
        <div class="row g-3">
          <div class="col-12 col-xl-4">
            <label class="form-label">地区赛事页</label>
            {competition_field_html}
          </div>
          <div class="col-12 col-xl-3">
            <label class="form-label">赛季</label>
            {season_field_html}
          </div>
          <div class="col-12 col-xl-5">
            <label class="form-label">选择 zip 压缩包</label>
            <input class="form-control" type="file" name="player_photo_zip_file" accept=".zip,application/zip,application/x-zip-compressed">
          </div>
        </div>
        <div class="small text-secondary mt-3">压缩包内图片文件名一般为 `id.png`，例如 `player-001.png`。支持 PNG、JPG、JPEG、WEBP、GIF；同名目录不影响匹配，系统只取文件名去掉扩展名后的 ID。</div>
        <div class="d-flex flex-wrap gap-2 mt-4">
          <button type="submit" class="btn btn-dark" name="action" value="import_player_photo_zip">上传并导入队员头像</button>
          <button type="submit" class="btn btn-outline-dark" name="action" value="export_season_player_photo_roster" formaction="/matches/new" formmethod="get" formnovalidate>导出本赛季队员名单</button>
        </div>
      </form>
    </section>
    """


def _import_batch_status_label(status: str) -> str:
    labels = {
        "running": "处理中",
        "succeeded": "成功",
        "failed": "失败",
        "rolled_back": "已回滚",
    }
    return labels.get(str(status or "").strip(), status or "未知")


def build_import_batches_panel(ctx: RequestContext) -> str:
    batches = load_import_batches()
    can_rollback = is_admin_user(ctx.current_user)
    rows = []
    for item in batches[:20]:
        batch_id = str(item.get("batch_id") or "").strip()
        status = str(item.get("status") or "").strip()
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        metadata_copy = " · ".join(
            part
            for part in [
                f"比赛 {metadata.get('created_matches')}" if metadata.get("created_matches") is not None else "",
                f"更新 {metadata.get('updated_matches')}" if metadata.get("updated_matches") is not None else "",
                f"选手 {metadata.get('created_players')}" if metadata.get("created_players") is not None else "",
                f"维度 {metadata.get('player_rows')}/{metadata.get('team_rows')}" if metadata.get("player_rows") is not None else "",
            ]
            if part
        )
        rollback_form = ""
        if status == "succeeded" and can_rollback:
            rollback_form = f"""
            <form method="post" action="/matches/new" class="d-flex flex-column gap-1">
              <input type="hidden" name="action" value="rollback_import_batch">
              <input type="hidden" name="batch_id" value="{escape(batch_id)}">
              <input class="form-control form-control-sm" name="danger_confirmation" placeholder="输入 回滚 {escape(batch_id)}">
              <button class="btn btn-sm btn-outline-danger" type="submit" data-confirm="确认回滚导入批次 {escape(batch_id)}？当前数据会恢复到该批次导入前。">回滚</button>
            </form>
            """
        rows.append(
            f"""
            <tr>
              <td><code>{escape(batch_id)}</code></td>
              <td><span class="chip">{escape(_import_batch_status_label(status))}</span></td>
              <td>
                <div class="fw-semibold">{escape(str(item.get('label') or item.get('action') or '导入'))}</div>
                <div class="small text-secondary">{escape(str(item.get('summary') or ''))}</div>
                {f'<div class="small text-secondary">{escape(metadata_copy)}</div>' if metadata_copy else ''}
              </td>
              <td class="small text-secondary">
                <div>{escape(str(item.get('created_at') or ''))}</div>
                <div>{escape(str(item.get('created_by') or ''))}</div>
                {f'<div>文件：{escape(str(item.get("filename") or ""))}</div>' if item.get("filename") else ''}
              </td>
              <td>{rollback_form or ('<span class="small text-secondary">仅管理员可回滚</span>' if status == 'succeeded' else '<span class="small text-secondary">不可回滚</span>')}</td>
            </tr>
            """
        )
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">导入记录与回滚</h2>
          <p class="section-copy mb-0">批量创建、比赛 Excel、维度 Excel 会自动生成批次。回滚会恢复到该批次导入前的数据状态，请谨慎操作。</p>
        </div>
        <span class="chip">最近 {len(batches[:20])} 条</span>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead><tr><th>批次</th><th>状态</th><th>摘要</th><th>创建</th><th>操作</th></tr></thead>
          <tbody>{''.join(rows) or '<tr><td colspan="5" class="text-secondary">暂无导入记录。</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    """


def get_management_form_values(
    ctx: RequestContext,
    values: dict[str, str] | None = None,
) -> dict[str, str]:
    current = values or {}
    return {
        "competition_name": current.get(
            "competition_name",
            form_value(ctx.form, "competition_name").strip()
            or form_value(ctx.query, "competition_name").strip()
            or form_value(ctx.query, "competition").strip(),
        ),
        "season": current.get(
            "season",
            form_value(ctx.form, "season").strip() or form_value(ctx.query, "season").strip(),
        ),
        "stage": current.get(
            "stage",
            form_value(ctx.form, "stage").strip() or form_value(ctx.query, "stage").strip(),
        ),
        "played_on": current.get(
            "played_on",
            form_value(ctx.form, "played_on").strip() or form_value(ctx.query, "played_on").strip(),
        ),
        "keyword": current.get(
            "keyword",
            form_value(ctx.form, "keyword").strip() or form_value(ctx.query, "keyword").strip(),
        ),
        "page": current.get(
            "page",
            form_value(ctx.form, "page").strip() or form_value(ctx.query, "page").strip() or "1",
        ),
        "per_page": current.get(
            "per_page",
            form_value(ctx.form, "per_page").strip() or form_value(ctx.query, "per_page").strip() or "25",
        ),
    }


def normalize_positive_int(value: str, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        parsed = default
    return max(minimum, min(maximum, parsed))


def build_match_management_path(
    ctx: RequestContext,
    competition_name: str = "",
    season_name: str = "",
    values: dict[str, str] | None = None,
) -> str:
    current = get_management_form_values(ctx, values)
    if competition_name and not current["competition_name"]:
        current["competition_name"] = competition_name
    if season_name and not current["season"]:
        current["season"] = season_name
    params = {
        key: value
        for key, value in {
            "competition": current["competition_name"],
            "season": current["season"],
            "stage": current["stage"],
            "played_on": current["played_on"],
            "keyword": current["keyword"],
            "page": "" if current["page"] in {"", "1"} else current["page"],
            "per_page": "" if current["per_page"] in {"", "25"} else current["per_page"],
        }.items()
        if value
    }
    if not params:
        return "/matches/new"
    return f"/matches/new?{urlencode(params)}"


def build_match_management_panel(
    ctx: RequestContext,
    values: dict[str, str] | None = None,
) -> str:
    current = get_management_form_values(ctx, values)
    data = load_validated_data()
    competition_name = current["competition_name"]
    season_name = current["season"]
    stage_value = current["stage"]
    played_on = current["played_on"]
    keyword = current["keyword"]
    requested_page = normalize_positive_int(current["page"], 1, 1, 100000)
    per_page = normalize_positive_int(current["per_page"], 25, 10, 100)
    if per_page not in {10, 25, 50, 100}:
        per_page = 25
    competition_field_html = build_match_competition_field(
        competition_name,
        ctx.current_user,
    )
    season_field_html = build_match_season_field(
        competition_name,
        season_name,
        include_non_ongoing=True,
    )
    filtered_matches = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
        )
        if (
            not competition_name
            or str(match.get("competition_name") or "").strip() == competition_name
        )
        and (not season_name or str(match.get("season") or "").strip() == season_name)
        and (not stage_value or str(match.get("stage") or "").strip() == stage_value)
        and (not played_on or str(match.get("played_on") or "").strip() == played_on)
        and (
            not keyword
            or keyword.lower() in str(match.get("match_id") or "").lower()
            or keyword.lower() in str(match.get("group_label") or "").lower()
            or keyword.lower() in str(match.get("table_label") or "").lower()
            or keyword.lower() in str(match.get("format") or "").lower()
        )
    ]
    total_matches = len(filtered_matches)
    page_count = max(1, (total_matches + per_page - 1) // per_page)
    page = min(requested_page, page_count)
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    page_matches = filtered_matches[start_index:end_index]
    page_summary = (
        f"显示第 {start_index + 1}-{min(end_index, total_matches)} 场，共 {total_matches} 场"
        if total_matches
        else "当前筛选下没有比赛"
    )
    rows_html = "".join(
        f"""
        <tr>
          <td><input class="form-check-input" type="checkbox" name="match_ids" value="{escape(match['match_id'])}"></td>
          <td>{escape(match['match_id'])}</td>
          <td>{escape(str(match.get('competition_name') or ''))}</td>
          <td>{escape(str(match.get('season') or ''))}</td>
          <td>{escape(match['played_on'])}</td>
          <td>{escape(STAGE_LABELS.get(match['stage'], match['stage']))}</td>
          <td>第 {match['round']} 轮</td>
          <td>{escape(str(match.get('group_label') or '未设置'))}</td>
          <td>{escape(str(match.get('table_label') or '未设置'))}</td>
          <td>{escape(match['format'])}</td>
          <td>{'待补录' if match['format'] == '待补录' else '已录入'}</td>
          <td>{'<span class="badge text-bg-warning">抽局</span>' if match.get('exclude_from_team_scores') else '<span class="badge text-bg-light text-dark border">计入战队</span>'}</td>
          <td>
            <div class="d-flex flex-wrap gap-2">
              <a class="btn btn-sm btn-outline-dark" href="/matches/{escape(match['match_id'])}">详情</a>
              <a class="btn btn-sm btn-dark" href="/matches/{escape(match['match_id'])}/edit?next={quote('/matches/new')}">编辑</a>
            </div>
          </td>
        </tr>
        """
        for match in page_matches
    )
    pagination_items = []
    if page_count > 1:
        def pagination_link(label: str, target_page: int, disabled: bool = False, active: bool = False) -> str:
            if disabled:
                return f'<span class="btn btn-sm btn-outline-dark disabled">{escape(label)}</span>'
            link_values = {**current, "page": str(target_page), "per_page": str(per_page)}
            class_name = "btn btn-sm btn-dark" if active else "btn btn-sm btn-outline-dark"
            return f'<a class="{class_name}" href="{escape(build_match_management_path(ctx, values=link_values))}#match-list">{escape(label)}</a>'

        pagination_items.append(pagination_link("上一页", page - 1, disabled=page <= 1))
        window_start = max(1, page - 2)
        window_end = min(page_count, page + 2)
        if window_start > 1:
            pagination_items.append(pagination_link("1", 1, active=page == 1))
            if window_start > 2:
                pagination_items.append('<span class="btn btn-sm btn-outline-dark disabled">...</span>')
        for page_no in range(window_start, window_end + 1):
            pagination_items.append(pagination_link(str(page_no), page_no, active=page_no == page))
        if window_end < page_count:
            if window_end < page_count - 1:
                pagination_items.append('<span class="btn btn-sm btn-outline-dark disabled">...</span>')
            pagination_items.append(pagination_link(str(page_count), page_count, active=page == page_count))
        pagination_items.append(pagination_link("下一页", page + 1, disabled=page >= page_count))
    pagination_html = (
        f"""
        <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-3 mt-3">
          <div class="small text-secondary">{escape(page_summary)} · 第 {page} / {page_count} 页</div>
          <div class="d-flex flex-wrap gap-2">{''.join(pagination_items)}</div>
        </div>
        """
        if total_matches
        else '<div class="small text-secondary mt-3">当前筛选下没有比赛。</div>'
    )
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4" id="match-list">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-4">
        <div>
          <h2 class="section-title mb-2">批量管理比赛</h2>
          <p class="section-copy mb-0">这里可以筛选、查看、编辑和批量删除比赛。列表已分页显示，避免数据量大时页面过长。</p>
        </div>
        <span class="chip">{escape(page_summary)}</span>
      </div>
      <form method="get" action="/matches/new" class="mb-4">
        <input type="hidden" name="page" value="1">
        <div class="row g-3">
          <div class="col-12 col-xl-3">
            <label class="form-label">地区赛事页</label>
            {competition_field_html}
          </div>
          <div class="col-12 col-xl-3">
            <label class="form-label">赛季</label>
            {season_field_html}
          </div>
          <div class="col-12 col-md-4 col-xl-2">
            <label class="form-label">赛段</label>
            <select class="form-select" name="stage">
              <option value="">全部赛段</option>
              {option_tags(STAGE_OPTIONS, stage_value)}
            </select>
          </div>
          <div class="col-12 col-md-4 col-xl-2">
            <label class="form-label">日期</label>
            <input class="form-control" type="date" name="played_on" value="{escape(played_on)}">
          </div>
          <div class="col-12 col-md-4 col-xl-2">
            <label class="form-label">关键词</label>
            <input class="form-control" name="keyword" value="{escape(keyword)}" placeholder="编号/分组/房间/板型">
          </div>
          <div class="col-12 col-md-4 col-xl-2">
            <label class="form-label">每页显示</label>
            <select class="form-select" name="per_page">
              {''.join(f'<option value="{size}"{" selected" if size == per_page else ""}>{size} 场</option>' for size in [10, 25, 50, 100])}
            </select>
          </div>
        </div>
        <div class="d-flex flex-wrap gap-2 mt-4">
          <button type="submit" class="btn btn-dark">查询比赛</button>
          <a class="btn btn-outline-dark" href="/matches/new">重置筛选</a>
        </div>
      </form>
      <form method="post" action="/matches/new">
        <input type="hidden" name="competition_name" value="{escape(competition_name)}">
        <input type="hidden" name="season" value="{escape(season_name)}">
        <input type="hidden" name="stage" value="{escape(stage_value)}">
        <input type="hidden" name="played_on" value="{escape(played_on)}">
        <input type="hidden" name="keyword" value="{escape(keyword)}">
        <input type="hidden" name="page" value="{page}">
        <input type="hidden" name="per_page" value="{per_page}">
        <div class="table-responsive">
          <table class="table align-middle">
            <thead>
              <tr>
                <th><input class="form-check-input" type="checkbox" data-toggle-all-matches></th>
                <th>编号</th>
                <th>赛事</th>
                <th>赛季</th>
                <th>日期</th>
                <th>赛段</th>
                <th>轮次</th>
                <th>分组</th>
                <th>房间</th>
                <th>板型</th>
                <th>状态</th>
                <th>战队计分</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>{rows_html or '<tr><td colspan="13" class="text-secondary">当前筛选下没有比赛。</td></tr>'}</tbody>
          </table>
        </div>
        {pagination_html}
        <div class="d-flex flex-wrap gap-2 mt-3">
          <div class="w-100">
            <label class="form-label">批量删除确认</label>
            <input class="form-control" name="danger_confirmation" placeholder="删除比赛时输入 删除比赛 确认">
            <div class="small text-secondary mt-2">只有批量删除会校验此确认文字；设为抽局和取消抽局不会删除比赛。</div>
          </div>
          <button type="submit" class="btn btn-outline-dark" name="action" value="batch_mark_team_score_excluded">设为抽局</button>
          <button type="submit" class="btn btn-outline-dark" name="action" value="batch_unmark_team_score_excluded">取消抽局</button>
          <button type="submit" class="btn btn-outline-danger" name="action" value="batch_delete_matches">批量删除选中比赛</button>
        </div>
      </form>
      <script>
        (() => {{
          const toggle = document.querySelector("[data-toggle-all-matches]");
          if (!toggle) return;
          const checkboxes = Array.from(document.querySelectorAll('input[name="match_ids"]'));
          toggle.addEventListener("change", () => {{
            checkboxes.forEach((item) => {{
              item.checked = toggle.checked;
            }});
          }});
        }})();
      </script>
    </section>
    """


def read_excel_sheet_rows(upload: UploadedFile, sheet_name: str) -> list[dict[str, str]]:
    with ZipFile(BytesIO(upload.data)) as archive:
        shared_strings = load_excel_shared_strings(archive)
        sheet_path = resolve_sheet_archive_path(archive, sheet_name)
        if not sheet_path:
            return []
        sheet_xml = ET.fromstring(archive.read(sheet_path))

    rows: list[list[str]] = []
    for row in sheet_xml.findall("main:sheetData/main:row", EXCEL_NS):
        if len(rows) >= MAX_EXCEL_SHEET_ROWS:
            raise ValueError(f"{sheet_name} 工作表超过 {MAX_EXCEL_SHEET_ROWS} 行，请拆分后再导入。")
        values: list[str] = []
        next_column_index = 1
        for cell in row.findall("main:c", EXCEL_NS):
            cell_ref = cell.attrib.get("r", "")
            column_index = excel_column_index(cell_ref) if cell_ref else next_column_index
            while len(values) < max(column_index - 1, 0):
                values.append("")
            text = ""
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                text = "".join(node.text or "" for node in cell.findall(".//main:t", EXCEL_NS))
            elif cell_type == "s":
                value_node = cell.find("main:v", EXCEL_NS)
                shared_index = int(value_node.text) if value_node is not None and value_node.text else -1
                if 0 <= shared_index < len(shared_strings):
                    text = shared_strings[shared_index]
            else:
                value_node = cell.find("main:v", EXCEL_NS)
                text = value_node.text if value_node is not None and value_node.text is not None else ""
            values.append(text)
            next_column_index = column_index + 1
        rows.append(values)
    if not rows:
        return []
    headers = [
        EXCEL_HEADER_ALIASES.get(str(item or "").strip(), str(item or "").strip())
        for item in rows[0]
    ]
    return [
        {
            headers[index]: (row[index].strip() if index < len(row) else "")
            for index in range(len(headers))
            if headers[index]
        }
        for row in rows[1:]
        if any(str(value or "").strip() for value in row)
    ]


def read_first_available_sheet_rows(upload: UploadedFile, sheet_names: list[str]) -> list[dict[str, str]]:
    for sheet_name in sheet_names:
        rows = read_excel_sheet_rows(upload, sheet_name)
        if rows:
            return rows
    return []


def load_excel_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    shared_strings_xml = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.findall(".//main:t", EXCEL_NS))
        for item in shared_strings_xml.findall("main:si", EXCEL_NS)
    ]


def normalize_archive_target(base_path: str, target: str) -> str:
    if not target:
        return ""
    if target.startswith("/"):
        return target.lstrip("/")
    return str((PurePosixPath(base_path).parent / target).as_posix())


def resolve_sheet_archive_path(archive: ZipFile, sheet_name: str) -> str:
    workbook_xml = ET.fromstring(archive.read("xl/workbook.xml"))
    rels_xml = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_target_by_id = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_xml.findall(f"{{{PKG_REL_NS}}}Relationship")
    }
    for sheet in workbook_xml.findall("main:sheets/main:sheet", EXCEL_NS):
        if str(sheet.attrib.get("name") or "").strip() != sheet_name.strip():
            continue
        relation_id = sheet.attrib.get(f"{{{REL_NS}}}id", "")
        return normalize_archive_target("xl/workbook.xml", rel_target_by_id.get(relation_id, ""))
    return ""


def resolve_part_relationships_path(part_path: str) -> str:
    part = PurePosixPath(part_path)
    return str((part.parent / "_rels" / f"{part.name}.rels").as_posix())


def read_excel_sheet_embedded_images(
    upload: UploadedFile,
    sheet_name: str,
) -> dict[tuple[int, int], tuple[str, bytes]]:
    with ZipFile(BytesIO(upload.data)) as archive:
        sheet_path = resolve_sheet_archive_path(archive, sheet_name)
        if not sheet_path:
            return {}
        wps_images = read_wps_cell_images(archive, sheet_path)
        if wps_images:
            return wps_images
        sheet_xml = ET.fromstring(archive.read(sheet_path))
        drawing_node = sheet_xml.find("main:drawing", EXCEL_NS)
        if drawing_node is None:
            return {}
        sheet_rels_path = resolve_part_relationships_path(sheet_path)
        if sheet_rels_path not in archive.namelist():
            return {}
        sheet_rels_xml = ET.fromstring(archive.read(sheet_rels_path))
        rel_target_by_id = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in sheet_rels_xml.findall(f"{{{PKG_REL_NS}}}Relationship")
        }
        drawing_rel_id = drawing_node.attrib.get(f"{{{REL_NS}}}id", "")
        drawing_path = normalize_archive_target(sheet_path, rel_target_by_id.get(drawing_rel_id, ""))
        if not drawing_path or drawing_path not in archive.namelist():
            return {}
        drawing_xml = ET.fromstring(archive.read(drawing_path))
        drawing_rels_path = resolve_part_relationships_path(drawing_path)
        if drawing_rels_path not in archive.namelist():
            return {}
        drawing_rels_xml = ET.fromstring(archive.read(drawing_rels_path))
        media_target_by_id = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in drawing_rels_xml.findall(f"{{{PKG_REL_NS}}}Relationship")
        }
        embedded_images: dict[tuple[int, int], tuple[str, bytes]] = {}
        anchors = [
            *drawing_xml.findall("xdr:twoCellAnchor", XDR_NS),
            *drawing_xml.findall("xdr:oneCellAnchor", XDR_NS),
        ]
        for anchor in anchors:
            from_node = anchor.find("xdr:from", XDR_NS)
            pic_node = anchor.find("xdr:pic", XDR_NS)
            if from_node is None or pic_node is None:
                continue
            row_text = from_node.findtext("xdr:row", default="", namespaces=XDR_NS)
            col_text = from_node.findtext("xdr:col", default="", namespaces=XDR_NS)
            try:
                row_index = int(row_text) + 1
                col_index = int(col_text) + 1
            except ValueError:
                continue
            blip_node = pic_node.find(".//a:blip", XDR_NS)
            if blip_node is None:
                continue
            embed_id = blip_node.attrib.get(f"{{{REL_NS}}}embed", "")
            media_path = normalize_archive_target(drawing_path, media_target_by_id.get(embed_id, ""))
            if not media_path or media_path not in archive.namelist():
                continue
            embedded_images[(row_index, col_index)] = (
                PurePosixPath(media_path).name,
                archive.read(media_path),
            )
        return embedded_images


def read_wps_cell_images(
    archive: ZipFile,
    sheet_path: str,
) -> dict[tuple[int, int], tuple[str, bytes]]:
    if "xl/cellimages.xml" not in archive.namelist() or "xl/_rels/cellimages.xml.rels" not in archive.namelist():
        return {}
    shared_strings = load_excel_shared_strings(archive)
    sheet_xml = ET.fromstring(archive.read(sheet_path))
    formula_image_id_by_cell: dict[tuple[int, int], str] = {}
    for row in sheet_xml.findall("main:sheetData/main:row", EXCEL_NS):
        row_number_text = row.attrib.get("r", "").strip()
        try:
            row_number = int(row_number_text)
        except ValueError:
            continue
        for cell in row.findall("main:c", EXCEL_NS):
            cell_ref = cell.attrib.get("r", "")
            column_index = excel_column_index(cell_ref) if cell_ref else 0
            if column_index <= 0:
                continue
            cell_type = cell.attrib.get("t")
            text = ""
            if cell_type == "inlineStr":
                text = "".join(node.text or "" for node in cell.findall(".//main:t", EXCEL_NS))
            elif cell_type == "s":
                value_node = cell.find("main:v", EXCEL_NS)
                shared_index = int(value_node.text) if value_node is not None and value_node.text else -1
                if 0 <= shared_index < len(shared_strings):
                    text = shared_strings[shared_index]
            else:
                value_node = cell.find("main:v", EXCEL_NS)
                text = value_node.text if value_node is not None and value_node.text is not None else ""
            matched = WPS_DISPIMG_PATTERN.search(text or "")
            if matched:
                formula_image_id_by_cell[(row_number, column_index)] = matched.group("image_id")
    if not formula_image_id_by_cell:
        return {}

    cellimages_xml = ET.fromstring(archive.read("xl/cellimages.xml"))
    cellimages_rels_xml = ET.fromstring(archive.read("xl/_rels/cellimages.xml.rels"))
    media_target_by_rel_id = {
        rel.attrib["Id"]: normalize_archive_target("xl/cellimages.xml", rel.attrib["Target"])
        for rel in cellimages_rels_xml.findall(f"{{{PKG_REL_NS}}}Relationship")
    }
    payload_by_image_id: dict[str, tuple[str, bytes]] = {}
    for cell_image in cellimages_xml.findall("etc:cellImage", WPS_CELLIMAGE_NS):
        pic_node = cell_image.find("xdr:pic", WPS_CELLIMAGE_NS)
        if pic_node is None:
            continue
        c_nv_pr = pic_node.find("xdr:nvPicPr/xdr:cNvPr", WPS_CELLIMAGE_NS)
        blip_node = pic_node.find(".//a:blip", WPS_CELLIMAGE_NS)
        if c_nv_pr is None or blip_node is None:
            continue
        image_id = str(c_nv_pr.attrib.get("name") or "").strip()
        rel_id = blip_node.attrib.get(f"{{{REL_NS}}}embed", "")
        media_path = media_target_by_rel_id.get(rel_id, "")
        if not image_id or not media_path or media_path not in archive.namelist():
            continue
        payload_by_image_id[image_id] = (
            PurePosixPath(media_path).name,
            archive.read(media_path),
        )
    embedded_images: dict[tuple[int, int], tuple[str, bytes]] = {}
    for cell_key, image_id in formula_image_id_by_cell.items():
        payload = payload_by_image_id.get(image_id)
        if payload:
            embedded_images[cell_key] = payload
    return embedded_images


def save_embedded_team_logo(team_id: str, original_name: str, image_bytes: bytes) -> str:
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(f"不支持的图片格式：{original_name}")
    signature_error = legacy.validate_image_bytes(original_name, image_bytes)
    if signature_error:
        raise ValueError(signature_error)
    ensure_team_asset_dirs()
    filename = f"{team_id}-{secrets.token_hex(6)}{extension}"
    target = TEAM_UPLOAD_DIR / filename
    target.write_bytes(image_bytes)
    return str(target.relative_to(ROOT_DIR)).replace("\\", "/")


def save_embedded_player_photo(player_id: str, original_name: str, image_bytes: bytes) -> str:
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(f"不支持的图片格式：{original_name}")
    signature_error = legacy.validate_image_bytes(original_name, image_bytes)
    if signature_error:
        raise ValueError(signature_error)
    legacy.ensure_player_asset_dirs()
    target = legacy.PLAYER_UPLOAD_DIR / f"{player_id}-{secrets.token_hex(6)}{extension}"
    target.write_bytes(image_bytes)
    return str(target.relative_to(ROOT_DIR)).replace("\\", "/")


def find_embedded_image_for_row(
    embedded_images: dict[tuple[int, int], tuple[str, bytes]],
    row_index: int,
    preferred_column: int = 2,
) -> tuple[str, bytes] | None:
    exact_match = embedded_images.get((row_index, preferred_column))
    if exact_match:
        return exact_match
    same_row_candidates = [
        (abs(column_index - preferred_column), column_index, payload)
        for (image_row, column_index), payload in embedded_images.items()
        if image_row == row_index
    ]
    if same_row_candidates:
        same_row_candidates.sort(key=lambda item: (item[0], item[1]))
        return same_row_candidates[0][2]
    nearby_row_candidates = [
        (abs(image_row - row_index), abs(column_index - preferred_column), image_row, column_index, payload)
        for (image_row, column_index), payload in embedded_images.items()
        if abs(image_row - row_index) <= 1
    ]
    if nearby_row_candidates:
        nearby_row_candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        return nearby_row_candidates[0][4]
    return None


def validate_excel_upload(upload: UploadedFile | None) -> str:
    if upload is None or not upload.filename:
        return "请先选择要上传的 Excel 文件。"
    if Path(upload.filename).suffix.lower() != ".xlsx":
        return "目前只支持上传 .xlsx 格式的比赛模板。"
    if not upload.data:
        return "上传的 Excel 文件为空，请重新选择。"
    if len(upload.data) > MAX_EXCEL_UPLOAD_BYTES:
        return f"Excel 文件不能超过 {MAX_EXCEL_UPLOAD_BYTES // 1024 // 1024} MB，请拆分后再上传。"
    try:
        with ZipFile(BytesIO(upload.data)) as archive:
            names = set(archive.namelist())
            if "xl/workbook.xml" not in names:
                return "上传的 .xlsx 文件结构无效，请确认文件没有损坏。"
            worksheet_count = sum(1 for name in names if name.startswith("xl/worksheets/") and name.endswith(".xml"))
            if worksheet_count <= 0:
                return "上传的 Excel 文件没有可读取的工作表。"
    except BadZipFile:
        return "上传的 .xlsx 文件无法解析，请确认文件没有损坏。"
    return ""


def validate_zip_upload(upload: UploadedFile | None) -> str:
    if upload is None or not upload.filename:
        return "请先选择要上传的 zip 压缩包。"
    if Path(upload.filename).suffix.lower() != ".zip":
        return "目前只支持上传 .zip 格式的头像压缩包。"
    if not upload.data:
        return "上传的 zip 压缩包为空，请重新选择。"
    if len(upload.data) > MAX_ZIP_UPLOAD_BYTES:
        return f"zip 压缩包不能超过 {MAX_ZIP_UPLOAD_BYTES // 1024 // 1024} MB，请拆分后再上传。"
    try:
        with ZipFile(BytesIO(upload.data)) as archive:
            entries = [
                info
                for info in archive.infolist()
                if not info.is_dir() and not info.filename.startswith("__MACOSX/")
            ]
            if len(entries) > MAX_ZIP_IMAGE_COUNT:
                return f"zip 压缩包内文件不能超过 {MAX_ZIP_IMAGE_COUNT} 个，请拆分后再上传。"
    except BadZipFile:
        return "zip 压缩包无法解析，请确认文件没有损坏。"
    return ""


def normalize_excel_serial_date(value: str, field_label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_label} 不能为空。")
    parsed_iso = parse_date_input(text)
    if parsed_iso:
        return parsed_iso.strftime("%Y-%m-%d")
    try:
        serial = float(text)
    except ValueError as exc:
        raise ValueError(f"{field_label} 格式不正确：{text}") from exc
    base_date = datetime(1899, 12, 30)
    return (base_date + timedelta(days=int(serial))).strftime("%Y-%m-%d")


def parse_excel_metric_value(value: str) -> str | int | float:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return int(number)
    return round(number, 2)


def get_excel_row_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def read_optional_sheet_rows(upload: UploadedFile, sheet_names: list[str]) -> list[dict[str, str]]:
    for sheet_name in sheet_names:
        rows = read_excel_sheet_rows(upload, sheet_name)
        if rows:
            return rows
    return []


def read_scoring_template_metadata(upload: UploadedFile) -> dict[str, object] | None:
    rows = read_excel_sheet_rows(upload, "_scoring_meta")
    if not rows:
        return None
    values = {
        str(row.get("meta_key") or "").strip(): str(row.get("meta_value") or "").strip()
        for row in rows
        if str(row.get("meta_key") or "").strip()
    }
    raw_rule = values.get("scoring_rule_json", "")
    if not raw_rule:
        raise ValueError("模板计分规则元数据缺失，请重新下载模板。")
    try:
        parsed_rule = json.loads(raw_rule)
    except json.JSONDecodeError as exc:
        raise ValueError("模板计分规则元数据损坏，请重新下载模板。") from exc
    if not isinstance(parsed_rule, dict):
        raise ValueError("模板计分规则格式无效，请重新下载模板。")
    scoring_rule = normalize_scoring_rule(parsed_rule)
    try:
        metadata_version = int(values.get("scoring_rule_version") or 0)
    except ValueError as exc:
        raise ValueError("模板计分规则版本无效，请重新下载模板。") from exc
    if metadata_version != int(scoring_rule.get("version") or 1):
        raise ValueError("模板计分规则版本与规则内容不一致，请重新下载模板。")
    return {
        "competition_name": values.get("competition_name", ""),
        "season_name": values.get("season_name", ""),
        "scoring_rule": scoring_rule,
    }


def validate_template_metadata_scope(
    rows: list[dict[str, str]],
    metadata: dict[str, object] | None,
) -> None:
    if not metadata:
        return
    expected_competition = str(metadata.get("competition_name") or "").strip()
    expected_season = str(metadata.get("season_name") or "").strip()
    for row in rows:
        competition_name = str(row.get("competition_name") or "").strip()
        season_name = str(row.get("season_name") or "").strip()
        if expected_competition and competition_name != expected_competition:
            raise ValueError(
                f"模板锁定赛事为 {expected_competition}，不能导入 {competition_name or '空赛事'}。"
            )
        if expected_season and season_name != expected_season:
            raise ValueError(
                f"模板锁定赛季为 {expected_season}，不能导入 {season_name or '空赛季'}。"
            )


def hydrate_excel_rows_from_match_ids(
    rows: list[dict[str, str]],
    data: dict[str, object],
    *,
    require_match_id: bool = False,
) -> None:
    existing_by_id = {
        str(match.get("match_id") or "").strip(): match
        for match in data.get("matches", [])
        if isinstance(match, dict) and str(match.get("match_id") or "").strip()
    }
    for row in rows:
        match_id = str(row.get("match_id") or "").strip()
        if not match_id:
            if require_match_id:
                raise ValueError("新版比赛模板的每一行都必须填写唯一比赛编号。")
            continue
        existing_match = existing_by_id.get(match_id)
        if not existing_match:
            raise ValueError(f"没有找到比赛编号：{match_id}。请先批量创建待补录比赛。")
        row["competition_name"] = get_match_competition_name(existing_match)
        row["season_name"] = str(existing_match.get("season") or "").strip()
        row["played_on"] = str(existing_match.get("played_on") or "").strip()
        row["stage"] = str(existing_match.get("stage") or "").strip()
        row["round"] = str(existing_match.get("round") or "").strip()
        row["game_no"] = str(existing_match.get("game_no") or "").strip()
        if not str(row.get("room_label") or row.get("table_label") or "").strip():
            row["room_label"] = str(existing_match.get("table_label") or "").strip()


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


def parse_excel_optional_int(value: str, default: int) -> int:
    raw = value.strip()
    if not raw:
        return default
    try:
        return int(float(raw))
    except ValueError as exc:
        raise ValueError("需要填写整数。") from exc


def parse_game_no_from_match_id(match_id: str) -> int | None:
    matched = MATCH_SEQUENCE_PATTERN.search(match_id.strip())
    if not matched:
        return None
    try:
        game_no = int(matched.group(1))
    except ValueError:
        return None
    return game_no if game_no > 0 else None


def resolve_excel_game_no(row: dict[str, str]) -> int:
    raw_game_no = row.get("game_no", "").strip()
    if raw_game_no:
        return parse_excel_int(raw_game_no, "game_no")
    match_id = row.get("match_id", "").strip()
    parsed_game_no = parse_game_no_from_match_id(match_id)
    if parsed_game_no is not None:
        return parsed_game_no
    raise ValueError("请填写比赛编号，或补充可解析尾号的编号。")


def parse_excel_award_name(
    player_rows: list[dict[str, str]],
    player_name_key: str,
    award_label: str,
) -> str:
    selected_names = [
        row.get("player_name", "").strip()
        for row in player_rows
        if row.get(player_name_key, "").strip()
    ]
    selected_names = [name for name in selected_names if name]
    if len(selected_names) > 1:
        raise ValueError(f"{award_label} 每局比赛只能标记一位选手。")
    return selected_names[0] if selected_names else ""


def parse_excel_score_breakdown(
    row: dict[str, str],
    scoring_rule: dict[str, object] | None,
) -> dict[str, float]:
    breakdown = {
        field_name: parse_float_value(row.get(field_name, "").strip() or "0", 0.0)
        for field_name, _ in MATCH_SCORE_COMPONENT_FIELDS
    }
    if not isinstance(scoring_rule, dict):
        return breakdown
    for component in scoring_rule.get("components", []):
        if not isinstance(component, dict) or not component.get("enabled", False):
            continue
        field_name = str(component.get("key") or "").strip()
        field_label = str(component.get("label") or "").strip()
        if not field_name:
            continue
        raw_value = str(
            row.get(field_name)
            or (row.get(field_label) if field_label else "")
            or ""
        ).strip()
        breakdown[field_name] = (
            parse_excel_float(raw_value, field_label or field_name)
            if raw_value
            else 0.0
        )
    return breakdown


def normalize_excel_participant_results(match: dict[str, object]) -> None:
    winning_camp = str(match.get("winning_camp") or "").strip()
    if winning_camp not in {"villagers", "werewolves", "third_party"}:
        return
    for participant in match.get("players", []):
        if not isinstance(participant, dict):
            continue
        camp = str(participant.get("camp") or "").strip()
        if camp in {"villagers", "werewolves", "third_party"}:
            participant["result"] = "win" if camp == winning_camp else "loss"


def build_match_from_excel_rows(
    match_row: dict[str, str],
    player_rows: list[dict[str, str]],
    scoring_rule_override: dict[str, object] | None = None,
) -> dict[str, object]:
    match = build_empty_match(
        match_row.get("competition_name", "").strip(),
        match_row.get("season_name", "").strip(),
    )
    match["match_id"] = match_row.get("match_id", "").strip() or "pending-new-match"
    match["competition_name"] = match_row.get("competition_name", "").strip()
    match["season"] = match_row.get("season_name", "").strip()
    match["stage"] = match_row.get("stage", "").strip()
    match["round"] = parse_excel_optional_int(match_row.get("round", ""), 1)
    match["game_no"] = resolve_excel_game_no(match_row)
    raw_score_model = (
        ""
        if isinstance(scoring_rule_override, dict)
        else match_row.get("score_model", "").strip()
    )
    inherited_rule = (
        normalize_scoring_rule(scoring_rule_override)
        if isinstance(scoring_rule_override, dict)
        else resolve_scoring_rule_for_scope(
            load_validated_data(),
            str(match["competition_name"]),
            str(match["season"]),
        )
    )
    inherited_model = normalize_match_score_model(
        str(inherited_rule.get("score_model") or "standard")
    )
    requested_model = normalize_match_score_model(raw_score_model) if raw_score_model else inherited_model
    match["score_model"] = requested_model
    match["scoring_rule"] = (
        inherited_rule
        if requested_model == inherited_model
        else default_scoring_rule(requested_model)
    )
    match["exclude_from_team_scores"] = parse_truthy_excel_value(
        match_row.get("exclude_from_team_scores", "")
    )
    match["played_on"] = match_row.get("played_on", "").strip()
    match["group_label"] = match_row.get("group_label", "").strip()
    match["table_label"] = (
        match_row.get("room_label", "").strip()
        or match_row.get("table_label", "").strip()
    )
    match["format"] = match_row.get("format", "").strip()
    is_placeholder_match = match["format"] == "待补录"
    match["duration_minutes"] = parse_excel_optional_int(
        match_row.get("duration_minutes", ""),
        0 if is_placeholder_match else 60,
    )
    match["winning_camp"] = (
        match_row.get("winning_camp", "").strip() or ("draw" if is_placeholder_match else "")
    )
    match["mvp_player_id"] = ""
    match["svp_player_id"] = ""
    match["scapegoat_player_id"] = ""
    match["notes"] = match_row.get("notes", "").strip()
    participants = []
    for player_row in sorted(player_rows, key=lambda item: parse_excel_int(item.get("seat", ""), "seat")):
        score_breakdown = parse_excel_score_breakdown(
            player_row,
            match.get("scoring_rule"),
        )
        if uses_structured_score_model(match["score_model"]):
            points_earned = calculate_score_breakdown_total(
                {"score_breakdown": score_breakdown},
                match.get("scoring_rule"),
            )
        else:
            points_earned = parse_excel_float(player_row.get("points_earned", ""), "points_earned")
        participants.append(
            {
                "player_id": player_row.get("player_id", "").strip(),
                "player_name": (
                    player_row.get("player_name", "").strip()
                    or player_row.get("player_id", "").strip()
                ),
                "team_id": player_row.get("team_id", "").strip(),
                "team_name": (
                    player_row.get("team_name", "").strip()
                    or player_row.get("team_id", "").strip()
                ),
                "seat": parse_excel_int(player_row.get("seat", ""), "seat"),
                "role": player_row.get("role", "").strip(),
                "camp": player_row.get("camp", "").strip(),
                "result": player_row.get("result", "").strip(),
                "points_earned": points_earned,
                **score_breakdown,
                "score_breakdown": score_breakdown,
                "stance_result": player_row.get("stance_result", "").strip() or "none",
                "notes": player_row.get("notes", "").strip(),
            }
        )
    match["mvp_player_name"] = parse_excel_award_name(player_rows, "mvp_player_name", "MVP")
    match["svp_player_name"] = parse_excel_award_name(player_rows, "svp_player_name", "SVP")
    match["scapegoat_player_name"] = parse_excel_award_name(player_rows, "scapegoat_player_name", "背锅")
    match["players"] = participants
    normalize_excel_participant_results(match)
    return match


def build_matches_from_flat_excel_rows(
    rows: list[dict[str, str]],
    scoring_rule_override: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    grouped_rows: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        group_key = build_excel_match_group_key(row)
        grouped_rows.setdefault(group_key, []).append(row)

    matches: list[dict[str, object]] = []
    for grouped in grouped_rows.values():
        match_row = grouped[0]
        player_rows: list[dict[str, str]] = []
        for row in grouped:
            player_name = row.get("player_name", "").strip()
            team_name = row.get("team_name", "").strip()
            if not player_name and not team_name:
                continue
            player_row = {
                key: str(value or "").strip()
                for key, value in row.items()
            }
            player_row.update(
                {
                    "player_name": player_name,
                    "team_name": team_name,
                }
            )
            player_rows.append(player_row)
        matches.append(
            build_match_from_excel_rows(
                match_row,
                player_rows,
                scoring_rule_override=scoring_rule_override,
            )
        )
    return matches


def build_excel_match_group_key(row: dict[str, str]) -> str:
    competition_name = row.get("competition_name", "").strip()
    season_name = row.get("season_name", "").strip()
    played_on = row.get("played_on", "").strip()
    match_id = row.get("match_id", "").strip()
    if match_id:
        return match_id
    game_no = row.get("game_no", "").strip()
    if not competition_name or not season_name or not played_on or not game_no:
        raise ValueError(
            "records 工作表缺少归组字段。请至少填写 competition_name、season_name、played_on、game_no。"
        )
    stage = row.get("stage", "").strip()
    group_label = row.get("group_label", "").strip()
    room_label = row.get("room_label", "").strip() or row.get("table_label", "").strip()
    round_no = row.get("round", "").strip()
    return "|".join(
        [competition_name, season_name, played_on, game_no, stage, group_label, room_label, round_no]
    )


def build_match_from_wide_excel_row(
    row: dict[str, str],
    scoring_rule_override: dict[str, object] | None = None,
) -> dict[str, object]:
    match = build_empty_match(
        row.get("competition_name", "").strip(),
        row.get("season_name", "").strip(),
    )
    match["match_id"] = row.get("match_id", "").strip() or "pending-new-match"
    match["competition_name"] = row.get("competition_name", "").strip()
    match["season"] = row.get("season_name", "").strip()
    match["stage"] = row.get("stage", "").strip()
    match["round"] = parse_excel_optional_int(row.get("round", ""), 1)
    match["game_no"] = resolve_excel_game_no(row)
    raw_score_model = (
        ""
        if isinstance(scoring_rule_override, dict)
        else row.get("score_model", "").strip()
    )
    inherited_rule = (
        normalize_scoring_rule(scoring_rule_override)
        if isinstance(scoring_rule_override, dict)
        else resolve_scoring_rule_for_scope(
            load_validated_data(),
            str(match["competition_name"]),
            str(match["season"]),
        )
    )
    inherited_model = normalize_match_score_model(
        str(inherited_rule.get("score_model") or "standard")
    )
    requested_model = normalize_match_score_model(raw_score_model) if raw_score_model else inherited_model
    match["score_model"] = requested_model
    match["scoring_rule"] = (
        inherited_rule
        if requested_model == inherited_model
        else default_scoring_rule(requested_model)
    )
    match["exclude_from_team_scores"] = parse_truthy_excel_value(
        row.get("exclude_from_team_scores", "")
    )
    match["played_on"] = row.get("played_on", "").strip()
    match["group_label"] = row.get("group_label", "").strip()
    match["table_label"] = row.get("room_label", "").strip() or row.get("table_label", "").strip()
    match["format"] = row.get("format", "").strip()
    is_placeholder_match = match["format"] == "待补录"
    match["duration_minutes"] = parse_excel_optional_int(
        row.get("duration_minutes", ""),
        0 if is_placeholder_match else 60,
    )
    match["winning_camp"] = row.get("winning_camp", "").strip() or ("draw" if is_placeholder_match else "")
    match["mvp_player_id"] = ""
    match["svp_player_id"] = ""
    match["scapegoat_player_id"] = ""
    match["mvp_player_name"] = row.get("mvp_player_name", "").strip()
    match["svp_player_name"] = row.get("svp_player_name", "").strip()
    match["scapegoat_player_name"] = row.get("scapegoat_player_name", "").strip()
    match["notes"] = row.get("notes", "").strip()

    participants: list[dict[str, object]] = []
    for seat in range(1, 13):
        prefix = f"seat{seat}_"
        player_name = row.get(f"{prefix}player_name", "").strip()
        team_name = row.get(f"{prefix}team_name", "").strip()
        if not player_name and not team_name:
            continue
        score_breakdown = {
            field_name: parse_float_value(row.get(f"{prefix}{field_name}", "").strip() or "0", 0.0)
            for field_name, _ in MATCH_SCORE_COMPONENT_FIELDS
        }
        points_earned = (
            calculate_score_breakdown_total(
                {"score_breakdown": score_breakdown},
                match.get("scoring_rule"),
            )
            if uses_structured_score_model(match["score_model"])
            else parse_float_value(row.get(f"{prefix}points_earned", "").strip() or "0", 0.0)
        )
        participants.append(
            {
                "player_id": "",
                "player_name": player_name,
                "team_id": "",
                "team_name": team_name,
                "seat": seat,
                "role": row.get(f"{prefix}role", "").strip(),
                "camp": row.get(f"{prefix}camp", "").strip(),
                "result": row.get(f"{prefix}result", "").strip(),
                "points_earned": points_earned,
                **score_breakdown,
                "score_breakdown": score_breakdown,
                "stance_result": row.get(f"{prefix}stance_result", "").strip() or "none",
                "notes": row.get(f"{prefix}notes", "").strip(),
            }
        )
    match["players"] = participants
    normalize_excel_participant_results(match)
    return match


def describe_excel_import_match(match: dict[str, object]) -> str:
    competition_name = str(match.get("competition_name") or "").strip() or "未填写赛事"
    season_name = str(match.get("season") or match.get("season_name") or "").strip() or "未填写赛季"
    match_id = str(match.get("match_id") or "").strip()
    if match_id and match_id != "pending-new-match":
        return f"{competition_name} / {season_name} / {match_id}"
    played_on = str(match.get("played_on") or "").strip() or "未填写日期"
    return f"{competition_name} / {season_name} / {played_on}"


def find_existing_match_for_excel_import(
    matches: list[dict[str, object]],
    imported_match: dict[str, object],
) -> dict[str, object]:
    match_id = str(imported_match.get("match_id") or "").strip()
    if match_id and match_id != "pending-new-match":
        matched_by_id = get_match_by_id(matches, match_id)
        if matched_by_id is not None:
            return matched_by_id
    competition_name = str(imported_match.get("competition_name") or "").strip()
    season_name = str(imported_match.get("season") or imported_match.get("season_name") or "").strip()
    played_on = str(imported_match.get("played_on") or "").strip()
    game_no = imported_match.get("game_no")
    stage = str(imported_match.get("stage") or "").strip()
    group_label = str(imported_match.get("group_label") or "").strip()
    table_label = str(imported_match.get("table_label") or imported_match.get("room_label") or "").strip()
    round_no = int(imported_match.get("round") or 0)
    candidates = [
        match
        for match in matches
        if str(match.get("competition_name") or "").strip() == competition_name
        and str(match.get("season") or "").strip() == season_name
        and str(match.get("played_on") or "").strip() == played_on
        and int(match.get("game_no") or 0) == int(game_no or 0)
    ]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        narrowing_rules = [
            ("stage", stage, lambda match: str(match.get("stage") or "").strip()),
            ("group_label", group_label, lambda match: str(match.get("group_label") or "").strip()),
            ("table_label", table_label, lambda match: str(match.get("table_label") or "").strip()),
            ("round", str(round_no) if round_no > 0 else "", lambda match: str(int(match.get("round") or 0))),
        ]
        for _, expected_value, resolver in narrowing_rules:
            if len(candidates) <= 1 or not expected_value:
                continue
            narrowed = [match for match in candidates if resolver(match) == expected_value]
            if len(narrowed) == 1:
                return narrowed[0]
            if narrowed:
                candidates = narrowed
    if not candidates:
        raise ValueError("未找到已预创建的比赛，请先批量创建赛程。")
    candidate_labels = []
    for match in candidates[:3]:
        candidate_labels.append(
            " / ".join(
                [
                    str(match.get("stage") or "").strip() or "未填赛段",
                    str(match.get("table_label") or "").strip() or "未填房间",
                ]
            )
        )
    hint = "；".join(candidate_labels)
    if hint:
        raise ValueError(
            "找到了多场同日期比赛，请在 Excel 中补充比赛编号、赛段、房间或分组后重试。"
            f" 当前候选：{hint}"
        )
    raise ValueError("找到了多场同日期比赛，请优先填写比赛编号后重试。")


def merge_excel_import_match(
    existing_match: dict[str, object],
    imported_match: dict[str, object],
) -> dict[str, object]:
    merged_match = dict(existing_match)
    for field in (
        "group_label",
        "score_model",
        "exclude_from_team_scores",
        "table_label",
        "format",
        "winning_camp",
        "mvp_player_name",
        "svp_player_name",
        "scapegoat_player_name",
        "notes",
    ):
        if field == "exclude_from_team_scores":
            if imported_match.get(field):
                merged_match[field] = True
            else:
                merged_match.setdefault(field, False)
            continue
        value = str(imported_match.get(field) or "").strip()
        if value:
            merged_match[field] = value
    imported_duration = imported_match.get("duration_minutes")
    if isinstance(imported_duration, int) and imported_duration > 0:
        merged_match["duration_minutes"] = imported_duration
    imported_players = imported_match.get("players")
    if isinstance(imported_players, list) and imported_players:
        merged_match["players"] = imported_players
        imported_rule = imported_match.get("scoring_rule")
        if isinstance(imported_rule, dict) and imported_rule:
            merged_match["scoring_rule"] = imported_rule
            merged_match["score_model"] = str(
                imported_rule.get("score_model")
                or imported_match.get("score_model")
                or merged_match.get("score_model")
                or "standard"
            )
    merged_match["match_id"] = existing_match["match_id"]
    merged_match["competition_name"] = existing_match["competition_name"]
    merged_match["season"] = existing_match["season"]
    merged_match["stage"] = existing_match["stage"]
    merged_match["round"] = existing_match["round"]
    merged_match["game_no"] = existing_match["game_no"]
    merged_match["played_on"] = existing_match["played_on"]
    merged_match["mvp_player_id"] = ""
    merged_match["svp_player_id"] = ""
    merged_match["scapegoat_player_id"] = ""
    return merged_match


def import_matches_from_excel(
    ctx: RequestContext,
    data: dict[str, object],
    upload: UploadedFile,
    group_label_override: str = "",
) -> tuple[list[dict[str, object]] | None, str]:
    try:
        template_metadata = read_scoring_template_metadata(upload)
        scoring_rule_override = (
            template_metadata.get("scoring_rule")
            if isinstance(template_metadata, dict)
            else None
        )
        flat_rows = read_first_available_sheet_rows(upload, ["records", "比赛记录", "单局成绩表"])
        if flat_rows:
            hydrate_excel_rows_from_match_ids(
                flat_rows,
                data,
                require_match_id=template_metadata is not None,
            )
            validate_template_metadata_scope(flat_rows, template_metadata)
            if any(any(key.startswith("seat1_") for key in row.keys()) for row in flat_rows):
                parsed_matches = [
                    build_match_from_wide_excel_row(
                        row,
                        scoring_rule_override=scoring_rule_override,
                    )
                    for row in flat_rows
                ]
            else:
                parsed_matches = build_matches_from_flat_excel_rows(
                    flat_rows,
                    scoring_rule_override=scoring_rule_override,
                )
            match_rows = []
            player_rows = []
        else:
            parsed_matches = []
            match_rows = read_excel_sheet_rows(upload, "matches")
            player_rows = read_excel_sheet_rows(upload, "players")
            hydrate_excel_rows_from_match_ids(
                match_rows,
                data,
                require_match_id=template_metadata is not None,
            )
            validate_template_metadata_scope(match_rows, template_metadata)
    except Exception as exc:
        return None, f"解析 Excel 失败：{exc}"
    if not parsed_matches and not match_rows:
        return None, "Excel 中没有读取到可导入的数据，请检查 records 工作表。"

    players_by_key: dict[str, list[dict[str, str]]] = {}
    for row in player_rows:
        match_key = row.get("match_key", "").strip()
        if match_key:
            players_by_key.setdefault(match_key, []).append(row)

    next_matches = [dict(match) for match in data["matches"]]
    existing_by_id = {match["match_id"]: match for match in next_matches}
    created_count = 0
    updated_count = 0

    source_matches = parsed_matches or []
    parsed_records_import = bool(parsed_matches)
    if not source_matches:
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
            source_matches.append(
                build_match_from_excel_rows(
                    row,
                    players_by_key.get(match_key, []),
                    scoring_rule_override=scoring_rule_override,
                )
            )

    for current_match in source_matches:
        if group_label_override:
            current_match["group_label"] = group_label_override
        match_key = describe_excel_import_match(current_match)
        import_mode = "update" if str(current_match.get("match_id") or "").strip() in existing_by_id else "create"
        match_id = str(current_match.get("match_id") or "").strip()
        if parsed_records_import:
            try:
                existing_match = find_existing_match_for_excel_import(next_matches, current_match)
            except ValueError as exc:
                return None, f"{match_key} 导入失败：{exc}"
            current_match = merge_excel_import_match(existing_match, current_match)
            import_mode = "update"
            match_id = existing_match["match_id"]
        competition_name = str(current_match["competition_name"] or "").strip()
        season_name = str(current_match["season"] or "").strip()
        if not can_manage_matches(ctx.current_user, data, competition_name):
            return None, f"你没有权限导入 {competition_name} 下的比赛。"
        competition_error = validate_match_competition_selection(data, competition_name)
        if competition_error:
            return None, competition_error
        season_error = validate_match_season_selection(
            data,
            competition_name,
            season_name,
            include_non_ongoing=True,
        )
        if season_error:
            return None, season_error
        resolution_errors = resolve_match_entities(data, [current_match])
        if resolution_errors:
            return None, f"{match_key} 导入失败：{resolution_errors[0]}"
        award_error = validate_match_awards(current_match)
        if award_error:
            return None, f"{match_key} 导入失败：{award_error}"

        if import_mode == "update":
            for index, existing_match in enumerate(next_matches):
                if existing_match["match_id"] == match_id:
                    next_matches[index] = current_match
                    existing_by_id[match_id] = current_match
                    break
            updated_count += 1
        else:
            next_matches.append(current_match)
            created_count += 1

    if parsed_records_import:
        summary = f"Excel 导入完成：更新 {updated_count} 场已预创建比赛。"
        return next_matches, summary
    summary = f"Excel 导入完成：新增 {created_count} 场，更新 {updated_count} 场。"
    return next_matches, summary


def build_player_dimension_stats_from_rows(
    data: dict[str, object],
    competition_name: str,
    season_name: str,
    rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    parsed_rows: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=2):
        player_name = get_excel_row_value(row, "选手姓名", "player_name")
        team_name = get_excel_row_value(row, "所属战队", "战队", "team_name")
        played_on = normalize_excel_serial_date(
            get_excel_row_value(row, "比赛日期", "played_on"),
            f"单日选手个人维度数据 第 {index} 行的比赛日期",
        )
        seat = parse_excel_optional_int(get_excel_row_value(row, "座位号", "seat"), 0)
        if not player_name:
            raise ValueError(f"单日选手个人维度数据 第 {index} 行缺少选手姓名。")
        team = None
        if team_name:
            team = legacy.find_team_by_name_in_scope(
                data,
                competition_name,
                season_name,
                team_name,
            )
            if not team:
                raise ValueError(f"单日选手个人维度数据 第 {index} 行未找到战队：{team_name}。")
        player = None
        if not team_name:
            matching_player_ids = {
                str(participant.get("player_id") or "").strip()
                for match in data.get("matches", [])
                if get_match_competition_name(match) == competition_name
                and str(match.get("season") or "").strip() == season_name
                for participant in match.get("players", [])
                if str(participant.get("player_name") or "").strip() == player_name
                and not str(participant.get("team_id") or "").strip()
                and str(participant.get("player_id") or "").strip()
            }
            if len(matching_player_ids) == 1:
                matched_player_id = next(iter(matching_player_ids))
                player = next(
                    (
                        item
                        for item in data.get("players", [])
                        if str(item.get("player_id") or "").strip() == matched_player_id
                    ),
                    None,
                )
        if not player:
            player = legacy.find_player_by_name_in_scope(
                data,
                competition_name,
                season_name,
                player_name,
                team_name,
            )
        if not player:
            raise ValueError(f"单日选手个人维度数据 第 {index} 行未找到选手：{player_name}。")
        parsed_row: dict[str, object] = {
            "competition_name": competition_name,
            "season_name": season_name,
            "played_on": played_on,
            "player_id": player["player_id"],
            "team_id": team["team_id"] if team else "",
            "seat": seat,
        }
        for header_name, field_name in PLAYER_DIMENSION_FIELD_MAP.items():
            parsed_row[field_name] = parse_excel_metric_value(row.get(header_name, ""))
        parsed_rows.append(parsed_row)
    return parsed_rows


def build_team_dimension_stats_from_rows(
    data: dict[str, object],
    competition_name: str,
    season_name: str,
    rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    parsed_rows: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=2):
        team_name = get_excel_row_value(row, "战队", "所属战队", "team_name")
        if not team_name:
            continue
        played_on = normalize_excel_serial_date(
            get_excel_row_value(row, "比赛日期", "played_on"),
            f"单日选手战队维度数据 第 {index} 行的比赛日期",
        )
        team = legacy.find_team_by_name_in_scope(data, competition_name, season_name, team_name)
        if not team:
            raise ValueError(f"单日选手战队维度数据 第 {index} 行未找到战队：{team_name}。")
        parsed_row: dict[str, object] = {
            "competition_name": competition_name,
            "season_name": season_name,
            "played_on": played_on,
            "team_id": team["team_id"],
            "seat": parse_excel_optional_int(get_excel_row_value(row, "座位号", "seat"), 0),
        }
        for header_name, field_name in TEAM_DIMENSION_FIELD_MAP.items():
            parsed_row[field_name] = parse_excel_metric_value(row.get(header_name, ""))
        parsed_rows.append(parsed_row)
    return parsed_rows


def dedupe_dimension_rows(
    rows: list[dict[str, object]],
    key_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    deduped_rows: dict[tuple[object, ...], dict[str, object]] = {}
    for row in rows:
        key = tuple(
            int(row.get(field_name) or 0) if field_name == "seat" else row.get(field_name)
            for field_name in key_fields
        )
        deduped_rows[key] = row
    return list(deduped_rows.values())


def import_dimension_stats_from_excel(
    ctx: RequestContext,
    data: dict[str, object],
    upload: UploadedFile,
    competition_name: str,
    season_name: str,
) -> tuple[list[dict[str, object]] | None, list[dict[str, object]] | None, str]:
    try:
        player_sheet_rows = read_optional_sheet_rows(upload, PLAYER_DIMENSION_SHEET_NAMES)
        team_sheet_rows = read_optional_sheet_rows(upload, TEAM_DIMENSION_SHEET_NAMES)
    except Exception as exc:
        return None, None, f"解析 Excel 失败：{exc}"
    if not player_sheet_rows and not team_sheet_rows:
        return None, None, "Excel 中没有找到可导入的维度数据工作表。"
    if not can_manage_matches(ctx.current_user, data, competition_name):
        return None, None, f"你没有权限导入 {competition_name} 下的维度数据。"
    competition_error = validate_match_competition_selection(data, competition_name)
    if competition_error:
        return None, None, competition_error
    season_error = validate_match_season_selection(
        data,
        competition_name,
        season_name,
        include_non_ongoing=True,
    )
    if season_error:
        return None, None, season_error
    try:
        imported_player_rows = build_player_dimension_stats_from_rows(
            data,
            competition_name,
            season_name,
            player_sheet_rows,
        )
        imported_team_rows = build_team_dimension_stats_from_rows(
            data,
            competition_name,
            season_name,
            team_sheet_rows,
        )
    except ValueError as exc:
        return None, None, str(exc)

    next_player_rows = dedupe_dimension_rows(
        imported_player_rows,
        ("competition_name", "season_name", "played_on", "player_id"),
    )
    next_team_rows = dedupe_dimension_rows(
        imported_team_rows,
        ("competition_name", "season_name", "played_on", "team_id", "seat"),
    )
    summary = (
        f"维度数据导入完成：选手 {len(imported_player_rows)} 条，战队 {len(imported_team_rows)} 条。"
        " 已按赛事、赛季、日期和主键逐条新增/更新，未删除本 Excel 之外的旧维度数据。"
    )
    return next_player_rows, next_team_rows, summary


def is_external_logo_url(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("http://") or normalized.startswith("https://")


def normalize_logo_reference(value: str) -> str:
    return str(value or "").strip()


def import_team_logos_from_excel(
    ctx: RequestContext,
    data: dict[str, object],
    upload: UploadedFile,
    competition_name: str,
    season_name: str,
) -> tuple[list[dict[str, object]] | None, str]:
    try:
        rows = read_first_available_sheet_rows(upload, TEAM_LOGO_SHEET_NAMES)
        embedded_images: dict[tuple[int, int], tuple[str, bytes]] = {}
        for sheet_name in TEAM_LOGO_SHEET_NAMES:
            embedded_images = read_excel_sheet_embedded_images(upload, sheet_name)
            if embedded_images:
                break
    except Exception as exc:
        return None, f"解析 Excel 失败：{exc}"
    if not rows:
        return None, "Excel 中没有找到可导入的战队图标数据工作表。"
    if not can_manage_matches(ctx.current_user, data, competition_name):
        return None, f"你没有权限导入 {competition_name} 下的战队图标。"
    competition_error = validate_match_competition_selection(data, competition_name)
    if competition_error:
        return None, competition_error
    season_error = validate_match_season_selection(
        data,
        competition_name,
        season_name,
        include_non_ongoing=True,
    )
    if season_error:
        return None, season_error

    created_count = 0
    updated_count = 0
    for index, row in enumerate(rows, start=2):
        team_name = get_excel_row_value(row, "team_name")
        if not team_name:
            return None, f"战队图标数据第 {index} 行缺少战队名称。"
        team = legacy.find_team_by_name_in_scope(data, competition_name, season_name, team_name)
        if not team:
            team = build_placeholder_team(
                build_team_serial(data, competition_name, season_name, data["teams"]),
                team_name,
                competition_name,
                season_name,
            )
            data["teams"].append(team)
            created_count += 1
        else:
            updated_count += 1
        embedded_logo = find_embedded_image_for_row(embedded_images, index, 2)
        if embedded_logo:
            original_name, image_bytes = embedded_logo
            try:
                team["logo"] = save_embedded_team_logo(team["team_id"], original_name, image_bytes)
            except ValueError as exc:
                return None, f"战队图标数据第 {index} 行图片保存失败：{exc}"
        else:
            logo_value = normalize_logo_reference(get_excel_row_value(row, "logo"))
            if not logo_value:
                return None, f"战队图标数据第 {index} 行缺少战队logo。"
            if not is_external_logo_url(logo_value):
                candidate = safe_asset_path(logo_value)
                if candidate is None:
                    return None, (
                        f"战队图标数据第 {index} 行的战队logo 必须是 Excel 里插入的图片、`assets/` 下的站内路径，"
                        "或 http/https 外链地址。"
                    )
                if not candidate.is_file():
                    return None, f"战队图标数据第 {index} 行的图标文件不存在：{logo_value}"
            team["logo"] = logo_value
        if not str(team.get("short_name") or "").strip():
            team["short_name"] = team_name.strip()[:12] or team["team_id"]

    return data["teams"], f"战队图标导入完成：新建 {created_count} 支，更新 {updated_count} 支。"


def find_players_by_name_in_scope(
    data: dict[str, object],
    competition_name: str,
    season_name: str,
    player_name: str,
) -> list[dict[str, object]]:
    normalized_player_name = player_name.strip()
    if not normalized_player_name:
        return []
    team_lookup = {
        str(team.get("team_id") or "").strip(): team
        for team in data.get("teams", [])
    }
    matched_players: list[dict[str, object]] = []
    for player in data.get("players", []):
        if str(player.get("display_name") or "").strip() != normalized_player_name:
            continue
        team = team_lookup.get(str(player.get("team_id") or "").strip())
        if not team:
            continue
        if (
            str(team.get("competition_name") or "").strip() != competition_name.strip()
            or str(team.get("season_name") or "").strip() != season_name.strip()
        ):
            continue
        matched_players.append(player)
    return matched_players


def list_match_record_player_ids(
    data: dict[str, object],
    competition_name: str,
    season_name: str,
) -> set[str]:
    player_ids: set[str] = set()
    for match in data.get("matches", []):
        if (
            str(match.get("competition_name") or "").strip() != competition_name.strip()
            or str(match.get("season") or "").strip() != season_name.strip()
        ):
            continue
        for participant in match.get("players", []):
            if not isinstance(participant, dict):
                continue
            player_id = str(participant.get("player_id") or "").strip()
            if player_id:
                player_ids.add(player_id)
    return player_ids


def build_match_record_player_counts(
    data: dict[str, object],
    competition_name: str,
    season_name: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for match in data.get("matches", []):
        if (
            str(match.get("competition_name") or "").strip() != competition_name.strip()
            or str(match.get("season") or "").strip() != season_name.strip()
        ):
            continue
        for participant in match.get("players", []):
            if not isinstance(participant, dict):
                continue
            player_id = str(participant.get("player_id") or "").strip()
            if player_id:
                counts[player_id] = counts.get(player_id, 0) + 1
    return counts


def build_season_player_photo_roster_csv(
    data: dict[str, object],
    competition_name: str,
    season_name: str,
) -> bytes:
    appearance_counts = build_match_record_player_counts(data, competition_name, season_name)
    team_lookup = {
        str(team.get("team_id") or "").strip(): team
        for team in data.get("teams", [])
    }
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "player_id",
            "display_name",
            "team_id",
            "team_name",
            "appearances",
            "suggested_photo_filename",
        ],
    )
    writer.writeheader()
    for player in sorted(
        data.get("players", []),
        key=lambda item: (
            str(item.get("display_name") or ""),
            str(item.get("player_id") or ""),
        ),
    ):
        player_id = str(player.get("player_id") or "").strip()
        if player_id not in appearance_counts:
            continue
        team = team_lookup.get(str(player.get("team_id") or "").strip(), {})
        writer.writerow(
            {
                "player_id": player_id,
                "display_name": str(player.get("display_name") or "").strip(),
                "team_id": str(player.get("team_id") or "").strip(),
                "team_name": str(team.get("name") or "").strip(),
                "appearances": appearance_counts[player_id],
                "suggested_photo_filename": f"{player_id}.png",
            }
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def archive_photo_player_id(filename: str) -> str:
    name = PurePosixPath(filename).name.strip()
    if not name or name.startswith("."):
        return ""
    extension = PurePosixPath(name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return ""
    return PurePosixPath(name).stem.strip()


def save_pending_player_photo_import(filename: str, image_bytes: bytes, batch_id: str) -> str:
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(f"不支持的图片格式：{filename}")
    signature_error = legacy.validate_image_bytes(filename, image_bytes)
    if signature_error:
        raise ValueError(signature_error)
    PLAYER_PHOTO_PENDING_DIR.mkdir(parents=True, exist_ok=True)
    batch_dir = PLAYER_PHOTO_PENDING_DIR / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    target = batch_dir / f"{secrets.token_hex(8)}{extension}"
    target.write_bytes(image_bytes)
    return str(target.relative_to(ROOT_DIR)).replace("\\", "/")


def resolve_pending_player_photo_path(relative_path: str) -> Path | None:
    text = str(relative_path or "").strip().lstrip("/")
    if not text:
        return None
    candidate = (ROOT_DIR / text).resolve()
    try:
        candidate.relative_to(PLAYER_PHOTO_PENDING_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def pending_photo_asset_url(relative_path: str) -> str:
    return "/" + str(relative_path or "").strip().lstrip("/")


def build_match_record_player_context(
    data: dict[str, object],
    competition_name: str,
    season_name: str,
) -> tuple[dict[str, dict[str, object]], dict[str, list[dict[str, object]]], dict[str, dict[str, object]]]:
    match_record_player_ids = list_match_record_player_ids(data, competition_name, season_name)
    team_lookup = {
        str(team.get("team_id") or "").strip(): team
        for team in data.get("teams", [])
    }
    player_by_id = {
        str(player.get("player_id") or "").strip(): player
        for player in data.get("players", [])
        if str(player.get("player_id") or "").strip() in match_record_player_ids
    }
    players_by_name: dict[str, list[dict[str, object]]] = {}
    for player in player_by_id.values():
        name = str(player.get("display_name") or "").strip()
        if name:
            players_by_name.setdefault(name, []).append(player)
    return player_by_id, players_by_name, team_lookup


def read_player_photo_zip_items(upload: UploadedFile) -> tuple[list[dict[str, object]] | None, str]:
    batch_id = secrets.token_hex(8)
    try:
        with ZipFile(BytesIO(upload.data)) as archive:
            entries = [
                info
                for info in archive.infolist()
                if not info.is_dir() and not info.filename.startswith("__MACOSX/")
            ]
            if not entries:
                return None, "zip 压缩包中没有找到可导入的头像图片。"
            if len(entries) > MAX_ZIP_IMAGE_COUNT:
                return None, f"zip 压缩包内文件不能超过 {MAX_ZIP_IMAGE_COUNT} 个，请拆分后再上传。"

            items: list[dict[str, object]] = []
            ignored_count = 0
            for info in entries:
                player_id = archive_photo_player_id(info.filename)
                if not player_id:
                    ignored_count += 1
                    continue
                if info.file_size > MAX_UPLOAD_BYTES:
                    return None, f"{PurePosixPath(info.filename).name} 超过 5 MB，未导入。"
                try:
                    image_bytes = archive.read(info)
                except Exception as exc:
                    return None, f"读取 {PurePosixPath(info.filename).name} 失败：{exc}"
                if not image_bytes:
                    ignored_count += 1
                    continue
                filename = PurePosixPath(info.filename).name
                try:
                    pending_path = save_pending_player_photo_import(filename, image_bytes, batch_id)
                except ValueError as exc:
                    return None, f"{filename} 图片校验失败：{exc}"
                items.append(
                    {
                        "token": str(len(items)),
                        "filename": filename,
                        "stem": player_id,
                        "pending_path": pending_path,
                        "data_url": pending_photo_asset_url(pending_path),
                    }
                )
    except BadZipFile:
        return None, "zip 压缩包无法解析，请确认文件没有损坏。"
    except Exception as exc:
        return None, f"解析 zip 压缩包失败：{exc}"

    if not items:
        return None, f"zip 压缩包中没有找到可导入的头像图片，已忽略 {ignored_count} 个文件。"
    return items, (f"忽略 {ignored_count} 个非图片文件。" if ignored_count else "")


def resolve_zip_photo_assignments(
    items: list[dict[str, object]],
    player_by_id: dict[str, dict[str, object]],
    players_by_name: dict[str, list[dict[str, object]]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    matched_items: list[dict[str, object]] = []
    conflicts: list[dict[str, object]] = []
    unmatched_count = 0
    for item in items:
        stem = str(item.get("stem") or "").strip()
        player = player_by_id.get(stem)
        if player:
            matched_items.append({**item, "player_id": str(player.get("player_id") or "")})
            continue
        name_candidates = players_by_name.get(stem, [])
        if len(name_candidates) == 1:
            matched_items.append(
                {**item, "player_id": str(name_candidates[0].get("player_id") or "")}
            )
        elif len(name_candidates) > 1:
            conflicts.append({**item, "kind": "ambiguous_player", "candidates": name_candidates})
        else:
            unmatched_count += 1

    by_player_id: dict[str, list[dict[str, object]]] = {}
    for item in matched_items:
        by_player_id.setdefault(str(item["player_id"]), []).append(item)

    auto_assignments: list[dict[str, object]] = []
    for player_id, player_items in by_player_id.items():
        if len(player_items) == 1:
            auto_assignments.append(player_items[0])
        else:
            conflicts.append(
                {
                    "kind": "multiple_photos",
                    "player_id": player_id,
                    "items": player_items,
                }
            )
    return auto_assignments, conflicts, unmatched_count


def apply_player_photo_assignments(
    data: dict[str, object],
    assignments: list[dict[str, str]],
) -> tuple[int, str]:
    player_by_id = {
        str(player.get("player_id") or "").strip(): player
        for player in data.get("players", [])
        if str(player.get("player_id") or "").strip()
    }
    updated_count = 0
    for assignment in assignments:
        player_id = str(assignment.get("player_id") or "").strip()
        filename = str(assignment.get("filename") or "").strip()
        pending_path = str(assignment.get("pending_path") or "").strip()
        player = player_by_id.get(player_id)
        source_path = resolve_pending_player_photo_path(pending_path)
        if not player or not filename or source_path is None:
            continue
        try:
            image_bytes = source_path.read_bytes()
            player["photo"] = save_embedded_player_photo(player_id, filename, image_bytes)
            source_path.unlink(missing_ok=True)
        except Exception as exc:
            return updated_count, f"{filename} 图片保存失败：{exc}"
        updated_count += 1
    return updated_count, ""


def parse_manual_player_photo_assignments(
    form: dict[str, list[str]],
    player_by_id: dict[str, dict[str, object]],
) -> list[dict[str, str]]:
    try:
        photo_count = int(form_value(form, "photo_count", "0") or "0")
        auto_count = int(form_value(form, "auto_count", "0") or "0")
    except ValueError:
        return []
    item_by_token: dict[str, dict[str, str]] = {}
    for index in range(photo_count):
        token = form_value(form, f"photo_token_{index}").strip()
        if not token:
            token = str(index)
        filename = form_value(form, f"photo_filename_{token}").strip()
        pending_path = form_value(form, f"photo_pending_path_{token}").strip()
        if filename and pending_path:
            item_by_token[token] = {"filename": filename, "pending_path": pending_path}

    assignments_by_player_id: dict[str, dict[str, str]] = {}
    for index in range(auto_count):
        token = form_value(form, f"auto_token_{index}").strip()
        player_id = form_value(form, f"auto_player_id_{index}").strip()
        item = item_by_token.get(token)
        if item and player_id in player_by_id:
            assignments_by_player_id[player_id] = {"player_id": player_id, **item}

    for key, values in form.items():
        if key.startswith("manual_player_photo_"):
            player_id = key.removeprefix("manual_player_photo_").strip()
            token = str(values[0] if values else "").strip()
            item = item_by_token.get(token)
            if item and player_id in player_by_id:
                assignments_by_player_id[player_id] = {"player_id": player_id, **item}
        elif key.startswith("manual_photo_player_"):
            token = key.removeprefix("manual_photo_player_").strip()
            player_id = str(values[0] if values else "").strip()
            item = item_by_token.get(token)
            if item and player_id in player_by_id:
                assignments_by_player_id[player_id] = {"player_id": player_id, **item}
    return list(assignments_by_player_id.values())


def build_player_photo_manual_select_page(
    ctx: RequestContext,
    competition_name: str,
    season_name: str,
    items: list[dict[str, object]],
    auto_assignments: list[dict[str, object]],
    conflicts: list[dict[str, object]],
    unmatched_count: int,
    ignored_message: str,
    player_by_id: dict[str, dict[str, object]],
    team_lookup: dict[str, dict[str, object]],
) -> str:
    item_inputs = [f'<input type="hidden" name="photo_count" value="{len(items)}">']
    for item in items:
        token = escape(str(item["token"]))
        item_inputs.append(
            f'<input type="hidden" name="photo_token_{token}" value="{token}">'
            f'<input type="hidden" name="photo_filename_{token}" value="{escape(str(item["filename"]))}">'
            f'<input type="hidden" name="photo_pending_path_{token}" value="{escape(str(item["pending_path"]))}">'
        )
    auto_inputs = [f'<input type="hidden" name="auto_count" value="{len(auto_assignments)}">']
    for index, item in enumerate(auto_assignments):
        auto_inputs.append(
            f'<input type="hidden" name="auto_token_{index}" value="{escape(str(item["token"]))}">'
            f'<input type="hidden" name="auto_player_id_{index}" value="{escape(str(item["player_id"]))}">'
        )

    sections: list[str] = []
    for index, conflict in enumerate(conflicts):
        if conflict.get("kind") == "multiple_photos":
            player_id = str(conflict.get("player_id") or "")
            player = player_by_id.get(player_id, {})
            team = team_lookup.get(str(player.get("team_id") or "").strip(), {})
            player_label = (
                f"{player.get('display_name') or player_id}"
                f" · {team.get('name') or team.get('team_name') or '未分队'} · {player_id}"
            )
            radio_cards = []
            for item in conflict.get("items", []):
                token = str(item["token"])
                radio_cards.append(
                    f"""
                    <label class="border rounded p-3 d-flex flex-column gap-2">
                      <input class="form-check-input" type="radio" name="manual_player_photo_{escape(player_id)}" value="{escape(token)}" required>
                      <img src="{escape(str(item['data_url']))}" alt="{escape(str(item['filename']))}" style="width:96px;height:96px;object-fit:cover;border-radius:8px;">
                      <span class="small">{escape(str(item['filename']))}</span>
                    </label>
                    """
                )
            sections.append(
                f"""
                <div class="border rounded p-3 mb-3">
                  <h3 class="h6 mb-3">{escape(player_label)} 匹配到多张图片，请选择一张</h3>
                  <div class="d-flex flex-wrap gap-3">{''.join(radio_cards)}</div>
                </div>
                """
            )
        else:
            item = conflict
            token = str(item["token"])
            option_html = ['<option value="">跳过这张图片</option>']
            for player in item.get("candidates", []):
                player_id = str(player.get("player_id") or "")
                team = team_lookup.get(str(player.get("team_id") or "").strip(), {})
                label = f"{player.get('display_name') or player_id} · {team.get('name') or team.get('team_name') or '未分队'} · {player_id}"
                option_html.append(f'<option value="{escape(player_id)}">{escape(label)}</option>')
            sections.append(
                f"""
                <div class="border rounded p-3 mb-3">
                  <h3 class="h6 mb-3">`{escape(str(item['filename']))}` 匹配到多个同名队员，请选择目标队员</h3>
                  <div class="d-flex flex-column flex-md-row gap-3 align-items-md-center">
                    <img src="{escape(str(item['data_url']))}" alt="{escape(str(item['filename']))}" style="width:96px;height:96px;object-fit:cover;border-radius:8px;">
                    <select class="form-select" name="manual_photo_player_{escape(token)}">
                      {''.join(option_html)}
                    </select>
                  </div>
                </div>
                """
            )

    body = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h1 class="section-title mb-2">手动确认队员头像</h1>
      <p class="section-copy mb-4">系统已自动识别 {len(auto_assignments)} 张图片，另有 {len(conflicts)} 处需要你确认；未匹配跳过 {unmatched_count} 个。{escape(ignored_message)}</p>
      <form method="post" action="/matches/new">
        <input type="hidden" name="action" value="confirm_player_photo_zip">
        <input type="hidden" name="competition_name" value="{escape(competition_name)}">
        <input type="hidden" name="season" value="{escape(season_name)}">
        {''.join(item_inputs)}
        {''.join(auto_inputs)}
        {''.join(sections)}
        <div class="d-flex flex-wrap gap-2 mt-4">
          <button type="submit" class="btn btn-dark">确认并导入头像</button>
          <a class="btn btn-outline-dark" href="{escape(build_match_management_path(ctx, competition_name, season_name))}">取消</a>
        </div>
      </form>
    </section>
    """
    return layout("手动确认队员头像", body, ctx)


def import_player_photos_from_zip(
    ctx: RequestContext,
    data: dict[str, object],
    upload: UploadedFile,
    competition_name: str,
    season_name: str,
) -> tuple[list[dict[str, object]] | None, str]:
    if not can_manage_matches(ctx.current_user, data, competition_name):
        return None, f"你没有权限导入 {competition_name} 下的队员头像。"
    competition_error = validate_match_competition_selection(data, competition_name)
    if competition_error:
        return None, competition_error
    season_error = validate_match_season_selection(
        data,
        competition_name,
        season_name,
        include_non_ongoing=True,
    )
    if season_error:
        return None, season_error

    player_by_id, players_by_name, _team_lookup = build_match_record_player_context(
        data,
        competition_name,
        season_name,
    )
    if not player_by_id:
        return None, "当前赛事赛季还没有可匹配的比赛记录队员。"
    items, ignored_message = read_player_photo_zip_items(upload)
    if items is None:
        return None, ignored_message
    auto_assignments, conflicts, unmatched_count = resolve_zip_photo_assignments(
        items,
        player_by_id,
        players_by_name,
    )
    if conflicts:
        return None, "manual-selection-required"
    updated_count, save_error = apply_player_photo_assignments(data, [
        {
            "player_id": str(item["player_id"]),
            "filename": str(item["filename"]),
            "pending_path": str(item["pending_path"]),
        }
        for item in auto_assignments
    ])
    if save_error:
        return None, save_error
    return (
        data["players"],
        f"队员头像导入完成：更新 {updated_count} 位，未匹配跳过 {unmatched_count} 个。{ignored_message}",
    )




def import_player_photos_from_excel(
    ctx: RequestContext,
    data: dict[str, object],
    upload: UploadedFile,
    competition_name: str,
    season_name: str,
) -> tuple[list[dict[str, object]] | None, str]:
    try:
        rows = read_first_available_sheet_rows(upload, PLAYER_PHOTO_SHEET_NAMES)
        embedded_images: dict[tuple[int, int], tuple[str, bytes]] = {}
        for sheet_name in PLAYER_PHOTO_SHEET_NAMES:
            embedded_images = read_excel_sheet_embedded_images(upload, sheet_name)
            if embedded_images:
                break
    except Exception as exc:
        return None, f"解析 Excel 失败：{exc}"
    if not rows:
        return None, "Excel 中没有找到可导入的队员头像数据工作表。"
    if not can_manage_matches(ctx.current_user, data, competition_name):
        return None, f"你没有权限导入 {competition_name} 下的队员头像。"
    competition_error = validate_match_competition_selection(data, competition_name)
    if competition_error:
        return None, competition_error
    season_error = validate_match_season_selection(
        data,
        competition_name,
        season_name,
        include_non_ongoing=True,
    )
    if season_error:
        return None, season_error

    updated_count = 0
    for index, row in enumerate(rows, start=2):
        player_name = get_excel_row_value(row, "player_name")
        if not player_name:
            return None, f"队员头像数据第 {index} 行缺少选手姓名。"
        matched_players = find_players_by_name_in_scope(data, competition_name, season_name, player_name)
        if not matched_players:
            return None, f"队员头像数据第 {index} 行没有匹配到赛季队员：{player_name}"
        if len(matched_players) > 1:
            return None, f"队员头像数据第 {index} 行命中了多个同名赛季队员：{player_name}"
        player = matched_players[0]
        embedded_photo = find_embedded_image_for_row(embedded_images, index, 2)
        if embedded_photo:
            original_name, image_bytes = embedded_photo
            try:
                player["photo"] = save_embedded_player_photo(
                    str(player.get("player_id") or ""),
                    original_name,
                    image_bytes,
                )
            except ValueError as exc:
                return None, f"队员头像数据第 {index} 行图片保存失败：{exc}"
        else:
            photo_value = normalize_logo_reference(get_excel_row_value(row, "photo"))
            if not photo_value:
                return None, f"队员头像数据第 {index} 行缺少选手头像。"
            if not is_external_logo_url(photo_value):
                candidate = safe_asset_path(photo_value)
                if candidate is None:
                    return None, (
                        f"队员头像数据第 {index} 行的选手头像必须是 Excel 里插入的图片、`assets/` 下的站内路径，"
                        "或 http/https 外链地址。"
                    )
                if not candidate.is_file():
                    return None, f"队员头像数据第 {index} 行的头像文件不存在：{photo_value}"
            player["photo"] = photo_value
        updated_count += 1
    return data["players"], f"队员头像导入完成：更新 {updated_count} 位。"


def batch_create_matches(
    competition_name: str,
    season_name: str,
    stage: str,
    start_date: str,
    end_date: str,
    round_start: int,
    matches_per_day: int,
    room_label: str,
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
    if not room_label.strip():
        raise ValueError("请填写房间。")

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
                    "",
                    room_label.strip(),
                )
            )
        current_dt += timedelta(days=1)
        round_no += 1
    return matches


def build_match_competition_field(
    current_competition_name: str,
    current_user: dict[str, object] | None = None,
    prioritize_active: bool = False,
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

    status_rank = {"ongoing": 0, "upcoming": 1, "draft": 2, "ended": 3}
    season_catalog = legacy.load_season_catalog(data) if prioritize_active else []

    def competition_sort_key(entry: dict[str, object]) -> tuple[object, ...]:
        if not prioritize_active:
            return (str(entry["series_name"]), str(entry["competition_name"]))
        season_entries = legacy.get_season_entries_for_series(
            season_catalog,
            str(entry["series_slug"]),
            include_non_ongoing=True,
            competition_name=str(entry["competition_name"]),
        )
        best_status_rank = min(
            (
                status_rank.get(legacy.get_season_status(season_entry), 4)
                for season_entry in season_entries
            ),
            default=4,
        )
        return (
            best_status_rank,
            str(entry["series_name"]),
            str(entry["competition_name"]),
        )

    grouped_items = list(grouped_entries.items())
    if prioritize_active:
        region_sort_keys = {
            region_name: min(
                (competition_sort_key(entry) for entry in entries),
                default=(4, "", ""),
            )
            for region_name, entries in grouped_items
        }
        grouped_items.sort(key=lambda item: (region_sort_keys[item[0]], item[0]))
    option_groups: list[str] = []
    known_competitions = {entry["competition_name"] for entry in catalog}
    if current_competition_name and current_competition_name not in known_competitions:
        option_groups.append(
            f'<option value="{escape(current_competition_name)}" selected>{escape(current_competition_name)}（历史赛事）</option>'
        )
    for region_name, entries in grouped_items:
        option_tags_html = []
        for entry in sorted(entries, key=competition_sort_key):
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
    include_non_ongoing: bool = False,
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
            include_non_ongoing=include_non_ongoing,
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
      <div class="small text-secondary mt-2" data-match-season-helper>按进行中、未开始、待排期、已结束排序；未开始赛季也可以提前创建待补录比赛。</div>
    </div>
    <script>
      (function() {{
        const scope = document.currentScript.previousElementSibling;
        if (!scope) return;
        const seasonMap = JSON.parse(scope.getAttribute("data-season-map") || "{{}}");
        const seasonSelect = scope.querySelector("[data-match-season-select]");
        const helper = scope.querySelector("[data-match-season-helper]");
        const form = scope.closest("form");
        const competitionSelect = form ? form.querySelector("[data-match-competition-select]") : null;
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
            seasonSelect.innerHTML = '<option value="">暂无可用赛季</option>';
          }}
          if (helper) {{
            helper.textContent = seasons.length
              ? '优先显示正在进行的赛季，已结束赛季排在最后。'
              : '当前地区赛事页还没有可用赛季，请先到系列赛管理里配置。';
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


def get_match_form_player_name(
    player_lookup: dict[str, dict[str, object]],
    participant: dict[str, object],
) -> str:
    explicit_name = str(participant.get("player_name") or "").strip()
    if explicit_name:
        return explicit_name
    player_id = str(participant.get("player_id") or "").strip()
    if player_id and player_id in player_lookup:
        return str(player_lookup[player_id].get("display_name") or player_id)
    return ""


def get_match_form_team_name(
    team_lookup: dict[str, dict[str, object]],
    participant: dict[str, object],
) -> str:
    explicit_name = str(participant.get("team_name") or "").strip()
    if explicit_name:
        return explicit_name
    team_id = str(participant.get("team_id") or "").strip()
    if team_id and team_id in team_lookup:
        return str(team_lookup[team_id].get("name") or team_id)
    return ""


def build_match_award_name_select(
    selected_ref: str,
    participants: list[dict[str, object]],
    player_lookup: dict[str, dict[str, object]],
    team_lookup: dict[str, dict[str, object]],
    placeholder: str,
    winning_camp: str = "",
    losing_only: bool = False,
) -> str:
    options = [f'<option value="">{escape(placeholder)}</option>']
    for index, participant in enumerate(participants):
        player_name = get_match_form_player_name(player_lookup, participant)
        if not player_name:
            continue
        camp = str(participant.get("camp") or "").strip()
        if losing_only and winning_camp and camp == winning_camp:
            continue
        seat = str(participant.get("seat") or "").strip()
        role = str(participant.get("role") or "").strip()
        team_name = get_match_form_team_name(team_lookup, participant)
        pieces = [f"{seat}号" if seat else "", player_name, role, team_name]
        label = " · ".join(piece for piece in pieces if piece)
        option_value = str(index)
        selected_attr = " selected" if option_value == selected_ref else ""
        options.append(
            f'<option value="{escape(option_value)}"{selected_attr}>{escape(label)}</option>'
        )
    return "".join(options)


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
    score_model = normalize_match_score_model(str(current.get("score_model", "")))
    score_model_label = get_match_score_model_label(score_model)
    try:
        current_data = load_validated_data()
    except Exception:
        current_data = {"players": [], "teams": [], "matches": []}
    scoring_rule = current.get("scoring_rule") or resolve_scoring_rule_for_scope(
        current_data,
        str(current.get("competition_name") or ""),
        str(current.get("season") or ""),
    )
    participation_mode = resolve_participation_mode_for_scope(
        current_data,
        str(current.get("competition_name") or ""),
        str(current.get("season") or ""),
        str(current.get("stage") or ""),
    )
    is_individual_match = participation_mode == PARTICIPATION_MODE_INDIVIDUAL
    configured_score_fields = scoring_rule_component_fields(scoring_rule)
    score_component_fields = (
        configured_score_fields or MATCH_SCORE_COMPONENT_FIELDS
        if uses_structured_score_model(score_model)
        else []
    )
    player_lookup = {
        str(player["player_id"]): player
        for player in current_data.get("players", [])
    }
    team_lookup = {
        str(team["team_id"]): team
        for team in current_data.get("teams", [])
    }
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
    def resolve_selected_award_ref(
        ref_key: str,
        id_key: str,
        name_key: str,
    ) -> str:
        selected_ref = str(current.get(ref_key) or "").strip()
        if selected_ref:
            return selected_ref
        selected_player_id = str(current.get(id_key) or "").strip()
        selected_player_name = str(current.get(name_key) or "").strip()
        for index, participant in enumerate(current["players"]):
            participant_player_id = str(participant.get("player_id") or "").strip()
            participant_player_name = get_match_form_player_name(player_lookup, participant)
            if selected_player_id and participant_player_id == selected_player_id:
                return str(index)
            if selected_player_name and participant_player_name == selected_player_name:
                return str(index)
        return ""

    selected_mvp_ref = resolve_selected_award_ref("mvp_player_ref", "mvp_player_id", "mvp_player_name")
    selected_svp_ref = resolve_selected_award_ref("svp_player_ref", "svp_player_id", "svp_player_name")
    selected_scapegoat_ref = resolve_selected_award_ref(
        "scapegoat_player_ref",
        "scapegoat_player_id",
        "scapegoat_player_name",
    )
    participant_rows = []
    fixed_score_field_names = {field_name for field_name, _ in MATCH_SCORE_COMPONENT_FIELDS}

    def score_input_name(field_name: str, index: int) -> str:
        if field_name in fixed_score_field_names:
            return f"{field_name}_{index}"
        return f"score_component_{field_name}_{index}"

    for index, player in enumerate(current["players"]):
        player_name = get_match_form_player_name(player_lookup, player)
        team_name = get_match_form_team_name(team_lookup, player)
        score_breakdown = normalize_score_breakdown(player)
        structured_cells = "".join(
            f'<td data-structured-score-column><input class="form-control form-control-sm" '
            f'data-score-component name="{score_input_name(field_name, index)}" type="number" step="0.1" '
            f'value="{escape(str(score_breakdown.get(field_name, 0.0)))}"></td>'
            for field_name, _ in score_component_fields
        )
        participant_rows.append(
            f"""
            <tr data-participant-row>
              <td><input class="form-control form-control-sm" data-award-player-id name="player_name_{index}" value="{escape(player_name)}"></td>
              <td><input class="form-control form-control-sm" name="team_name_{index}" value="{escape(team_name)}"></td>
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
              {structured_cells}
              <td><input class="form-control form-control-sm" data-points-earned name="points_earned_{index}" type="number" step="0.1" value="{escape(str(player['points_earned']))}"></td>
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
          <p class="section-copy mb-0">这里可以录入或修改一场比赛的基础信息和全部上场选手数据。比赛编号会按“城市缩写-赛季缩写-六位日期-两位序号”自动生成，赛季为必填项。</p>
        </div>
        <div class="d-flex gap-2">
          <a class="btn btn-outline-dark" href="{escape(next_path)}">返回上一页</a>
        </div>
      </div>
      <form method="post" action="{escape(action_url)}" data-dynamic-rule-form="{'1' if str(current.get('match_id') or '') == 'pending-new-match' else '0'}">
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
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">计分模型</label>
            <input type="hidden" data-score-model-select name="score_model" value="{escape(score_model)}">
            <input class="form-control" value="{escape(score_model_label)}" readonly>
            <div class="small text-secondary mt-2">由当前系列赛/赛季计分规则自动带入；需要调整请前往系列赛管理。</div>
          </div>
          <div class="col-12 col-md-6 col-xl-3 d-flex align-items-end">
            <div class="form-check mb-2">
              <input class="form-check-input" id="exclude_from_team_scores" name="exclude_from_team_scores" type="checkbox" value="1"{' checked' if current.get('exclude_from_team_scores') else ''}>
              <label class="form-check-label" for="exclude_from_team_scores">抽局，不计战队总分</label>
              <div class="small text-secondary mt-1">个人得分仍会正常计入选手数据。</div>
            </div>
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
          <input type="hidden" name="game_no" value="{escape(str(current['game_no']))}">
          <div class="col-12 col-md-6 col-xl-2">
            <label class="form-label">日期</label>
            <input class="form-control" name="played_on" type="date" value="{escape(str(current['played_on']))}">
          </div>
          <div class="col-12 col-md-6 col-xl-2">
            <label class="form-label">参赛分组</label>
            <input class="form-control" name="group_label" value="{escape(str(current.get('group_label') or ''))}">
          </div>
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">房间</label>
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
            <select class="form-select" data-award-select="mvp" data-selected="{escape(selected_mvp_ref)}" name="mvp_player_ref">
              {build_match_award_name_select(selected_mvp_ref, current['players'], player_lookup, team_lookup, '请选择 MVP')}
            </select>
            <input type="hidden" name="mvp_player_name" value="">
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label">SVP</label>
            <select class="form-select" data-award-select="svp" data-selected="{escape(selected_svp_ref)}" name="svp_player_ref">
              {build_match_award_name_select(selected_svp_ref, current['players'], player_lookup, team_lookup, '请选择 SVP')}
            </select>
            <input type="hidden" name="svp_player_name" value="">
          </div>
          <div class="col-12 col-md-4" data-scapegoat-field{scapegoat_hidden_attr}>
            <label class="form-label">背锅</label>
            <select class="form-select" data-award-select="scapegoat" data-selected="{escape(selected_scapegoat_ref)}" name="scapegoat_player_ref">
              {build_match_award_name_select(selected_scapegoat_ref, current['players'], player_lookup, team_lookup, '请选择背锅选手', str(current.get('winning_camp', '')), True)}
            </select>
            <input type="hidden" name="scapegoat_player_name" value="">
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
            <div class="small text-secondary">这里按当前顺序编辑所有参赛选手信息。{('当前是个人赛，战队名称可以留空，成绩只进入个人统计。' if is_individual_match else '录入时直接填写队员姓名和战队名称；系统会在当前赛事赛季内自动匹配，找不到时会先创建赛季档案。')}计分分项来自后台系列赛/赛季规则，并自动汇总总分。</div>
          </div>
        </div>

        <div class="table-responsive mb-4">
          <table class="table align-middle">
            <thead>
              <tr>
                <th>队员姓名</th>
                <th>战队名称{'（可留空）' if is_individual_match else ''}</th>
                <th>座位</th>
                <th>角色</th>
                <th>阵营</th>
                <th>结果</th>
                {''.join(f'<th data-structured-score-column>{escape(field_label)}</th>' for _, field_label in score_component_fields)}
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
        const scoreModelSelect = form.querySelector("[data-score-model-select]");
        const competitionSelect = form.querySelector("[data-match-competition-select]");
        const seasonSelect = form.querySelector("[data-match-season-select]");
        const dynamicRuleForm = form.getAttribute("data-dynamic-rule-form") === "1";
        const initialCompetition = {json.dumps(str(current.get("competition_name") or ""), ensure_ascii=False)};
        const initialSeason = {json.dumps(str(current.get("season") or ""), ensure_ascii=False)};
        const playerInputs = Array.from(form.querySelectorAll("[data-award-player-id]"));
        const teamNameInputs = Array.from(form.querySelectorAll('[name^="team_name_"]'));
        const seatInputs = Array.from(form.querySelectorAll("[data-award-seat]"));
        const roleInputs = Array.from(form.querySelectorAll("[data-award-role]"));
        const campInputs = Array.from(form.querySelectorAll("[data-award-camp]"));
        const structuredScoreColumns = Array.from(form.querySelectorAll("[data-structured-score-column]"));
        const participantRows = Array.from(form.querySelectorAll("[data-participant-row]"));
        function collectParticipants() {{
          return playerInputs.map((input, index) => {{
            const playerName = (input.value || "").trim();
            const seat = (seatInputs[index] && seatInputs[index].value) || "";
            const role = (roleInputs[index] && roleInputs[index].value) || "";
            const teamNameInput = form.querySelector(`[name="team_name_${{index}}"]`);
            const teamName = (teamNameInput && teamNameInput.value) || "";
            const camp = (campInputs[index] && campInputs[index].value) || "";
            return {{ index, playerName, seat, role, teamName, camp }};
          }}).filter((item) => item.playerName);
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
              const pieces = [`${{item.seat}}号`, item.playerName];
              if (item.role) pieces.push(item.role);
              if (item.teamName) pieces.push(item.teamName);
              const optionValue = String(item.index);
              const selected = optionValue === selectedValue ? " selected" : "";
              return `<option value="${{optionValue}}"${{selected}}>${{pieces.join(" · ")}}</option>`;
            }})
          );
          select.innerHTML = options.join("");
          if (selectedValue && !filtered.some((item) => String(item.index) === selectedValue)) {{
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
        function updateStructuredScoreRows() {{
          const isStructured = scoreModelSelect && scoreModelSelect.value === "jingcheng_daily";
          structuredScoreColumns.forEach((element) => {{
            element.style.display = isStructured ? "" : "none";
          }});
          participantRows.forEach((row) => {{
            const totalInput = row.querySelector("[data-points-earned]");
            const componentInputs = Array.from(row.querySelectorAll("[data-score-component]"));
            if (!totalInput) return;
            totalInput.readOnly = !!isStructured;
            if (!isStructured) return;
            const total = componentInputs.reduce((sum, input) => {{
              const nextValue = Number.parseFloat(input.value || "0");
              return sum + (Number.isFinite(nextValue) ? nextValue : 0);
            }}, 0);
            totalInput.value = total.toFixed(2);
          }});
        }}
        function reloadForSelectedRule() {{
          if (!dynamicRuleForm || !competitionSelect || !seasonSelect) return;
          const competition = competitionSelect.value || "";
          const season = seasonSelect.value || "";
          if (!competition || !season) return;
          if (competition === initialCompetition && season === initialSeason) return;
          const target = new URL(window.location.href);
          target.pathname = "/matches/new";
          target.searchParams.delete("action");
          target.searchParams.set("competition", competition);
          target.searchParams.set("season", season);
          window.location.href = target.toString();
        }}
        [winningCampSelect, ...playerInputs, ...teamNameInputs, ...seatInputs, ...roleInputs, ...campInputs]
          .filter(Boolean)
          .forEach((element) => element.addEventListener("input", renderAwards));
        [winningCampSelect, ...campInputs]
          .filter(Boolean)
          .forEach((element) => element.addEventListener("change", renderAwards));
        participantRows.forEach((row) => {{
          row.querySelectorAll("[data-score-component]").forEach((input) => {{
            input.addEventListener("input", updateStructuredScoreRows);
          }});
        }});
        if (scoreModelSelect) scoreModelSelect.addEventListener("change", updateStructuredScoreRows);
        if (competitionSelect) competitionSelect.addEventListener("change", reloadForSelectedRule);
        if (seasonSelect) seasonSelect.addEventListener("change", reloadForSelectedRule);
        updateStructuredScoreRows();
        renderAwards();
        window.setTimeout(reloadForSelectedRule, 0);
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
        "room_label": "1号房",
    }


def get_match_edit_page(
    ctx: RequestContext,
    match_id: str,
    alert: str = "",
    field_values: dict[str, object] | None = None,
) -> str:
    alert = alert or form_value(ctx.query, "alert").strip()
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

    current = ensure_match_form_players(field_values or match)
    if not current.get("scoring_rule"):
        current["scoring_rule"] = resolve_scoring_rule_for_scope(
            data,
            get_match_competition_name(match),
            str(match.get("season") or ""),
        )
    next_path = form_value(ctx.query, "next").strip() or "/matches/new"
    match_code_hint = current.get("match_id", match_id)
    form_html = render_match_form_page(
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
    excel_panel_html = build_excel_import_panel(ctx)
    dimension_panel_html = build_dimension_import_panel(ctx)
    team_logo_panel_html = build_team_logo_import_panel(ctx)
    player_photo_panel_html = build_player_photo_import_panel(ctx)
    if '<section class="form-panel' not in form_html:
        return form_html
    return form_html.replace(
        '<section class="form-panel',
        f"{excel_panel_html}{dimension_panel_html}{team_logo_panel_html}{player_photo_panel_html}<section class=\"form-panel",
        1,
    )


def get_match_create_page(
    ctx: RequestContext,
    alert: str = "",
    field_values: dict[str, object] | None = None,
    batch_form_values: dict[str, str] | None = None,
    excel_form_values: dict[str, str] | None = None,
) -> str:
    alert = alert or form_value(ctx.query, "alert").strip()
    current = ensure_match_form_players(field_values or build_empty_match(
        form_value(ctx.query, "competition").strip(),
        form_value(ctx.query, "season").strip(),
    ))
    if not field_values and current.get("competition_name") and current.get("season"):
        scoring_rule = resolve_scoring_rule_for_scope(
            load_validated_data(),
            str(current.get("competition_name") or ""),
            str(current.get("season") or ""),
        )
        current["score_model"] = str(scoring_rule.get("score_model") or "standard")
        current["scoring_rule"] = scoring_rule
    if current.get("competition_name"):
        data = load_validated_data()
        if ctx.current_user and not can_manage_matches(
            ctx.current_user,
            data,
            str(current.get("competition_name") or ""),
        ):
            return layout("没有权限", '<div class="alert alert-danger">你不能在这个地区系列赛下创建比赛。</div>', ctx)
    next_path = form_value(ctx.query, "next").strip() or build_match_management_path(
        ctx,
        str(current.get("competition_name") or ""),
        str(current.get("season") or ""),
    )
    manual_form_html = render_match_form_page(
        ctx,
        current,
        f"/matches/new?next={quote(next_path)}",
        "比赛管理",
        "新增比赛",
        "创建比赛",
        next_path,
        "保存后自动生成",
        alert=alert,
    )
    management_panel_html = build_match_management_panel(ctx)
    batch_panel_html = build_batch_create_form(ctx, get_batch_create_form_values(ctx, batch_form_values))
    excel_panel_html = build_excel_import_panel(ctx, excel_form_values)
    dimension_panel_html = build_dimension_import_panel(ctx)
    team_logo_panel_html = build_team_logo_import_panel(ctx)
    player_photo_panel_html = build_player_photo_import_panel(ctx)
    import_batches_panel_html = build_import_batches_panel(ctx)
    body_start = manual_form_html.find('<section class="form-panel')
    if body_start == -1:
        return manual_form_html
    combined_body = manual_form_html.replace(
        '<section class="form-panel',
        f"{batch_panel_html}{excel_panel_html}{dimension_panel_html}{team_logo_panel_html}{player_photo_panel_html}{import_batches_panel_html}<section class=\"form-panel",
        1,
    )
    if "</main>" in combined_body:
        combined_body = combined_body.replace("</main>", f"{management_panel_html}</main>", 1)
    else:
        combined_body = combined_body.replace("</body>", f"{management_panel_html}</body>", 1)
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

    updated_match = parse_match_form(ctx.form, ensure_match_form_players(match))
    resolution_errors = resolve_match_entities(data, [updated_match])
    if resolution_errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_edit_page(ctx, match_id, alert=resolution_errors[0], field_values=updated_match),
        )
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
        include_non_ongoing=True,
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
        action = form_value(ctx.query, "action").strip()
        if action == "download_scoring_template":
            data = load_validated_data()
            competition_name = (
                form_value(ctx.query, "competition_name").strip()
                or form_value(ctx.query, "competition").strip()
            )
            season_name = form_value(ctx.query, "season").strip()
            if not can_manage_matches(ctx.current_user, data, competition_name):
                return start_response_html(
                    start_response,
                    "403 Forbidden",
                    layout(
                        "没有权限",
                        f'<div class="alert alert-danger">你没有权限下载 {escape(competition_name)} 的赛季模板。</div>',
                        ctx,
                    ),
                )
            competition_error = validate_match_competition_selection(data, competition_name)
            season_error = validate_match_season_selection(
                data,
                competition_name,
                season_name,
                include_non_ongoing=True,
            )
            if competition_error or season_error:
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_match_create_page(
                        ctx,
                        alert=competition_error or season_error,
                        excel_form_values={
                            "group_label": "",
                            "competition_name": competition_name,
                            "season": season_name,
                        },
                    ),
                )
            scoring_rule = resolve_scoring_rule_for_scope(
                data,
                competition_name,
                season_name,
            )
            payload = build_dynamic_match_template_bytes(
                competition_name,
                season_name,
                scoring_rule,
            )
            version = int(scoring_rule.get("version") or 1)
            safe_scope = re.sub(
                r"[^A-Za-z0-9_.-]+",
                "-",
                f"{competition_name}-{season_name}",
            ).strip("-")
            filename = f"{safe_scope or 'season-scoring'}-template-v{version}.xlsx"
            start_response(
                "200 OK",
                [
                    (
                        "Content-Type",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ),
                    ("Content-Length", str(len(payload))),
                    ("Content-Disposition", f'attachment; filename="{filename}"'),
                ],
            )
            return [payload]
        if action == "export_season_player_photo_roster":
            data = load_validated_data()
            competition_name = (
                form_value(ctx.query, "competition_name").strip()
                or form_value(ctx.query, "competition").strip()
            )
            season_name = form_value(ctx.query, "season").strip()
            if not can_manage_matches(ctx.current_user, data, competition_name):
                return start_response_html(
                    start_response,
                    "403 Forbidden",
                    layout("没有权限", f'<div class="alert alert-danger">你没有权限导出 {escape(competition_name)} 下的队员名单。</div>', ctx),
                )
            competition_error = validate_match_competition_selection(data, competition_name)
            if competition_error:
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_match_create_page(ctx, alert=competition_error),
                )
            season_error = validate_match_season_selection(
                data,
                competition_name,
                season_name,
                include_non_ongoing=True,
            )
            if season_error:
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_match_create_page(ctx, alert=season_error),
                )
            payload = build_season_player_photo_roster_csv(data, competition_name, season_name)
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{competition_name}-{season_name}-players").strip("-")
            filename = f"{safe_name or 'season-players'}.csv"
            start_response(
                "200 OK",
                [
                    ("Content-Type", "text/csv; charset=utf-8"),
                    ("Content-Length", str(len(payload))),
                    ("Content-Disposition", f'attachment; filename="{filename}"'),
                ],
            )
            return [payload]
        return start_response_html(start_response, "200 OK", get_match_create_page(ctx))

    data = load_validated_data()
    action = form_value(ctx.form, "action").strip()
    if action == "rollback_import_batch":
        if not is_admin_user(ctx.current_user):
            return start_response_html(
                start_response,
                "403 Forbidden",
                get_match_create_page(ctx, alert="只有管理员可以回滚导入批次。"),
            )
        batch_id = form_value(ctx.form, "batch_id").strip()
        expected_confirmation = f"回滚 {batch_id}"
        confirmation_error = danger_confirmation_error(
            form_value(ctx.form, "danger_confirmation"),
            expected_confirmation,
            "回滚导入批次",
        )
        if confirmation_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=confirmation_error),
            )
        ok, message = rollback_import_batch(batch_id, ctx)
        audit_action(
            ctx,
            "import_batch.rollback",
            target_type="import_batch",
            target_id=batch_id,
            summary=message,
            metadata={"ok": ok},
        )
        return redirect(start_response, append_alert_query("/matches/new", message))
    if action in {
        "batch_delete_matches",
        "batch_mark_team_score_excluded",
        "batch_unmark_team_score_excluded",
    }:
        selected_match_ids = [
            value.strip()
            for value in ctx.form.get("match_ids", [])
            if str(value or "").strip()
        ]
        management_form_values = {
            "competition_name": form_value(ctx.form, "competition_name").strip(),
            "season": form_value(ctx.form, "season").strip(),
            "stage": form_value(ctx.form, "stage").strip(),
            "played_on": form_value(ctx.form, "played_on").strip(),
            "keyword": form_value(ctx.form, "keyword").strip(),
        }
        if not selected_match_ids:
            action_labels = {
                "batch_delete_matches": "删除",
                "batch_mark_team_score_excluded": "设为抽局",
                "batch_unmark_team_score_excluded": "取消抽局",
            }
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(
                    ctx,
                    alert=f"请先勾选要{action_labels.get(action, '管理')}的比赛。",
                    batch_form_values=None,
                ),
            )
        selected_matches = [
            match for match in data["matches"] if match["match_id"] in set(selected_match_ids)
        ]
        if len(selected_matches) != len(set(selected_match_ids)):
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="选中的比赛里有不存在的记录，请刷新后重试。"),
            )
        for match in selected_matches:
            permission_guard = require_competition_manager(
                ctx,
                start_response,
                data,
                get_match_competition_name(match),
                "你不能管理未授权地区系列赛下的比赛。",
            )
            if permission_guard is not None:
                return permission_guard
        if action == "batch_delete_matches":
            confirmation_error = danger_confirmation_error(
                form_value(ctx.form, "danger_confirmation"),
                "删除比赛",
                "批量删除比赛",
            )
            if confirmation_error:
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_match_create_page(ctx, alert=confirmation_error),
                )
        if action in {
            "batch_mark_team_score_excluded",
            "batch_unmark_team_score_excluded",
        }:
            should_exclude = action == "batch_mark_team_score_excluded"
            selected_match_id_set = set(selected_match_ids)
            updated_count = 0
            for match in data["matches"]:
                if match["match_id"] not in selected_match_id_set:
                    continue
                if bool(match.get("exclude_from_team_scores")) == should_exclude:
                    continue
                match["exclude_from_team_scores"] = should_exclude
                updated_count += 1
            users = load_users()
            errors = save_repository_state(data, users)
            if errors:
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_match_create_page(ctx, alert="抽局状态保存失败：" + "；".join(errors[:3])),
                )
            action_message = "设为抽局" if should_exclude else "取消抽局"
            audit_action(
                ctx,
                "matches.batch_score_exclusion",
                target_type="match",
                target_id=",".join(selected_match_ids[:20]),
                summary=f"批量{action_message} {updated_count} 场比赛",
                metadata={
                    "match_ids": selected_match_ids,
                    "exclude_from_team_scores": should_exclude,
                },
            )
            return redirect(
                start_response,
                append_alert_query(
                    build_match_management_path(ctx, values=management_form_values),
                    f"已{action_message} {updated_count} 场比赛。",
                ),
            )
        remaining_matches = [
            match for match in data["matches"] if match["match_id"] not in set(selected_match_ids)
        ]
        users = load_users()
        data["matches"] = remaining_matches
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="批量删除失败：" + "；".join(errors[:3])),
            )
        audit_action(
            ctx,
            "matches.batch_delete",
            target_type="match",
            target_id=",".join(selected_match_ids[:20]),
            summary=f"批量删除 {len(selected_match_ids)} 场比赛",
            metadata={"match_ids": selected_match_ids},
        )
        return redirect(
            start_response,
            append_alert_query(
                build_match_management_path(ctx, values=management_form_values),
                f"已删除 {len(selected_match_ids)} 场比赛。",
            ),
        )
    if action == "batch_create_matches":
        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season").strip()
        stage = form_value(ctx.form, "stage").strip()
        start_date = form_value(ctx.form, "start_date").strip()
        end_date = form_value(ctx.form, "end_date").strip()
        round_start_raw = form_value(ctx.form, "round_start", "1").strip()
        matches_per_day_raw = form_value(ctx.form, "matches_per_day", "1").strip()
        room_label = form_value(ctx.form, "room_label", "1号房").strip()
        batch_form_values = {
            "competition_name": competition_name,
            "season": season_name,
            "stage": stage,
            "start_date": start_date,
            "end_date": end_date,
            "round_start": round_start_raw or "1",
            "matches_per_day": matches_per_day_raw or "1",
            "room_label": room_label or "1号房",
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
        season_error = validate_match_season_selection(
            data,
            competition_name,
            season_name,
            include_non_ongoing=True,
        )
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
                room_label,
            )
        except ValueError as exc:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=str(exc), batch_form_values=batch_form_values),
            )
        import_batch_id = create_import_batch(
            ctx=ctx,
            action="matches.batch_create",
            label="批量创建待补录比赛",
            metadata={
                "competition_name": competition_name,
                "season_name": season_name,
                "created_matches": len(new_matches),
            },
        )
        normalized_matches, _ = canonicalize_match_ids([*data["matches"], *new_matches])
        users = load_users()
        data["matches"] = normalized_matches
        users = ensure_placeholder_users_for_player_ids(data, users, [])
        errors = save_repository_state(data, users)
        if errors:
            update_import_batch(import_batch_id, status="failed", summary="批量创建失败：" + "；".join(errors[:3]), ctx=ctx)
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="批量创建失败：" + "；".join(errors[:3]), batch_form_values=batch_form_values),
            )
        update_import_batch(
            import_batch_id,
            status="succeeded",
            summary=f"批量创建 {len(new_matches)} 场待补录比赛",
            metadata={
                "match_ids": [str(match.get("match_id") or "") for match in new_matches],
            },
            ctx=ctx,
        )
        audit_action(
            ctx,
            "matches.batch_create",
            target_type="competition",
            target_id=competition_name,
            summary=f"批量创建 {len(new_matches)} 场待补录比赛",
            metadata={
                "competition_name": competition_name,
                "season_name": season_name,
                "match_ids": [str(match.get("match_id") or "") for match in new_matches],
            },
        )
        next_path = form_value(ctx.query, "next").strip() or build_match_management_path(
            ctx,
            competition_name,
            season_name,
        )
        return redirect(
            start_response,
            append_alert_query(next_path, f"已批量创建 {len(new_matches)} 场待补录比赛。"),
        )
    if action == "import_match_excel":
        group_label = form_value(ctx.form, "group_label").strip()
        excel_form_values = {"group_label": group_label}
        upload = file_value(ctx.files, "match_excel_file")
        upload_error = validate_excel_upload(upload)
        if upload_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=upload_error, excel_form_values=excel_form_values),
            )
        next_matches, import_message = import_matches_from_excel(ctx, data, upload, group_label)
        if next_matches is None:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=import_message, excel_form_values=excel_form_values),
            )
        before_match_by_id = {str(match.get("match_id") or ""): match for match in data.get("matches", [])}
        next_match_by_id = {str(match.get("match_id") or ""): match for match in next_matches}
        created_match_ids = [match_id for match_id in next_match_by_id if match_id and match_id not in before_match_by_id]
        updated_match_ids = [
            match_id
            for match_id, match in next_match_by_id.items()
            if match_id in before_match_by_id
            and json.dumps(before_match_by_id[match_id], ensure_ascii=False, sort_keys=True)
            != json.dumps(match, ensure_ascii=False, sort_keys=True)
        ]
        import_batch_id = create_import_batch(
            ctx=ctx,
            action="matches.import_excel",
            label="Excel 批量补录比赛详情",
            filename=getattr(upload, "filename", "") or "",
            metadata={
                "group_label": group_label,
                "created_matches": len(created_match_ids),
                "updated_matches": len(updated_match_ids),
            },
        )
        users = load_users()
        normalized_matches, _ = canonicalize_match_ids(next_matches)
        data["matches"] = normalized_matches
        created_player_ids = ensure_placeholder_players_for_matches(data, normalized_matches)
        users = ensure_placeholder_users_for_player_ids(data, users, created_player_ids)
        errors = save_repository_state(data, users)
        if errors:
            update_import_batch(import_batch_id, status="failed", summary="Excel 导入保存失败：" + "；".join(errors[:3]), ctx=ctx)
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(
                    ctx,
                    alert="Excel 导入保存失败：" + "；".join(errors[:3]),
                    excel_form_values=excel_form_values,
                ),
            )
        update_import_batch(
            import_batch_id,
            status="succeeded",
            summary=import_message,
            metadata={
                "created_matches": len(created_match_ids),
                "updated_matches": len(updated_match_ids),
                "created_players": len(created_player_ids),
                "created_match_ids": created_match_ids[:100],
                "updated_match_ids": updated_match_ids[:100],
            },
            ctx=ctx,
        )
        audit_action(
            ctx,
            "matches.import_excel",
            target_type="competition",
            target_id=group_label,
            summary=import_message,
            metadata={
                "group_label": group_label,
                "match_count": len(normalized_matches),
                "placeholder_player_ids": created_player_ids,
            },
        )
        next_path = form_value(ctx.query, "next").strip() or build_match_management_path(ctx)
        alert_message = import_message
        if created_player_ids:
            alert_message += " 系统还为模板里不存在的参赛 ID 自动创建了赛季档案。"
        return redirect(start_response, append_alert_query(next_path, alert_message))
    if action == "import_dimension_excel":
        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season").strip()
        upload = file_value(ctx.files, "dimension_excel_file")
        upload_error = validate_excel_upload(upload)
        if upload_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=upload_error),
            )
        next_player_rows, next_team_rows, import_message = import_dimension_stats_from_excel(
            ctx,
            data,
            upload,
            competition_name,
            season_name,
        )
        if next_player_rows is None or next_team_rows is None:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=import_message),
            )
        import_batch_id = create_import_batch(
            ctx=ctx,
            action="dimension.import_excel",
            label="Excel 批量导入赛季维度数据",
            filename=getattr(upload, "filename", "") or "",
            metadata={
                "competition_name": competition_name,
                "season_name": season_name,
                "player_rows": len(next_player_rows),
                "team_rows": len(next_team_rows),
            },
        )
        try:
            save_season_dimension_stats(next_player_rows, next_team_rows)
            invalidate_validated_data_cache()
        except Exception as exc:
            update_import_batch(import_batch_id, status="failed", summary=f"维度数据保存失败：{exc}", ctx=ctx)
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=f"维度数据保存失败：{exc}"),
            )
        update_import_batch(
            import_batch_id,
            status="succeeded",
            summary=import_message,
            metadata={
                "competition_name": competition_name,
                "season_name": season_name,
                "player_rows": len(next_player_rows),
                "team_rows": len(next_team_rows),
            },
            ctx=ctx,
        )
        audit_action(
            ctx,
            "dimension.import_excel",
            target_type="competition",
            target_id=competition_name,
            summary=import_message,
            metadata={
                "competition_name": competition_name,
                "season_name": season_name,
                "player_rows": len(next_player_rows),
                "team_rows": len(next_team_rows),
            },
        )
        next_path = form_value(ctx.query, "next").strip() or build_match_management_path(
            ctx,
            competition_name,
            season_name,
        )
        return redirect(start_response, append_alert_query(next_path, import_message))
    if action == "clear_dimension_stats":
        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season").strip()
        if not competition_name:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="请先选择要清空的地区赛事页。"),
            )
        if not season_name:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="请先选择要清空的赛季。"),
            )
        if not can_manage_matches(ctx.current_user, data, competition_name):
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=f"你没有权限清空 {competition_name} 下的维度数据。"),
            )
        confirmation_error = danger_confirmation_error(
            form_value(ctx.form, "danger_confirmation"),
            "清空维度",
            "清空赛季维度数据",
        )
        if confirmation_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=confirmation_error),
            )
        competition_error = validate_match_competition_selection(data, competition_name)
        if competition_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=competition_error),
            )
        season_error = validate_match_season_selection(
            data,
            competition_name,
            season_name,
            include_non_ongoing=True,
        )
        if season_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=season_error),
            )
        try:
            deleted_player_count, deleted_team_count = clear_season_dimension_stats(
                competition_name,
                season_name,
            )
        except Exception as exc:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=f"清空维度数据失败：{exc}"),
            )
        audit_action(
            ctx,
            "dimension.clear",
            target_type="competition",
            target_id=competition_name,
            summary=f"清空 {competition_name} / {season_name} 维度数据",
            metadata={
                "competition_name": competition_name,
                "season_name": season_name,
                "deleted_player_count": deleted_player_count,
                "deleted_team_count": deleted_team_count,
            },
        )
        next_path = form_value(ctx.query, "next").strip() or build_match_management_path(
            ctx,
            competition_name,
            season_name,
        )
        return redirect(
            start_response,
            append_alert_query(
                next_path,
                f"已清空维度数据：选手 {deleted_player_count} 条，战队 {deleted_team_count} 条。",
            ),
        )
    if action == "import_team_logo_excel":
        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season").strip()
        upload = file_value(ctx.files, "team_logo_excel_file")
        upload_error = validate_excel_upload(upload)
        if upload_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=upload_error),
            )
        next_teams, import_message = import_team_logos_from_excel(
            ctx,
            data,
            upload,
            competition_name,
            season_name,
        )
        if next_teams is None:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=import_message),
            )
        users = load_users()
        data["teams"] = next_teams
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="战队图标导入保存失败：" + "；".join(errors[:3])),
            )
        audit_action(
            ctx,
            "team_logo.import_excel",
            target_type="competition",
            target_id=competition_name,
            summary=import_message,
            metadata={"competition_name": competition_name, "season_name": season_name},
        )
        next_path = form_value(ctx.query, "next").strip() or build_match_management_path(
            ctx,
            competition_name,
            season_name,
        )
        return redirect(start_response, append_alert_query(next_path, import_message))
    if action == "confirm_player_photo_zip":
        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season").strip()
        if not can_manage_matches(ctx.current_user, data, competition_name):
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=f"你没有权限导入 {competition_name} 下的队员头像。"),
            )
        competition_error = validate_match_competition_selection(data, competition_name)
        if competition_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=competition_error),
            )
        season_error = validate_match_season_selection(
            data,
            competition_name,
            season_name,
            include_non_ongoing=True,
        )
        if season_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=season_error),
            )
        player_by_id, _players_by_name, _team_lookup = build_match_record_player_context(
            data,
            competition_name,
            season_name,
        )
        assignments = parse_manual_player_photo_assignments(ctx.form, player_by_id)
        if not assignments:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="请至少选择一张要导入的队员头像。"),
            )
        updated_count, save_error = apply_player_photo_assignments(data, assignments)
        if save_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=save_error),
            )
        users = load_users()
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="队员头像导入保存失败：" + "；".join(errors[:3])),
            )
        audit_action(
            ctx,
            "player_photo.import_manual",
            target_type="competition",
            target_id=competition_name,
            summary=f"手动确认导入队员头像，更新 {updated_count} 位",
            metadata={
                "competition_name": competition_name,
                "season_name": season_name,
                "updated_count": updated_count,
            },
        )
        next_path = form_value(ctx.query, "next").strip() or build_match_management_path(
            ctx,
            competition_name,
            season_name,
        )
        return redirect(start_response, append_alert_query(next_path, f"队员头像导入完成：更新 {updated_count} 位。"))
    if action == "import_player_photo_zip":
        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season").strip()
        upload = file_value(ctx.files, "player_photo_zip_file")
        upload_error = validate_zip_upload(upload)
        if upload_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=upload_error),
            )
        if not can_manage_matches(ctx.current_user, data, competition_name):
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=f"你没有权限导入 {competition_name} 下的队员头像。"),
            )
        competition_error = validate_match_competition_selection(data, competition_name)
        if competition_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=competition_error),
            )
        season_error = validate_match_season_selection(
            data,
            competition_name,
            season_name,
            include_non_ongoing=True,
        )
        if season_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=season_error),
            )
        player_by_id, players_by_name, team_lookup = build_match_record_player_context(
            data,
            competition_name,
            season_name,
        )
        if not player_by_id:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="当前赛事赛季还没有可匹配的比赛记录队员。"),
            )
        items, ignored_message = read_player_photo_zip_items(upload)
        if items is None:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=ignored_message),
            )
        auto_assignments, conflicts, unmatched_count = resolve_zip_photo_assignments(
            items,
            player_by_id,
            players_by_name,
        )
        if conflicts:
            return start_response_html(
                start_response,
                "200 OK",
                build_player_photo_manual_select_page(
                    ctx,
                    competition_name,
                    season_name,
                    items,
                    auto_assignments,
                    conflicts,
                    unmatched_count,
                    ignored_message,
                    player_by_id,
                    team_lookup,
                ),
            )
        updated_count, save_error = apply_player_photo_assignments(data, [
            {
                "player_id": str(item["player_id"]),
                "filename": str(item["filename"]),
                "pending_path": str(item["pending_path"]),
            }
            for item in auto_assignments
        ])
        if save_error:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert=save_error),
            )
        users = load_users()
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_match_create_page(ctx, alert="队员头像导入保存失败：" + "；".join(errors[:3])),
            )
        audit_action(
            ctx,
            "player_photo.import_zip",
            target_type="competition",
            target_id=competition_name,
            summary=f"ZIP 导入队员头像，更新 {updated_count} 位，跳过 {unmatched_count} 个",
            metadata={
                "competition_name": competition_name,
                "season_name": season_name,
                "updated_count": updated_count,
                "unmatched_count": unmatched_count,
            },
        )
        next_path = form_value(ctx.query, "next").strip() or build_match_management_path(
            ctx,
            competition_name,
            season_name,
        )
        import_message = (
            f"队员头像导入完成：更新 {updated_count} 位，"
            f"未匹配跳过 {unmatched_count} 个。{ignored_message}"
        )
        return redirect(start_response, append_alert_query(next_path, import_message))

    submitted_competition = form_value(ctx.form, "competition_name").strip()
    submitted_season = form_value(ctx.form, "season").strip()
    match_seed = build_empty_match(submitted_competition, submitted_season)
    submitted_rule = resolve_scoring_rule_for_scope(
        data,
        submitted_competition,
        submitted_season,
    )
    match_seed["score_model"] = str(submitted_rule.get("score_model") or "standard")
    match_seed["scoring_rule"] = submitted_rule
    submitted_form = {
        **ctx.form,
        "score_model": [str(submitted_rule.get("score_model") or "standard")],
    }
    new_match = parse_match_form(submitted_form, match_seed)
    resolution_errors = resolve_match_entities(data, [new_match])
    if resolution_errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_create_page(ctx, alert=resolution_errors[0], field_values=new_match),
        )
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
        include_non_ongoing=True,
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

    audit_action(
        ctx,
        "match.create",
        target_type="match",
        target_id=resolved_match_id or str(new_match.get("match_id") or ""),
        summary=f"新增比赛 {resolved_match_id or str(new_match.get('match_id') or '')}",
        metadata={
            "competition_name": str(new_match.get("competition_name") or ""),
            "season_name": str(new_match.get("season") or ""),
            "placeholder_player_ids": created_player_ids,
        },
    )

    next_path = form_value(ctx.query, "next").strip()
    if next_path:
        if created_player_ids and next_path.startswith("/matches/"):
            next_path = append_alert_query(next_path, "placeholder-created")
        return redirect(start_response, next_path)
    redirect_path = build_match_management_path(
        ctx,
        str(new_match.get("competition_name") or ""),
        str(new_match.get("season") or ""),
    )
    if created_player_ids:
        redirect_path = append_alert_query(redirect_path, "placeholder-created")
    return redirect(start_response, redirect_path)
