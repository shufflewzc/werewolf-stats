"""Task-oriented administration console pages.

Route semantics expected from the compatibility dispatcher in ``web_app.py``:

``GET /console``
    Render the operator overview for the current authorized series/season.
``GET /console/matches``
    Render the permission-filtered match search and paginated result list.
``GET /console/matches/create``
    Open the focused single-match creation task.
``GET /console/matches/batch-create``
    Open the focused schedule batch-creation task.
``GET /console/imports[/data|/assets]``
    Open the matching upload task or the import activity hub.

This module owns the first two handlers.  The remaining paths are stable task
links for the dispatcher/import feature to attach to, which keeps this page
independent from the legacy all-in-one ``/matches/new`` implementation.
"""

from __future__ import annotations

from datetime import date
from html import escape
import json
from typing import Any, Callable, Iterable
from urllib.parse import quote, urlencode

import web_app as legacy


RequestContext = legacy.RequestContext
form_value = legacy.form_value
get_match_competition_name = legacy.get_match_competition_name
is_admin_user = legacy.is_admin_user
layout = legacy.layout
list_seasons = legacy.list_seasons
load_import_batches = legacy.load_import_batches
load_series_catalog = legacy.load_series_catalog
load_validated_data = legacy.load_validated_data
redirect = legacy.redirect
resolve_stage_options_for_scope = legacy.resolve_stage_options_for_scope
start_response_html = legacy.start_response_html


SCOPE_VIEW_PERMISSION_KEYS = (
    "competition_catalog_manage",
    "competition_season_manage",
    "match_schedule_manage",
    "match_result_manage",
    "match_import_manage",
    "dimension_data_manage",
    "season_asset_manage",
    "prediction_manage",
    "scope_audit_view",
)

CONSOLE_ROUTE_SEMANTICS = {
    "/console": "overview",
    "/console/matches": "match_search",
    "/console/matches/create": "single_match_create",
    "/console/matches/batch-create": "batch_schedule_create",
    "/console/imports": "import_activity",
    "/console/imports/data": "match_dimension_import",
    "/console/imports/matches": "match_import",
    "/console/imports/dimensions": "dimension_import",
    "/console/imports/assets": "season_asset_import",
}


def _query_value(ctx: RequestContext, key: str, default: str = "") -> str:
    return form_value(ctx.query, key, default).strip()


def _query_has(ctx: RequestContext, key: str) -> bool:
    return key in ctx.query


def _safe_positive_int(
    value: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _normalize_iso_date(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError:
        return ""


def _scope_key_for_competition(
    data: dict[str, Any],
    competition_name: str,
) -> str:
    entry = next(
        (
            item
            for item in load_series_catalog(data)
            if str(item.get("competition_name") or "").strip() == competition_name
        ),
        None,
    )
    if not entry:
        return ""
    builder = getattr(legacy, "build_manager_scope_key", None)
    region_name = str(entry.get("region_name") or "").strip()
    series_slug = str(entry.get("series_slug") or "").strip()
    if callable(builder):
        return str(builder(region_name, series_slug) or "").strip()
    return f"{region_name}::{series_slug}" if region_name and series_slug else ""


def _scope_label_for_competition(
    data: dict[str, Any],
    competition_name: str,
) -> str:
    entry = next(
        (
            item
            for item in load_series_catalog(data)
            if str(item.get("competition_name") or "").strip() == competition_name
        ),
        None,
    )
    if not entry:
        return competition_name
    region_name = str(entry.get("region_name") or "").strip()
    series_name = str(entry.get("series_name") or competition_name).strip()
    return " · ".join(part for part in (region_name, series_name) if part)


def _has_scope_permission(
    user: dict[str, Any] | None,
    data: dict[str, Any],
    competition_name: str,
    permission_key: str,
) -> bool:
    if is_admin_user(user):
        return True
    if not user or not competition_name:
        return False
    scope_key = _scope_key_for_competition(data, competition_name)
    helper = getattr(legacy, "user_has_scope_permission", None)
    if callable(helper) and scope_key:
        return bool(helper(user, scope_key, permission_key))
    # Compatibility for installations which have not migrated scope grants yet.
    can_manage = getattr(legacy, "can_manage_matches", None)
    return bool(
        callable(can_manage)
        and can_manage(user, data, competition_name)
    )


def _can_view_scope(
    user: dict[str, Any] | None,
    data: dict[str, Any],
    competition_name: str,
) -> bool:
    if is_admin_user(user):
        return True
    if not user or not competition_name:
        return False
    scope_key = _scope_key_for_competition(data, competition_name)
    helper = getattr(legacy, "user_has_any_scope_permission", None)
    if callable(helper) and scope_key:
        return bool(helper(user, scope_key, SCOPE_VIEW_PERMISSION_KEYS))
    return _has_scope_permission(user, data, competition_name, "match_result_manage")


def _all_competition_names(data: dict[str, Any]) -> list[str]:
    names: set[str] = {
        str(item.get("competition_name") or "").strip()
        for item in load_series_catalog(data)
        if str(item.get("competition_name") or "").strip()
    }
    names.update(
        get_match_competition_name(match)
        for match in data.get("matches", [])
        if get_match_competition_name(match)
    )
    return sorted(names)


def accessible_competitions(
    user: dict[str, Any] | None,
    data: dict[str, Any],
) -> list[str]:
    """Return series names visible in the console, never just UI-hidden."""

    return [
        competition_name
        for competition_name in _all_competition_names(data)
        if _can_view_scope(user, data, competition_name)
    ]


def _default_competition(
    data: dict[str, Any],
    competition_names: Iterable[str],
) -> str:
    allowed = set(competition_names)
    latest_match = max(
        (
            match
            for match in data.get("matches", [])
            if get_match_competition_name(match) in allowed
        ),
        key=lambda item: (
            str(item.get("played_on") or ""),
            int(item.get("round") or 0),
            int(item.get("game_no") or 0),
            str(item.get("match_id") or ""),
        ),
        default=None,
    )
    if latest_match:
        return get_match_competition_name(latest_match)
    return sorted(allowed)[0] if allowed else ""


def _seasons_for_competition(
    data: dict[str, Any],
    competition_name: str,
) -> list[str]:
    if not competition_name:
        return []
    try:
        ordered = list(
            list_seasons(
                data,
                competition_name,
                include_non_ongoing=True,
            )
        )
    except (KeyError, TypeError, ValueError):
        ordered = []
    seen = set(ordered)
    for match in sorted(
        data.get("matches", []),
        key=lambda item: str(item.get("played_on") or ""),
        reverse=True,
    ):
        if get_match_competition_name(match) != competition_name:
            continue
        season_name = str(match.get("season") or "").strip()
        if season_name and season_name not in seen:
            ordered.append(season_name)
            seen.add(season_name)
    return ordered


def _selected_scope(
    ctx: RequestContext,
    data: dict[str, Any],
    competition_names: list[str],
    *,
    allow_all: bool,
) -> tuple[str, str, str]:
    requested_competition = _query_value(ctx, "competition")
    explicit_competition = _query_has(ctx, "competition")
    warning = ""
    if requested_competition and requested_competition not in competition_names:
        warning = "你没有权限访问所选系列赛，已切换到默认授权范围。"
        requested_competition = ""
        explicit_competition = False
    if allow_all and explicit_competition and not requested_competition:
        selected_competition = ""
    else:
        selected_competition = requested_competition or _default_competition(
            data, competition_names
        )

    seasons = _seasons_for_competition(data, selected_competition)
    requested_season = _query_value(ctx, "season")
    if requested_season and requested_season not in seasons:
        warning = warning or "所选赛季不属于当前系列赛，已切换到默认赛季。"
        requested_season = ""
    if allow_all and _query_has(ctx, "season") and not requested_season:
        selected_season = ""
    else:
        selected_season = requested_season or (seasons[0] if seasons else "")
    return selected_competition, selected_season, warning


def _match_status(match: dict[str, Any]) -> str:
    return "pending" if str(match.get("format") or "").strip() == "待补录" else "recorded"


def _match_people_context(
    data: dict[str, Any],
    match: dict[str, Any],
    player_lookup: dict[str, str] | None = None,
    team_lookup: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    if player_lookup is None:
        player_lookup = {
            str(item.get("player_id") or "").strip(): str(
                item.get("display_name") or item.get("name") or ""
            ).strip()
            for item in data.get("players", [])
        }
    if team_lookup is None:
        team_lookup = {
            str(item.get("team_id") or "").strip(): str(
                item.get("name") or item.get("team_name") or ""
            ).strip()
            for item in data.get("teams", [])
        }
    player_names: list[str] = []
    team_names: list[str] = []
    for participant in match.get("players", []) or []:
        if not isinstance(participant, dict):
            continue
        player_id = str(participant.get("player_id") or "").strip()
        team_id = str(participant.get("team_id") or "").strip()
        player_name = str(
            participant.get("player_name")
            or player_lookup.get(player_id)
            or player_id
        ).strip()
        team_name = str(
            participant.get("team_name")
            or team_lookup.get(team_id)
            or team_id
        ).strip()
        if player_name and player_name not in player_names:
            player_names.append(player_name)
        if team_name and team_name not in team_names:
            team_names.append(team_name)
    return player_names, team_names


def _match_search_text(
    data: dict[str, Any],
    match: dict[str, Any],
    player_lookup: dict[str, str] | None = None,
    team_lookup: dict[str, str] | None = None,
) -> str:
    player_names, team_names = _match_people_context(
        data, match, player_lookup, team_lookup
    )
    values = [
        str(match.get("match_id") or ""),
        get_match_competition_name(match),
        str(match.get("season") or ""),
        str(match.get("played_on") or ""),
        str(match.get("group_label") or ""),
        str(match.get("table_label") or ""),
        str(match.get("format") or ""),
        *team_names,
        *player_names,
    ]
    return "\n".join(values).casefold()


def filter_console_matches(
    data: dict[str, Any],
    matches: Iterable[dict[str, Any]],
    *,
    competition_name: str = "",
    season_name: str = "",
    stage: str = "",
    date_from: str = "",
    date_to: str = "",
    record_status: str = "",
    team_score: str = "",
    keyword: str = "",
) -> list[dict[str, Any]]:
    """Apply console filters to an already permission-scoped match iterable."""

    normalized_keyword = str(keyword or "").strip().casefold()
    player_lookup = {
        str(item.get("player_id") or "").strip(): str(
            item.get("display_name") or item.get("name") or ""
        ).strip()
        for item in data.get("players", [])
    }
    team_lookup = {
        str(item.get("team_id") or "").strip(): str(
            item.get("name") or item.get("team_name") or ""
        ).strip()
        for item in data.get("teams", [])
    }
    filtered: list[dict[str, Any]] = []
    for match in matches:
        played_on = str(match.get("played_on") or "").strip()
        if competition_name and get_match_competition_name(match) != competition_name:
            continue
        if season_name and str(match.get("season") or "").strip() != season_name:
            continue
        if stage and str(match.get("stage") or "").strip() != stage:
            continue
        if date_from and played_on < date_from:
            continue
        if date_to and played_on > date_to:
            continue
        if record_status in {"pending", "recorded"} and _match_status(match) != record_status:
            continue
        if team_score == "included" and bool(match.get("exclude_from_team_scores")):
            continue
        if team_score == "excluded" and not bool(match.get("exclude_from_team_scores")):
            continue
        if normalized_keyword and normalized_keyword not in _match_search_text(
            data, match, player_lookup, team_lookup
        ):
            continue
        filtered.append(match)
    return sorted(
        filtered,
        key=lambda item: (
            str(item.get("played_on") or ""),
            int(item.get("round") or 0),
            int(item.get("game_no") or 0),
            str(item.get("match_id") or ""),
        ),
        reverse=True,
    )


def _summarize_names(names: list[str], visible: int) -> str:
    if not names:
        return "未设置"
    copy = "、".join(names[:visible])
    remaining = len(names) - visible
    return f"{copy} 等 {len(names)} 项" if remaining > 0 else copy


def _scope_switcher(
    ctx: RequestContext,
    data: dict[str, Any],
    competition_names: list[str],
    selected_competition: str,
    selected_season: str,
    *,
    action: str,
    allow_all: bool,
) -> str:
    season_map = {
        competition_name: _seasons_for_competition(data, competition_name)
        for competition_name in competition_names
    }
    serialized_season_map = escape(
        json.dumps(season_map, ensure_ascii=False, separators=(",", ":")),
        quote=True,
    )
    empty_season_label = "全部赛季" if allow_all else "请选择赛季"
    competition_options = []
    if allow_all:
        competition_options.append(
            f'<option value=""{" selected" if not selected_competition else ""}>全部授权系列赛</option>'
        )
    for competition_name in competition_names:
        selected = " selected" if competition_name == selected_competition else ""
        competition_options.append(
            f'<option value="{escape(competition_name)}"{selected}>{escape(_scope_label_for_competition(data, competition_name))}</option>'
        )
    season_options = [
        f'<option value=""{" selected" if not selected_season else ""}>{empty_season_label}</option>'
    ]
    for season_name in _seasons_for_competition(data, selected_competition):
        selected = " selected" if season_name == selected_season else ""
        season_options.append(
            f'<option value="{escape(season_name)}"{selected}>{escape(season_name)}</option>'
        )
    return f"""
    <form method="get" action="{escape(action)}" class="row g-2 align-items-end" data-console-scope-form data-console-season-map="{serialized_season_map}" data-console-season-empty-label="{escape(empty_season_label)}" data-console-allow-all="{'true' if allow_all else 'false'}">
      <div class="col-12 col-lg-7">
        <label class="form-label" for="console-competition">系列赛</label>
        <select class="form-select" id="console-competition" name="competition" data-console-competition-select>{''.join(competition_options)}</select>
      </div>
      <div class="col-8 col-lg-3">
        <label class="form-label" for="console-season">赛季</label>
        <select class="form-select" id="console-season" name="season" data-console-season-select{' disabled' if not selected_competition else ''}>{''.join(season_options)}</select>
      </div>
      <div class="col-4 col-lg-2 d-grid">
        <button class="btn btn-dark" type="submit">切换</button>
      </div>
    </form>
    <script>
      (function() {{
        document.querySelectorAll("[data-console-scope-form]").forEach(function(form) {{
          if (form.dataset.consoleScopeBound === "true") return;
          form.dataset.consoleScopeBound = "true";
          const competitionSelect = form.querySelector("[data-console-competition-select]");
          const seasonSelect = form.querySelector("[data-console-season-select]");
          if (!competitionSelect || !seasonSelect) return;

          let seasonMap = {{}};
          try {{
            seasonMap = JSON.parse(form.dataset.consoleSeasonMap || "{{}}");
          }} catch (_error) {{
            seasonMap = {{}};
          }}

          competitionSelect.addEventListener("change", function() {{
            const competitionName = competitionSelect.value;
            const seasons = Array.isArray(seasonMap[competitionName])
              ? seasonMap[competitionName]
              : [];
            const allowAll = form.dataset.consoleAllowAll === "true";
            const emptyLabel = form.dataset.consoleSeasonEmptyLabel || "请选择赛季";
            seasonSelect.replaceChildren();

            const emptyOption = document.createElement("option");
            emptyOption.value = "";
            emptyOption.textContent = emptyLabel;
            seasonSelect.appendChild(emptyOption);
            seasons.forEach(function(seasonName) {{
              const option = document.createElement("option");
              option.value = seasonName;
              option.textContent = seasonName;
              seasonSelect.appendChild(option);
            }});

            seasonSelect.disabled = !competitionName;
            seasonSelect.value = allowAll ? "" : (seasons[0] || "");
          }});
        }});
      }})();
    </script>
    """


def _task_link(
    label: str,
    copy: str,
    href: str,
) -> str:
    return f"""
    <div class="col-12 col-md-6 col-xl-4">
      <a class="team-link-card shadow-sm p-3 h-100 d-block text-decoration-none" href="{escape(href)}">
        <h3 class="h6 text-dark mb-1">{escape(label)}</h3>
        <p class="small text-secondary mb-0">{escape(copy)}</p>
      </a>
    </div>
    """


def build_operation_task_links(
    user: dict[str, Any] | None,
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
) -> str:
    query = urlencode(
        {
            key: value
            for key, value in {
                "competition": competition_name,
                "season": season_name,
            }.items()
            if value
        }
    )

    def href(path: str) -> str:
        return f"{path}?{query}" if query else path

    links = [
        _task_link("搜索与编辑比赛", "按编号、战队、选手或日期定位比赛。", href("/console/matches"))
    ]
    if competition_name and _has_scope_permission(
        user, data, competition_name, "match_schedule_manage"
    ):
        links.extend(
            [
                _task_link("新增单场比赛", "录入一场比赛及完整赛果。", href("/console/matches/create")),
                _task_link("批量创建赛程", "一次创建多场待补录比赛。", href("/console/matches/batch-create")),
            ]
        )
    can_import_matches = bool(
        competition_name
        and _has_scope_permission(user, data, competition_name, "match_import_manage")
    )
    can_import_dimensions = bool(
        competition_name
        and _has_scope_permission(user, data, competition_name, "dimension_data_manage")
    )
    if can_import_matches or can_import_dimensions:
        links.append(
            _task_link(
                "上传比赛与维度数据",
                "先导入比赛结果，成功后再上传对应赛季维度。",
                href("/console/imports/data"),
            )
        )
    if competition_name and _has_scope_permission(
        user, data, competition_name, "season_asset_manage"
    ):
        links.append(
            _task_link("上传赛季素材", "集中维护战队图标和选手头像。", href("/console/imports/assets"))
        )
    if competition_name and _has_scope_permission(
        user, data, competition_name, "prediction_manage"
    ):
        prediction_query = urlencode(
            {
                "scenario_competition": competition_name,
                "scenario_season": season_name,
            }
        )
        links.append(
            _task_link(
                "维护胜率预测",
                "按赛季录入和发布预测名单。",
                f"/prediction-admin?{prediction_query}",
            )
        )
    return ''.join(links)


def _operation_toolbar_links(
    user: dict[str, Any] | None,
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
) -> str:
    params = {
        key: value
        for key, value in {
            "competition": competition_name,
            "season": season_name,
        }.items()
        if value
    }

    def href(path: str) -> str:
        return path + (f"?{urlencode(params)}" if params else "")

    links: list[str] = []
    if competition_name and _has_scope_permission(
        user, data, competition_name, "match_schedule_manage"
    ):
        links.append(
            f'<a class="btn btn-dark" href="{escape(href("/console/matches/create"))}">新增比赛</a>'
        )
        links.append(
            f'<a class="btn btn-outline-dark" href="{escape(href("/console/matches/batch-create"))}">批量创建</a>'
        )
    can_import_matches = bool(
        competition_name
        and _has_scope_permission(user, data, competition_name, "match_import_manage")
    )
    can_import_dimensions = bool(
        competition_name
        and _has_scope_permission(user, data, competition_name, "dimension_data_manage")
    )
    if can_import_matches or can_import_dimensions:
        links.append(
            f'<a class="btn btn-outline-dark" href="{escape(href("/console/imports/data"))}">上传比赛与维度</a>'
        )
    return ''.join(links)


def _batch_competitions(batch: dict[str, Any]) -> set[str]:
    metadata = batch.get("metadata")
    if not isinstance(metadata, dict):
        return set()
    names = {
        str(metadata.get("competition_name") or "").strip(),
        str(metadata.get("competition") or "").strip(),
    }
    for key in ("matched_scopes", "scopes"):
        items = metadata.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                names.add(str(item.get("competition_name") or "").strip())
    return {name for name in names if name}


def _batch_scope_labels(batch: dict[str, Any]) -> list[tuple[str, str]]:
    metadata = batch.get("metadata")
    if not isinstance(metadata, dict):
        return []
    labels: list[tuple[str, str]] = []

    def add_scope(raw: object) -> None:
        if not isinstance(raw, dict):
            return
        competition_name = str(
            raw.get("competition_name") or raw.get("competition") or ""
        ).strip()
        season_name = str(raw.get("season_name") or raw.get("season") or "").strip()
        label = (competition_name, season_name)
        if any(label) and label not in labels:
            labels.append(label)

    for key in ("matched_scopes", "scopes"):
        raw_scopes = metadata.get(key)
        if isinstance(raw_scopes, list):
            for raw_scope in raw_scopes:
                add_scope(raw_scope)
    add_scope(metadata)
    preflight = metadata.get("preflight")
    if isinstance(preflight, dict):
        payload = preflight.get("payload")
        if isinstance(payload, dict):
            raw_scopes = payload.get("matched_scopes")
            if isinstance(raw_scopes, list):
                for raw_scope in raw_scopes:
                    add_scope(raw_scope)
    return labels


def _batch_scope_keys(batch: dict[str, Any]) -> set[str]:
    metadata = batch.get("metadata")
    if not isinstance(metadata, dict):
        return set()
    raw_scope_keys = metadata.get("permission_scope_keys")
    if not isinstance(raw_scope_keys, list):
        return set()
    return {
        str(scope_key or "").strip()
        for scope_key in raw_scope_keys
        if str(scope_key or "").strip()
    }


def _batch_action_permission(batch: dict[str, Any]) -> str:
    return {
        "matches.import_excel": "match_import_manage",
        "dimension.import_excel": "dimension_data_manage",
        "team_logo.import_excel": "season_asset_manage",
        "player_photo.import_zip": "season_asset_manage",
        "matches.batch_create": "match_schedule_manage",
    }.get(str(batch.get("action") or "").strip(), "scope_audit_view")


def _visible_import_batches(
    ctx: RequestContext,
    data: dict[str, Any],
    accessible_names: set[str],
) -> list[dict[str, Any]]:
    username = str((ctx.current_user or {}).get("username") or "").strip()
    visible: list[dict[str, Any]] = []
    for batch in load_import_batches():
        scope_keys = _batch_scope_keys(batch)
        if is_admin_user(ctx.current_user):
            visible.append(batch)
        elif (
            scope_keys
            and all(
                legacy.user_has_scope_permission(
                    ctx.current_user,
                    scope_key,
                    "scope_audit_view",
                )
                or legacy.user_has_scope_permission(
                    ctx.current_user,
                    scope_key,
                    _batch_action_permission(batch),
                )
                for scope_key in scope_keys
            )
        ):
            visible.append(batch)
        elif (
            not scope_keys
            and str(batch.get("created_by") or "").strip() == username
        ):
            # Old import records did not persist scope metadata. Preserve the
            # creator-only fallback for those records, but never let ownership
            # bypass current scope authorization once scope keys are known.
            visible.append(batch)
    return visible


def _import_status_label(status: str) -> str:
    return {
        "awaiting_confirmation": "待确认",
        "queued": "排队中",
        "running": "处理中",
        "succeeded": "成功",
        "failed": "失败",
        "cancelled": "已取消",
        "stale": "需重新预检",
        "rolled_back": "已回滚",
    }.get(str(status or "").strip(), str(status or "").strip() or "未知")


def get_console_page(ctx: RequestContext, alert: str = "") -> str:
    data = load_validated_data()
    competition_names = accessible_competitions(ctx.current_user, data)
    selected_competition, selected_season, scope_warning = _selected_scope(
        ctx,
        data,
        competition_names,
        allow_all=False,
    )
    scope_matches = filter_console_matches(
        data,
        (
            match
            for match in data.get("matches", [])
            if get_match_competition_name(match) in competition_names
        ),
        competition_name=selected_competition,
        season_name=selected_season,
    )
    pending_matches = [match for match in scope_matches if _match_status(match) == "pending"]
    import_batches = _visible_import_batches(ctx, data, set(competition_names))
    active_batches = [
        item
        for item in import_batches
        if str(item.get("status") or "").strip()
        in {"awaiting_confirmation", "queued", "running", "stale"}
    ]
    recent_batches = import_batches[:5]

    pending_rows = []
    for match in pending_matches[:6]:
        competition_name = get_match_competition_name(match)
        edit_link = ""
        if _has_scope_permission(
            ctx.current_user, data, competition_name, "match_result_manage"
        ):
            edit_link = (
                f'<a class="btn btn-sm btn-dark" href="/matches/{quote(str(match.get("match_id") or ""))}/edit?next={quote("/console")}">补录</a>'
            )
        pending_rows.append(
            f"""
            <tr>
              <td><code>{escape(str(match.get('match_id') or ''))}</code></td>
              <td>{escape(str(match.get('played_on') or ''))}</td>
              <td>{escape(str(match.get('group_label') or '未设置'))} / {escape(str(match.get('table_label') or '未设置'))}</td>
              <td>{edit_link or '<span class="small text-secondary">只读</span>'}</td>
            </tr>
            """
        )

    batch_rows = []
    for item in recent_batches:
        scope_labels = _batch_scope_labels(item)
        scope_html = "".join(
            f'<div>{escape(competition_name or "未记录赛事")}'
            f'<span class="small text-secondary"> / {escape(season_name or "未记录赛季")}</span></div>'
            for competition_name, season_name in scope_labels
        ) or '<span class="small text-secondary">未记录</span>'
        batch_rows.append(
            f"""
            <tr>
              <td><code>{escape(str(item.get('batch_id') or ''))}</code></td>
              <td>{escape(str(item.get('label') or item.get('action') or '导入任务'))}</td>
              <td>{scope_html}</td>
              <td>{escape(_import_status_label(str(item.get('status') or '')))}</td>
              <td class="small text-secondary">{escape(str(item.get('created_at') or ''))}</td>
            </tr>
            """
        )

    warning_html = (
        f'<div class="alert alert-warning" role="alert">{escape(scope_warning)}</div>'
        if scope_warning
        else ""
    )
    body = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-3">
      <div class="d-flex flex-column flex-xl-row justify-content-between gap-3 mb-3">
        <div>
          <div class="eyebrow mb-2">后台工作台</div>
          <h1 class="h3 mb-1">控制台</h1>
          <p class="small text-secondary mb-0">选择当前运营范围，再进入对应任务。</p>
        </div>
        <div class="flex-grow-1" style="max-width: 760px">
          {_scope_switcher(ctx, data, competition_names, selected_competition, selected_season, action='/console', allow_all=False)}
        </div>
      </div>
      {warning_html}
      <div class="row g-2">
        <div class="col-6 col-xl-3"><div class="border rounded p-3 h-100"><div class="small text-secondary">当前赛季比赛</div><div class="h4 mb-0 mt-1">{len(scope_matches)}</div></div></div>
        <div class="col-6 col-xl-3"><div class="border rounded p-3 h-100"><div class="small text-secondary">待补录</div><div class="h4 mb-0 mt-1">{len(pending_matches)}</div></div></div>
        <div class="col-6 col-xl-3"><div class="border rounded p-3 h-100"><div class="small text-secondary">活动导入任务</div><div class="h4 mb-0 mt-1">{len(active_batches)}</div></div></div>
        <div class="col-6 col-xl-3"><div class="border rounded p-3 h-100"><div class="small text-secondary">授权系列赛</div><div class="h4 mb-0 mt-1">{len(competition_names)}</div></div></div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-3">
      <div class="d-flex justify-content-between align-items-end gap-3 mb-3">
        <div><h2 class="h5 mb-1">常用操作</h2><p class="small text-secondary mb-0">只显示当前账号在所选系列赛可执行的任务。</p></div>
      </div>
      <div class="row g-2">{build_operation_task_links(ctx.current_user, data, selected_competition, selected_season)}</div>
    </section>
    <div class="row g-3">
      <div class="col-12 col-xl-7">
        <section class="panel shadow-sm p-3 p-lg-4 h-100">
          <div class="d-flex justify-content-between align-items-end gap-3 mb-2">
            <div><h2 class="h5 mb-1">待补录比赛</h2><p class="small text-secondary mb-0">按比赛日期倒序显示。</p></div>
            <a class="btn btn-sm btn-outline-dark" href="/console/matches?{urlencode({'competition': selected_competition, 'season': selected_season, 'status': 'pending'})}">查看全部</a>
          </div>
          <div class="table-responsive"><table class="table table-sm align-middle mb-0"><thead><tr><th>比赛编号</th><th>日期</th><th>场地</th><th>操作</th></tr></thead><tbody>{''.join(pending_rows) or '<tr><td colspan="4" class="text-secondary">当前范围没有待补录比赛。</td></tr>'}</tbody></table></div>
        </section>
      </div>
      <div class="col-12 col-xl-5">
        <section class="panel shadow-sm p-3 p-lg-4 h-100">
          <div class="d-flex justify-content-between align-items-end gap-3 mb-2">
            <div><h2 class="h5 mb-1">最近导入</h2><p class="small text-secondary mb-0">显示当前账号可见的任务。</p></div>
            <a class="btn btn-sm btn-outline-dark" href="/console/imports">导入记录</a>
          </div>
          <div class="table-responsive"><table class="table table-sm align-middle mb-0"><thead><tr><th>批次</th><th>类型</th><th>赛事 / 赛季</th><th>状态</th><th>创建时间</th></tr></thead><tbody>{''.join(batch_rows) or '<tr><td colspan="5" class="text-secondary">暂无导入记录。</td></tr>'}</tbody></table></div>
        </section>
      </div>
    </div>
    """
    return layout("控制台", body, ctx, alert=alert)


def _build_filter_path(values: dict[str, str], page: int) -> str:
    params = {
        key: value
        for key, value in {**values, "page": str(page)}.items()
        if value and not (key == "page" and value == "1")
    }
    return "/console/matches" + (f"?{urlencode(params)}" if params else "")


def _pagination_html(
    values: dict[str, str],
    page: int,
    page_count: int,
    total: int,
    start_index: int,
    end_index: int,
) -> str:
    if not total:
        return '<div class="small text-secondary mt-3">当前筛选下没有比赛。</div>'
    links: list[str] = []

    def item(label: str, target: int, *, disabled: bool = False, active: bool = False) -> str:
        if disabled:
            return f'<li class="page-item disabled"><span class="page-link">{escape(label)}</span></li>'
        current = " active" if active else ""
        aria = ' aria-current="page"' if active else ""
        return f'<li class="page-item{current}"><a class="page-link" href="{escape(_build_filter_path(values, target))}"{aria}>{escape(label)}</a></li>'

    links.append(item("上一页", page - 1, disabled=page <= 1))
    window_start = max(1, page - 2)
    window_end = min(page_count, page + 2)
    if window_start > 1:
        links.append(item("1", 1, active=page == 1))
        if window_start > 2:
            links.append('<li class="page-item disabled"><span class="page-link">…</span></li>')
    for page_no in range(window_start, window_end + 1):
        links.append(item(str(page_no), page_no, active=page_no == page))
    if window_end < page_count:
        if window_end < page_count - 1:
            links.append('<li class="page-item disabled"><span class="page-link">…</span></li>')
        links.append(item(str(page_count), page_count, active=page_count == page))
    links.append(item("下一页", page + 1, disabled=page >= page_count))
    return f"""
    <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-2 mt-3">
      <div class="small text-secondary">显示 {start_index + 1}-{end_index} 场，共 {total} 场</div>
      <nav aria-label="比赛列表分页"><ul class="pagination pagination-sm mb-0">{''.join(links)}</ul></nav>
    </div>
    """


def get_console_matches_page(ctx: RequestContext, alert: str = "") -> str:
    data = load_validated_data()
    competition_names = accessible_competitions(ctx.current_user, data)
    selected_competition, selected_season, scope_warning = _selected_scope(
        ctx,
        data,
        competition_names,
        allow_all=True,
    )

    stage = _query_value(ctx, "stage")
    raw_date_from = _query_value(ctx, "date_from")
    raw_date_to = _query_value(ctx, "date_to")
    date_from = _normalize_iso_date(raw_date_from)
    date_to = _normalize_iso_date(raw_date_to)
    record_status = _query_value(ctx, "status")
    if record_status not in {"", "pending", "recorded"}:
        record_status = ""
    team_score = _query_value(ctx, "team_score")
    if team_score not in {"", "included", "excluded"}:
        team_score = ""
    keyword = _query_value(ctx, "q")
    per_page = _safe_positive_int(_query_value(ctx, "per_page", "25"), 25, minimum=10, maximum=100)
    if per_page not in {10, 25, 50, 100}:
        per_page = 25
    requested_page = _safe_positive_int(_query_value(ctx, "page", "1"), 1, minimum=1, maximum=100000)

    authorized_matches = [
        match
        for match in data.get("matches", [])
        if get_match_competition_name(match) in competition_names
    ]
    filtered_matches = filter_console_matches(
        data,
        authorized_matches,
        competition_name=selected_competition,
        season_name=selected_season,
        stage=stage,
        date_from=date_from,
        date_to=date_to,
        record_status=record_status,
        team_score=team_score,
        keyword=keyword,
    )
    total = len(filtered_matches)
    page_count = max(1, (total + per_page - 1) // per_page)
    page = min(requested_page, page_count)
    start_index = (page - 1) * per_page
    page_matches = filtered_matches[start_index : start_index + per_page]
    end_index = min(start_index + per_page, total)

    stage_options: dict[str, str] = {}
    if selected_competition and selected_season:
        try:
            stage_options.update(
                resolve_stage_options_for_scope(
                    data, selected_competition, selected_season
                )
            )
        except (KeyError, TypeError, ValueError):
            pass
    for match in authorized_matches:
        stage_key = str(match.get("stage") or "").strip()
        if stage_key:
            stage_options.setdefault(stage_key, stage_key)

    rows = []
    player_lookup = {
        str(item.get("player_id") or "").strip(): str(
            item.get("display_name") or item.get("name") or ""
        ).strip()
        for item in data.get("players", [])
    }
    team_lookup = {
        str(item.get("team_id") or "").strip(): str(
            item.get("name") or item.get("team_name") or ""
        ).strip()
        for item in data.get("teams", [])
    }
    for match in page_matches:
        competition_name = get_match_competition_name(match)
        match_id = str(match.get("match_id") or "").strip()
        player_names, team_names = _match_people_context(
            data, match, player_lookup, team_lookup
        )
        stage_key = str(match.get("stage") or "").strip()
        stage_label = stage_options.get(stage_key, stage_key or "未设置")
        return_path = _build_filter_path(
            {
                "competition": selected_competition,
                "season": selected_season,
                "stage": stage,
                "date_from": date_from,
                "date_to": date_to,
                "status": record_status,
                "team_score": team_score,
                "q": keyword,
                "per_page": str(per_page),
            },
            page,
        )
        edit_link = ""
        if _has_scope_permission(
            ctx.current_user, data, competition_name, "match_result_manage"
        ):
            edit_link = f'<a class="btn btn-sm btn-dark" href="/matches/{quote(match_id)}/edit?next={quote(return_path)}">编辑</a>'
        rows.append(
            f"""
            <tr{' class="table-active"' if keyword and keyword.casefold() == match_id.casefold() else ''}>
              <td><a href="/matches/{quote(match_id)}?next={quote(return_path)}"><code>{escape(match_id)}</code></a></td>
              <td><div>{escape(competition_name)}</div><div class="small text-secondary">{escape(str(match.get('season') or ''))}</div></td>
              <td><div>{escape(str(match.get('played_on') or ''))}</div><div class="small text-secondary">{escape(stage_label)} · 第 {int(match.get('round') or 0)} 轮 / 第 {int(match.get('game_no') or 0)} 局</div></td>
              <td><div>{escape(str(match.get('group_label') or '未设置'))}</div><div class="small text-secondary">{escape(str(match.get('table_label') or '未设置'))} · {escape(str(match.get('format') or '未设置'))}</div></td>
              <td><div>{escape(_summarize_names(team_names, 2))}</div><div class="small text-secondary">{escape(_summarize_names(player_names, 3))}</div></td>
              <td><div>{'待补录' if _match_status(match) == 'pending' else '已录入'}</div><div class="small text-secondary">{'不计战队总分' if match.get('exclude_from_team_scores') else '计入战队总分'}</div></td>
              <td><div class="d-flex flex-wrap gap-1"><a class="btn btn-sm btn-outline-dark" href="/matches/{quote(match_id)}?next={quote(return_path)}">详情</a>{edit_link}</div></td>
            </tr>
            """
        )

    competition_options = [
        f'<option value=""{" selected" if not selected_competition else ""}>全部授权系列赛</option>'
    ]
    for competition_name in competition_names:
        selected = " selected" if competition_name == selected_competition else ""
        competition_options.append(
            f'<option value="{escape(competition_name)}"{selected}>{escape(_scope_label_for_competition(data, competition_name))}</option>'
        )
    season_options = [
        f'<option value=""{" selected" if not selected_season else ""}>全部赛季</option>'
    ]
    for season_name in _seasons_for_competition(data, selected_competition):
        selected = " selected" if season_name == selected_season else ""
        season_options.append(f'<option value="{escape(season_name)}"{selected}>{escape(season_name)}</option>')
    stage_option_html = ['<option value="">全部赛段</option>']
    for value, label in stage_options.items():
        selected = " selected" if value == stage else ""
        stage_option_html.append(f'<option value="{escape(value)}"{selected}>{escape(label)}</option>')

    filter_values = {
        "competition": selected_competition,
        "season": selected_season,
        "stage": stage,
        "date_from": date_from,
        "date_to": date_to,
        "status": record_status,
        "team_score": team_score,
        "q": keyword,
        "per_page": str(per_page),
    }
    pagination = _pagination_html(
        filter_values, page, page_count, total, start_index, end_index
    )
    warnings = []
    if scope_warning:
        warnings.append(scope_warning)
    if raw_date_from and not date_from:
        warnings.append("开始日期格式无效，已忽略该条件。")
    if raw_date_to and not date_to:
        warnings.append("结束日期格式无效，已忽略该条件。")
    if date_from and date_to and date_from > date_to:
        warnings.append("开始日期不能晚于结束日期。")
    warning_html = ''.join(
        f'<div class="alert alert-warning py-2" role="alert">{escape(message)}</div>'
        for message in warnings
    )
    exact_match = next(
        (
            match
            for match in filtered_matches
            if keyword and str(match.get("match_id") or "").casefold() == keyword.casefold()
        ),
        None,
    )
    exact_html = ""
    if exact_match:
        exact_id = str(exact_match.get("match_id") or "")
        exact_html = f'<div class="alert alert-light border py-2 d-flex flex-wrap justify-content-between align-items-center gap-2"><span>已精确匹配比赛编号 <code>{escape(exact_id)}</code></span><a class="btn btn-sm btn-outline-dark" href="/matches/{quote(exact_id)}">打开比赛</a></div>'

    body = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-3">
      <div class="d-flex flex-column flex-xl-row justify-content-between align-items-xl-end gap-3 mb-3">
        <div><div class="eyebrow mb-2">比赛运营</div><h1 class="h3 mb-1">比赛搜索</h1><p class="small text-secondary mb-0">结果已按账号授权范围过滤，搜索支持比赛编号、战队、选手、日期、分组、房间和板型。</p></div>
        <div class="d-flex flex-wrap gap-2"><a class="btn btn-outline-dark" href="/console">返回工作台</a>{_operation_toolbar_links(ctx.current_user, data, selected_competition, selected_season)}</div>
      </div>
      {warning_html}{exact_html}
      <form method="get" action="/console/matches">
        <div class="row g-2">
          <div class="col-12 col-lg-4"><label class="form-label" for="match-q">搜索</label><input class="form-control" id="match-q" name="q" value="{escape(keyword)}" placeholder="比赛编号、战队、选手、日期、分组、房间或板型"></div>
          <div class="col-12 col-md-6 col-lg-4"><label class="form-label" for="match-competition">系列赛</label><select class="form-select" id="match-competition" name="competition">{''.join(competition_options)}</select></div>
          <div class="col-12 col-md-6 col-lg-2"><label class="form-label" for="match-season">赛季</label><select class="form-select" id="match-season" name="season"{' disabled' if not selected_competition else ''}>{''.join(season_options)}</select></div>
          <div class="col-12 col-md-6 col-lg-2"><label class="form-label" for="match-stage">赛段</label><select class="form-select" id="match-stage" name="stage">{''.join(stage_option_html)}</select></div>
          <div class="col-6 col-md-3 col-lg-2"><label class="form-label" for="match-date-from">开始日期</label><input class="form-control" type="date" id="match-date-from" name="date_from" value="{escape(date_from)}"></div>
          <div class="col-6 col-md-3 col-lg-2"><label class="form-label" for="match-date-to">结束日期</label><input class="form-control" type="date" id="match-date-to" name="date_to" value="{escape(date_to)}"></div>
          <div class="col-6 col-md-3 col-lg-2"><label class="form-label" for="match-status">录入状态</label><select class="form-select" id="match-status" name="status"><option value="">全部</option><option value="pending"{' selected' if record_status == 'pending' else ''}>待补录</option><option value="recorded"{' selected' if record_status == 'recorded' else ''}>已录入</option></select></div>
          <div class="col-6 col-md-3 col-lg-2"><label class="form-label" for="match-team-score">战队计分</label><select class="form-select" id="match-team-score" name="team_score"><option value="">全部</option><option value="included"{' selected' if team_score == 'included' else ''}>计入战队总分</option><option value="excluded"{' selected' if team_score == 'excluded' else ''}>不计战队总分</option></select></div>
          <div class="col-6 col-md-3 col-lg-2"><label class="form-label" for="match-per-page">每页</label><select class="form-select" id="match-per-page" name="per_page">{''.join(f'<option value="{size}"{" selected" if size == per_page else ""}>{size} 场</option>' for size in (10, 25, 50, 100))}</select></div>
          <div class="col-6 col-md-3 col-lg-2 d-flex align-items-end gap-2"><button class="btn btn-dark flex-grow-1" type="submit">查询</button><a class="btn btn-outline-dark" href="/console/matches">重置</a></div>
        </div>
      </form>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-wrap justify-content-between align-items-end gap-2 mb-2"><div><h2 class="h5 mb-1">比赛列表</h2><p class="small text-secondary mb-0">共 {total} 场；最近比赛优先。</p></div></div>
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead><tr><th>编号</th><th>赛事/赛季</th><th>日期/赛段</th><th>分组/场地</th><th>战队/选手</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>{''.join(rows) or '<tr><td colspan="7" class="text-secondary">当前筛选下没有比赛。</td></tr>'}</tbody>
        </table>
      </div>
      {pagination}
    </section>
    """
    return layout("比赛搜索", body, ctx, alert=alert)


def _method_not_allowed(ctx: RequestContext, start_response):
    return start_response_html(
        start_response,
        "405 Method Not Allowed",
        layout(
            "请求方式不支持",
            '<div class="alert alert-danger">此控制台页面仅支持 GET 请求。</div>',
            ctx,
        ),
        headers=[("Allow", "GET")],
    )


def _require_console_user(ctx: RequestContext, start_response):
    if not ctx.current_user:
        next_path = ctx.path
        if ctx.query:
            next_path += "?" + urlencode(
                {key: values[0] for key, values in ctx.query.items() if values}
            )
        return redirect(start_response, "/login?next=" + quote(next_path))
    data = load_validated_data()
    if is_admin_user(ctx.current_user) or accessible_competitions(ctx.current_user, data):
        return None
    return start_response_html(
        start_response,
        "403 Forbidden",
        layout(
            "没有权限",
            '<div class="alert alert-danger">当前账号没有可访问的赛区运营范围。</div>',
            ctx,
        ),
    )


def handle_console(ctx: RequestContext, start_response):
    guard = _require_console_user(ctx, start_response)
    if guard is not None:
        return guard
    if ctx.method != "GET":
        return _method_not_allowed(ctx, start_response)
    return start_response_html(start_response, "200 OK", get_console_page(ctx))


def handle_console_matches(ctx: RequestContext, start_response):
    guard = _require_console_user(ctx, start_response)
    if guard is not None:
        return guard
    if ctx.method != "GET":
        return _method_not_allowed(ctx, start_response)
    return start_response_html(
        start_response,
        "200 OK",
        get_console_matches_page(ctx),
    )


def handle_console_route(ctx: RequestContext, start_response):
    """Dispatch routes owned here; return ``None`` for adjacent task routes."""

    handlers: dict[str, Callable[[RequestContext, Any], Any]] = {
        "/console": handle_console,
        "/console/matches": handle_console_matches,
    }
    handler = handlers.get(ctx.path)
    return handler(ctx, start_response) if handler else None


__all__ = [
    "CONSOLE_ROUTE_SEMANTICS",
    "SCOPE_VIEW_PERMISSION_KEYS",
    "accessible_competitions",
    "build_operation_task_links",
    "filter_console_matches",
    "get_console_matches_page",
    "get_console_page",
    "handle_console",
    "handle_console_matches",
    "handle_console_route",
]
