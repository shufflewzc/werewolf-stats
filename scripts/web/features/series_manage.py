from __future__ import annotations

import json

import web_app as legacy

RequestContext = legacy.RequestContext
DEFAULT_REGION_NAME = legacy.DEFAULT_REGION_NAME
audit_action = legacy.audit_action
build_competition_catalog_rows = legacy.build_competition_catalog_rows
build_scoped_path = legacy.build_scoped_path
build_series_manage_path = legacy.build_series_manage_path
can_manage_competition_catalog = legacy.can_manage_competition_catalog
can_manage_competition_seasons = legacy.can_manage_competition_seasons
can_manage_series_entry = legacy.can_manage_series_entry
china_today_label = legacy.china_today_label
escape = legacy.escape
format_datetime_local_label = legacy.format_datetime_local_label
form_value = legacy.form_value
get_match_competition_name = legacy.get_match_competition_name
get_season_entries_for_series = legacy.get_season_entries_for_series
get_season_entry = legacy.get_season_entry
get_series_entry_by_competition = legacy.get_series_entry_by_competition
is_admin_user = legacy.is_admin_user
layout = legacy.layout
load_membership_requests = legacy.load_membership_requests
load_season_catalog = legacy.load_season_catalog
load_series_catalog = legacy.load_series_catalog
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
normalize_season_catalog_entry = legacy.normalize_season_catalog_entry
normalize_scoring_rule = legacy.normalize_scoring_rule
normalize_series_catalog_entry = legacy.normalize_series_catalog_entry
merge_scoring_rules = legacy.merge_scoring_rules
parse_china_datetime = legacy.parse_china_datetime
require_competition_catalog_manager = legacy.require_competition_catalog_manager
require_competition_season_manager = legacy.require_competition_season_manager
save_membership_requests = legacy.save_membership_requests
save_repository_state = legacy.save_repository_state
save_season_catalog = legacy.save_season_catalog
save_series_catalog = legacy.save_series_catalog
season_status_label = legacy.season_status_label
scoring_rule_component_fields = legacy.scoring_rule_component_fields
version_scoring_rule = legacy.version_scoring_rule
start_response_html = legacy.start_response_html
STAGE_OPTIONS = legacy.STAGE_OPTIONS
SCORING_RULE_COMPONENTS = legacy.SCORING_RULE_COMPONENTS
MATCH_SCORE_MODEL_OPTIONS = legacy.MATCH_SCORE_MODEL_OPTIONS
MAX_SCORING_RULE_COMPONENTS = legacy.MAX_SCORING_RULE_COMPONENTS

RESERVED_EXCEL_SCORE_LABELS = {
    "座位号",
    "战队名",
    "战队",
    "选手",
    "选手名",
    "局号",
    "比赛编号",
    "局次",
    "赛段",
    "轮次",
    "分组",
    "房间",
    "身份",
    "角色",
    "单局积分",
    "阵营",
    "结果",
    "站边",
    "赛事名称",
    "赛季",
    "日期",
    "板型",
    "时长",
    "胜利阵营",
    "积分模型",
    "MVP",
    "SVP",
    "背锅",
    "备注",
    "seat",
    "team_name",
    "player_name",
    "match_id",
    "game_no",
    "stage",
    "round",
    "group_label",
    "room_label",
    "table_label",
    "role",
    "points_earned",
    "camp",
    "result",
    "stance_result",
    "competition_name",
    "season_name",
    "played_on",
    "format",
    "duration_minutes",
    "winning_camp",
    "score_model",
    "mvp_player_name",
    "svp_player_name",
    "scapegoat_player_name",
    "notes",
}


def build_stage_window_form_values(entry: dict[str, str] | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    windows = entry.get("stage_windows", []) if isinstance(entry, dict) else []
    window_by_stage = {
        str(item.get("stage") or "").strip(): item
        for item in windows
        if isinstance(item, dict)
    }
    for stage_key in STAGE_OPTIONS:
        window = window_by_stage.get(stage_key, {})
        values[f"stage_{stage_key}_start_at"] = str(window.get("start_at") or "")
        values[f"stage_{stage_key}_end_at"] = str(window.get("end_at") or "")
    return values


def collect_stage_windows_from_form(form: dict[str, list[str]]) -> list[dict[str, str]]:
    windows: list[dict[str, str]] = []
    for stage_key in STAGE_OPTIONS:
        start_at = form_value(form, f"stage_{stage_key}_start_at").strip()
        end_at = form_value(form, f"stage_{stage_key}_end_at").strip()
        if not start_at and not end_at:
            continue
        windows.append({"stage": stage_key, "start_at": start_at, "end_at": end_at})
    return windows


def validate_stage_windows(stage_windows: list[dict[str, str]]) -> str:
    for window in stage_windows:
        stage_key = str(window.get("stage") or "").strip()
        stage_label = STAGE_OPTIONS.get(stage_key, stage_key or "赛段")
        start_at = str(window.get("start_at") or "").strip()
        end_at = str(window.get("end_at") or "").strip()
        if not start_at or not end_at:
            return f"{stage_label} 需要同时填写开始时间和结束时间。"
        normalized_start = parse_china_datetime(start_at)
        normalized_end = parse_china_datetime(end_at)
        if not normalized_start or not normalized_end:
            return f"{stage_label} 的起止时间格式无效。"
        if normalized_start > normalized_end:
            return f"{stage_label} 开始时间不能晚于结束时间。"
    return ""


def render_stage_window_cards(entry: dict[str, object]) -> str:
    windows = entry.get("stage_windows", []) if isinstance(entry, dict) else []
    window_by_stage = {
        str(item.get("stage") or "").strip(): item
        for item in windows
        if isinstance(item, dict)
    }
    cards: list[str] = []
    for stage_key, stage_label in STAGE_OPTIONS.items():
        window = window_by_stage.get(stage_key)
        period = (
            f"{format_datetime_local_label(str(window.get('start_at') or ''))} - "
            f"{format_datetime_local_label(str(window.get('end_at') or ''))}"
            if window
            else "未设置"
        )
        cards.append(
            f"""
            <div class="col-12 col-lg-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="small text-secondary">{escape(stage_label)}</div>
                <div class="fw-semibold mt-1">{escape(period)}</div>
              </div>
            </div>
            """
        )
    return "".join(cards)


def collect_scoring_rule_from_form(
    form: dict[str, list[str]],
    prefix: str,
    *,
    allow_inherit: bool = False,
) -> dict[str, object]:
    if allow_inherit and form_value(form, f"{prefix}_scoring_inherit").strip() in {"1", "true", "on", "yes"}:
        return {"inherit": True}
    components = []
    used_keys: set[str] = set()
    for field_name, default_label in SCORING_RULE_COMPONENTS:
        enabled = form_value(form, f"{prefix}_score_{field_name}_enabled").strip() in {"1", "true", "on", "yes"}
        label = form_value(form, f"{prefix}_score_{field_name}_label").strip() or default_label
        components.append(
            {
                "key": field_name,
                "label": label,
                "enabled": enabled,
                "counts_for_player": True,
                "counts_for_team": True,
            }
        )
        used_keys.add(field_name)
    try:
        custom_count = min(
            100,
            max(0, int(form_value(form, f"{prefix}_custom_count", "0") or "0")),
        )
    except ValueError:
        custom_count = 0
    for index in range(custom_count):
        if len(components) >= MAX_SCORING_RULE_COMPONENTS:
            break
        key = form_value(form, f"{prefix}_custom_key_{index}").strip().lower()
        label = form_value(form, f"{prefix}_custom_label_{index}").strip()
        if not label:
            continue
        if not key or key in used_keys:
            key = f"custom_{index + 1}"
            suffix = index + 1
            while key in used_keys:
                suffix += 1
                key = f"custom_{suffix}"
        components.append(
            {
                "key": key,
                "label": label,
                "enabled": form_value(form, f"{prefix}_custom_enabled_{index}").strip()
                in {"1", "true", "on", "yes"},
                "counts_for_player": True,
                "counts_for_team": True,
            }
        )
        used_keys.add(key)
    return normalize_scoring_rule(
        {
            "score_model": form_value(form, f"{prefix}_score_model").strip(),
            "components": components,
            "notes": form_value(form, f"{prefix}_scoring_notes").strip(),
        },
        allow_inherit=allow_inherit,
    )


def validate_scoring_rule_labels(rule: dict[str, object]) -> str:
    if rule.get("inherit"):
        return ""
    seen_labels: dict[str, str] = {}
    for component in rule.get("components", []):
        if not isinstance(component, dict):
            continue
        label = str(component.get("label") or "").strip()
        key = str(component.get("key") or "").strip()
        if not label:
            return "每个计分维度都需要填写名称。"
        normalized_label = label.casefold()
        if normalized_label in seen_labels:
            return f"计分维度名称“{label}”重复，请为每个维度使用不同名称。"
        if label in RESERVED_EXCEL_SCORE_LABELS or normalized_label in RESERVED_EXCEL_SCORE_LABELS:
            return f"计分维度名称“{label}”与 Excel 系统列冲突，请更换名称。"
        seen_labels[normalized_label] = key
    return ""


def render_scoring_rule_summary(rule: dict[str, object] | None) -> str:
    normalized_rule = normalize_scoring_rule(rule)
    model_label = MATCH_SCORE_MODEL_OPTIONS.get(
        str(normalized_rule.get("score_model") or ""),
        MATCH_SCORE_MODEL_OPTIONS.get("standard", "通用总分录入"),
    )
    fields = scoring_rule_component_fields(normalized_rule)
    field_text = "、".join(label for _, label in fields) if fields else "直接录入总分"
    notes = str(normalized_rule.get("notes") or "").strip()
    version = int(normalized_rule.get("version") or 1)
    return f"""
    <div class="small text-secondary">计分方式</div>
    <div class="fw-semibold mt-1">{escape(model_label)} · V{version}</div>
    <div class="small text-secondary mt-3">启用分项</div>
    <div class="fw-semibold mt-1">{escape(field_text)}</div>
    {f'<div class="small text-secondary mt-3">规则备注</div><div class="fw-semibold mt-1">{escape(notes)}</div>' if notes else ''}
    """


def render_scoring_rule_editor(
    rule: dict[str, object] | None,
    prefix: str,
    *,
    allow_inherit: bool = False,
    inherited_rule: dict[str, object] | None = None,
) -> str:
    normalized_rule = normalize_scoring_rule(rule, allow_inherit=allow_inherit)
    inherited = bool(normalized_rule.get("inherit"))
    effective_rule = normalize_scoring_rule(inherited_rule if inherited else normalized_rule)
    selected_model = str(effective_rule.get("score_model") or "standard")
    component_by_key = {
        str(item.get("key") or ""): item
        for item in effective_rule.get("components", [])
        if isinstance(item, dict)
    }
    inherit_html = ""
    if allow_inherit:
        inherit_html = f"""
        <div class="col-12">
          <div class="form-check">
            <input class="form-check-input" id="{escape(prefix)}_scoring_inherit" name="{escape(prefix)}_scoring_inherit" type="checkbox" value="1"{' checked' if inherited else ''}>
            <label class="form-check-label" for="{escape(prefix)}_scoring_inherit">继承系列赛默认计分规则</label>
            <div class="small text-secondary mt-1">取消勾选后，该赛季会使用自己的计分规则；历史赛季建议保持独立规则，避免口径混淆。</div>
          </div>
        </div>
        """
    component_rows = []
    fixed_component_keys = {key for key, _ in SCORING_RULE_COMPONENTS}
    for field_name, default_label in SCORING_RULE_COMPONENTS:
        component = component_by_key.get(field_name, {})
        component_rows.append(
            f"""
            <div class="col-12 col-md-6 col-xl-4">
              <div class="team-link-card shadow-sm p-3 h-100">
                <div class="form-check mb-2">
                  <input class="form-check-input" id="{escape(prefix)}_{escape(field_name)}_enabled" name="{escape(prefix)}_score_{escape(field_name)}_enabled" type="checkbox" value="1"{' checked' if component.get('enabled') else ''}>
                  <label class="form-check-label" for="{escape(prefix)}_{escape(field_name)}_enabled">启用该分项</label>
                </div>
                <label class="form-label small text-secondary">分项名称</label>
                <input class="form-control" name="{escape(prefix)}_score_{escape(field_name)}_label" value="{escape(str(component.get('label') or default_label))}">
              </div>
            </div>
            """
        )
    custom_components = [
        item
        for item in effective_rule.get("components", [])
        if isinstance(item, dict) and str(item.get("key") or "") not in fixed_component_keys
    ]
    custom_rows = []
    for index, component in enumerate(custom_components):
        custom_rows.append(
            f"""
            <div class="col-12 col-md-6 col-xl-4" data-custom-score-row>
              <div class="team-link-card shadow-sm p-3 h-100">
                <input type="hidden" name="{escape(prefix)}_custom_key_{index}" value="{escape(str(component.get('key') or ''))}">
                <div class="d-flex justify-content-between align-items-center gap-2 mb-2">
                  <div class="form-check mb-0">
                    <input class="form-check-input" id="{escape(prefix)}_custom_{index}_enabled" name="{escape(prefix)}_custom_enabled_{index}" type="checkbox" value="1"{' checked' if component.get('enabled') else ''}>
                    <label class="form-check-label" for="{escape(prefix)}_custom_{index}_enabled">启用该维度</label>
                  </div>
                  <button class="btn btn-sm btn-outline-danger" type="button" data-remove-custom-score>删除</button>
                </div>
                <label class="form-label small text-secondary">维度名称</label>
                <input class="form-control" name="{escape(prefix)}_custom_label_{index}" value="{escape(str(component.get('label') or ''))}" required>
              </div>
            </div>
            """
        )
    custom_count = len(custom_components)
    custom_row_template = f"""
      <div class="team-link-card shadow-sm p-3 h-100">
        <input type="hidden" name="{escape(prefix)}_custom_key___INDEX__" value="__KEY__">
        <div class="d-flex justify-content-between align-items-center gap-2 mb-2">
          <div class="form-check mb-0">
            <input class="form-check-input" id="{escape(prefix)}_custom___INDEX___enabled" name="{escape(prefix)}_custom_enabled___INDEX__" type="checkbox" value="1" checked>
            <label class="form-check-label" for="{escape(prefix)}_custom___INDEX___enabled">启用该维度</label>
          </div>
          <button class="btn btn-sm btn-outline-danger" type="button" data-remove-custom-score>删除</button>
        </div>
        <label class="form-label small text-secondary">维度名称</label>
        <input class="form-control" name="{escape(prefix)}_custom_label___INDEX__" placeholder="例如：发言表现分" required>
      </div>
    """
    return f"""
    <div class="col-12">
      <div class="team-link-card shadow-sm p-4">
        <div class="d-flex flex-column flex-lg-row justify-content-between gap-2 mb-3">
          <div>
            <h3 class="h5 mb-1">计分规则</h3>
            <div class="small text-secondary">按系列赛或赛季配置比赛录入页展示的计分方式和分项名称。</div>
          </div>
        </div>
        <div class="row g-3">
          {inherit_html}
          <div class="col-12 col-md-6">
            <label class="form-label">计分方式</label>
            <select class="form-select" name="{escape(prefix)}_score_model">
              {legacy.option_tags(MATCH_SCORE_MODEL_OPTIONS, selected_model)}
            </select>
            <div class="small text-secondary mt-2">启用任意分项后，比赛录入会按分项自动汇总得分。</div>
          </div>
          <div class="col-12 col-md-6">
            <label class="form-label">规则备注</label>
            <input class="form-control" name="{escape(prefix)}_scoring_notes" value="{escape(str(effective_rule.get('notes') or ''))}" placeholder="例如：常规赛使用日报分项，表演赛只录总分">
          </div>
          {''.join(component_rows)}
          <div class="col-12">
            <div class="d-flex justify-content-between align-items-center gap-3 mt-2">
              <div>
                <h4 class="h6 mb-1">自定义维度</h4>
                <div class="small text-secondary">可新增赛事专属分项，例如发言、警徽流、技能收益或裁判调整。</div>
              </div>
              <button class="btn btn-sm btn-outline-dark" type="button" data-add-custom-score>新增维度</button>
            </div>
            <input type="hidden" name="{escape(prefix)}_custom_count" value="{custom_count}" data-custom-score-count>
            <div class="row g-3 mt-1" data-custom-score-list>{''.join(custom_rows)}</div>
          </div>
        </div>
      </div>
    </div>
    <script>
      (function() {{
        const editor = document.currentScript.previousElementSibling;
        if (!editor) return;
        const list = editor.querySelector("[data-custom-score-list]");
        const countInput = editor.querySelector("[data-custom-score-count]");
        const addButton = editor.querySelector("[data-add-custom-score]");
        if (!list || !countInput || !addButton) return;
        const rowTemplate = {json.dumps(custom_row_template, ensure_ascii=False)};
        let nextIndex = Number.parseInt(countInput.value || "0", 10) || 0;
        function bindRemove(button) {{
          button.addEventListener("click", function() {{
            const row = button.closest("[data-custom-score-row]");
            if (row) row.remove();
          }});
        }}
        list.querySelectorAll("[data-remove-custom-score]").forEach(bindRemove);
        addButton.addEventListener("click", function() {{
          if (list.querySelectorAll("[data-custom-score-row]").length >= {MAX_SCORING_RULE_COMPONENTS - len(SCORING_RULE_COMPONENTS)}) return;
          const index = nextIndex++;
          countInput.value = String(nextIndex);
          const key = "custom_" + Date.now().toString(36) + "_" + index;
          const wrapper = document.createElement("div");
          wrapper.className = "col-12 col-md-6 col-xl-4";
          wrapper.setAttribute("data-custom-score-row", "");
          wrapper.innerHTML = rowTemplate
            .replaceAll("__INDEX__", String(index))
            .replaceAll("__KEY__", key);
          list.appendChild(wrapper);
          bindRemove(wrapper.querySelector("[data-remove-custom-score]"));
        }});
      }})();
    </script>
    """


def get_series_manage_page(
    ctx: RequestContext,
    alert: str = "",
    form_values: dict[str, str] | None = None,
) -> str:
    data = load_validated_data()
    catalog = load_series_catalog(data)
    season_catalog = load_season_catalog(data)
    manageable_catalog = [entry for entry in catalog if can_manage_series_entry(ctx.current_user, entry)] if not is_admin_user(ctx.current_user) else catalog
    competition_rows = build_competition_catalog_rows(data, manageable_catalog)
    requested_competition_name = form_value(ctx.query, "competition_name").strip()
    requested_season_name = form_value(ctx.query, "season_name").strip()
    requested_edit_mode = str(form_values.get("edit_mode") or "").strip() if form_values and form_values.get("edit_mode") is not None else form_value(ctx.query, "edit").strip()
    if requested_edit_mode not in {"catalog", "season", "create"}:
        requested_edit_mode = ""
    selected_entry = get_series_entry_by_competition(manageable_catalog, requested_competition_name) if requested_competition_name else None
    if requested_competition_name and not selected_entry:
        return layout("没有权限", '<div class="alert alert-danger">你只能管理自己负责地区系列赛下的赛季和赛事页。</div>', ctx, alert=alert)
    selected_season_entry = get_season_entry(season_catalog, selected_entry["series_slug"], requested_season_name, competition_name=requested_competition_name) if selected_entry and requested_season_name else None
    current_form = {
        "series_name": "",
        "series_code": "",
        "region_name": DEFAULT_REGION_NAME,
        "competition_name": "",
        "summary": "",
        "page_badge": "",
        "hero_title": "",
        "hero_intro": "",
        "hero_note": "",
        "scoring_rule": normalize_scoring_rule({}),
        "original_competition_name": "",
        "next": form_value(ctx.query, "next").strip(),
        "edit_mode": requested_edit_mode,
    }
    season_form = {
        "competition_name": requested_competition_name,
        "original_season_name": requested_season_name,
        "season_name": "",
        "start_at": "",
        "end_at": "",
        "notes": "",
        "scoring_rule": {"inherit": True},
        "edit_mode": requested_edit_mode,
        **build_stage_window_form_values(),
    }
    if selected_entry:
        current_form.update(
            {
                "series_name": selected_entry["series_name"],
                "series_code": selected_entry["series_code"],
                "region_name": selected_entry["region_name"],
                "competition_name": selected_entry["competition_name"],
                "summary": selected_entry.get("summary", ""),
                "page_badge": selected_entry.get("page_badge", ""),
                "hero_title": selected_entry.get("hero_title", ""),
                "hero_intro": selected_entry.get("hero_intro", ""),
                "hero_note": selected_entry.get("hero_note", ""),
                "scoring_rule": normalize_scoring_rule(selected_entry.get("scoring_rule")),
                "original_competition_name": selected_entry["competition_name"],
            }
        )
    if selected_season_entry:
        season_form.update(
            {
                "competition_name": requested_competition_name,
                "original_season_name": selected_season_entry["season_name"],
                "season_name": selected_season_entry["season_name"],
                "start_at": selected_season_entry.get("start_at", ""),
                "end_at": selected_season_entry.get("end_at", ""),
                "notes": selected_season_entry.get("notes", ""),
                "scoring_rule": normalize_scoring_rule(selected_season_entry.get("scoring_rule"), allow_inherit=True),
                **build_stage_window_form_values(selected_season_entry),
            }
        )
    if form_values:
        current_form.update(form_values)
        if "catalog_scoring_rule" in form_values:
            current_form["scoring_rule"] = form_values["catalog_scoring_rule"]
        season_form.update(
            {
                key: form_values[key]
                for key in (
                    "competition_name",
                    "original_season_name",
                    "season_name",
                    "start_at",
                    "end_at",
                    "notes",
                    "edit_mode",
                    *[
                        key
                        for stage_key in STAGE_OPTIONS
                        for key in (f"stage_{stage_key}_start_at", f"stage_{stage_key}_end_at")
                    ],
                )
                if key in form_values
            }
        )
        if "season_scoring_rule" in form_values:
            season_form["scoring_rule"] = form_values["season_scoring_rule"]
    editing_existing = bool(current_form["original_competition_name"])
    form_heading = "编辑赛事页信息" if editing_existing else "新建地区系列赛"
    form_copy = (
        "这里可以调整这个地区赛事页的顶部标识、主标题、导语和说明文案。为了避免历史比赛脱钩，已有赛事页名称在编辑模式下保持只读。"
        if editing_existing
        else "如果同一系列赛要在多个地区共用一个专题页，请保持“系列编码”一致，例如同系列的广州站和北京站都使用同一个编码。"
    )
    competition_name_field = (
        f"""
        <input class="form-control" name="competition_name" value="{escape(current_form['competition_name'])}" readonly>
        <div class="small text-secondary mt-2">已有赛事页名称作为比赛挂载键使用，当前编辑模式下保持只读。</div>
        """
        if editing_existing
        else f'<input class="form-control" name="competition_name" value="{escape(current_form["competition_name"])}" required>'
    )
    region_name_field = (
        f"""
        <input class="form-control" name="region_name" value="{escape(current_form['region_name'])}" readonly>
        <div class="small text-secondary mt-2">已有地区赛事页的所属地区会参与赛事负责人权限匹配，编辑模式下保持只读。</div>
        """
        if editing_existing
        else f'<input class="form-control" name="region_name" value="{escape(current_form["region_name"])}" required>'
    )
    selected_competition_name = current_form["competition_name"].strip()
    selected_series_slug = selected_entry["series_slug"] if selected_entry else ""
    can_edit_selected_catalog = bool(selected_competition_name and can_manage_competition_catalog(ctx.current_user, data, selected_competition_name))
    can_manage_selected_seasons = bool(selected_competition_name and can_manage_competition_seasons(ctx.current_user, data, selected_competition_name))
    can_force_delete_selected_season = bool(is_admin_user(ctx.current_user) and selected_competition_name)
    catalog_editor_active = bool(requested_edit_mode == "catalog" or (requested_edit_mode == "create" and is_admin_user(ctx.current_user)))
    season_editor_active = bool(requested_edit_mode == "season")
    competition_season_entries = get_season_entries_for_series(season_catalog, selected_series_slug, include_non_ongoing=True, competition_name=selected_competition_name) if selected_series_slug else []

    existing_cards = []
    for row in competition_rows:
        detail_path = build_series_manage_path(row["competition_name"], current_form["next"])
        edit_path = build_series_manage_path(row["competition_name"], current_form["next"], None, "catalog")
        season_manage_path = build_series_manage_path(row["competition_name"], current_form["next"], None, "season")
        row_can_edit_catalog = can_manage_competition_catalog(ctx.current_user, data, row["competition_name"])
        row_can_manage_seasons = can_manage_competition_seasons(ctx.current_user, data, row["competition_name"])
        is_selected_row = row["competition_name"] == selected_competition_name
        existing_cards.append(
            f"""
            <div class="col-12 col-lg-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">{escape(row['region_name'])} · {escape(row['series_name'])}</div>
                    <h2 class="h5 mb-2">{escape(row['competition_name'])}</h2>
                    <div class="small-muted">系列编码 {escape(row['series_code'])} · 赛季 {escape('、'.join(row['seasons'])) if row['seasons'] else '待录入'}</div>
                    <div class="small-muted mt-1">最近比赛日 {escape(row['latest_played_on'] or '待更新')}</div>
                  </div>
                  <span class="chip">{'当前查看' if is_selected_row else ('启用中' if row['active'] else '已停用')}</span>
                </div>
                <p class="section-copy mt-3 mb-2">{escape(row['summary'] or '暂无专题说明。')}</p>
                <div class="small-muted">赛事页标题 {escape(row.get('hero_title') or row['competition_name'])}</div>
                <div class="small-muted mt-1">顶部标识 {escape(row.get('page_badge') or (row['region_name'] + ' · 赛事专属页面'))}</div>
                <div class="d-flex flex-wrap gap-2 mt-3">
                  <a class="btn btn-sm btn-outline-dark" href="{escape(detail_path)}">查看详情</a>
                  {(f'<a class="btn btn-sm btn-outline-dark" href="{escape(edit_path)}">编辑赛事页</a>' if row_can_edit_catalog else '')}
                  {(f'<a class="btn btn-sm btn-outline-dark" href="{escape(season_manage_path)}">赛季管理</a>' if row_can_manage_seasons else '')}
                  <a class="btn btn-sm btn-outline-dark" href="{escape(build_scoped_path('/competitions', row['competition_name'], None, row['region_name'], row['series_slug']))}">打开赛事页</a>
                </div>
              </div>
            </div>
            """
        )

    selected_overview_html = ""
    if selected_entry:
        selected_competition_path = build_scoped_path("/competitions", selected_entry["competition_name"], None, selected_entry["region_name"], selected_entry["series_slug"])
        selected_overview_html = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-start gap-3 mb-4">
            <div>
              <div class="eyebrow mb-2">{escape(selected_entry['region_name'])} · {escape(selected_entry['series_name'])}</div>
              <h2 class="section-title mb-2">{escape(selected_entry['competition_name'])}</h2>
              <p class="section-copy mb-0">默认只读展示这个地区系列赛的信息。需要修改时，再进入单独的编辑页。</p>
            </div>
            <div class="d-flex flex-wrap gap-2">
              <a class="btn btn-outline-dark" href="/series-manage">返回全部系列赛</a>
              {(f'<a class="btn btn-dark" href="{escape(build_series_manage_path(selected_competition_name, current_form["next"], None, "catalog"))}">编辑赛事页</a>' if can_edit_selected_catalog else '')}
              {(f'<a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition_name, current_form["next"], None, "season"))}">新增赛季</a>' if can_manage_selected_seasons else '')}
              <a class="btn btn-outline-dark" href="{escape(selected_competition_path)}">打开赛事页</a>
            </div>
          </div>
          <div class="row g-3">
            <div class="col-12 col-lg-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="small text-secondary">系列编码</div>
                <div class="fw-semibold mt-1">{escape(selected_entry['series_code'])}</div>
                <div class="small text-secondary mt-3">赛事页标题</div>
                <div class="fw-semibold mt-1">{escape(selected_entry.get('hero_title') or selected_entry['competition_name'])}</div>
                <div class="small text-secondary mt-3">顶部标识</div>
                <div class="fw-semibold mt-1">{escape(selected_entry.get('page_badge') or (selected_entry['region_name'] + ' · 赛事专属页面'))}</div>
              </div>
            </div>
            <div class="col-12 col-lg-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="small text-secondary">专题说明</div>
                <div class="fw-semibold mt-1">{escape(selected_entry.get('summary') or '暂无专题说明')}</div>
                <div class="small text-secondary mt-3">导语</div>
                <div class="fw-semibold mt-1">{escape(selected_entry.get('hero_intro') or '暂无导语')}</div>
                <div class="small text-secondary mt-3">说明备注</div>
                <div class="fw-semibold mt-1">{escape(selected_entry.get('hero_note') or '暂无说明备注')}</div>
              </div>
            </div>
            <div class="col-12">
              <div class="team-link-card shadow-sm p-4">
                {render_scoring_rule_summary(selected_entry.get('scoring_rule'))}
              </div>
            </div>
          </div>
        </section>
        """

    selected_season_overview_html = ""
    if selected_season_entry:
        selected_season_overview_html = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-start gap-3">
            <div>
              <div class="eyebrow mb-2">当前赛季</div>
              <h2 class="section-title mb-2">{escape(selected_season_entry['season_name'])}</h2>
              <p class="section-copy mb-0">这里先显示赛季信息。只有点“编辑当前赛季”才会进入修改模式。</p>
            </div>
            <div class="d-flex flex-wrap gap-2">
              {(f'<a class="btn btn-dark" href="{escape(build_series_manage_path(selected_competition_name, current_form["next"], selected_season_entry["season_name"], "season"))}">编辑当前赛季</a>' if can_manage_selected_seasons else '')}
              <a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition_name, current_form['next']))}">返回该系列赛</a>
            </div>
          </div>
          <div class="row g-3 mt-1">
            <div class="col-12 col-lg-4"><div class="team-link-card shadow-sm p-4 h-100"><div class="small text-secondary">开始时间</div><div class="fw-semibold mt-1">{escape(format_datetime_local_label(selected_season_entry.get('start_at', '')))}</div></div></div>
            <div class="col-12 col-lg-4"><div class="team-link-card shadow-sm p-4 h-100"><div class="small text-secondary">结束时间</div><div class="fw-semibold mt-1">{escape(format_datetime_local_label(selected_season_entry.get('end_at', '')))}</div></div></div>
            <div class="col-12 col-lg-4"><div class="team-link-card shadow-sm p-4 h-100"><div class="small text-secondary">状态</div><div class="fw-semibold mt-1">{escape(season_status_label(selected_season_entry))}</div></div></div>
            <div class="col-12"><div class="team-link-card shadow-sm p-4"><div class="small text-secondary">赛季说明</div><div class="fw-semibold mt-1">{escape(selected_season_entry.get('notes') or '暂无赛季说明')}</div></div></div>
            <div class="col-12"><div class="team-link-card shadow-sm p-4">{render_scoring_rule_summary(merge_scoring_rules(selected_entry.get('scoring_rule') if selected_entry else None, selected_season_entry.get('scoring_rule')))}</div></div>
            <div class="col-12"><h3 class="h5 mb-0 mt-2">赛段时间</h3></div>
            {render_stage_window_cards(selected_season_entry)}
          </div>
        </section>
        """

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    season_cards = []
    for season_entry in competition_season_entries:
        season_detail_path = build_series_manage_path(selected_competition_name, current_form["next"], season_entry["season_name"])
        season_edit_path = build_series_manage_path(selected_competition_name, current_form["next"], season_entry["season_name"], "season")
        season_cards.append(
            f"""
            <div class="col-12 col-lg-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">赛季档期</div>
                    <h2 class="h5 mb-2">{escape(season_entry['season_name'])}</h2>
                    <div class="small-muted">起止时间 {escape(format_datetime_local_label(season_entry.get('start_at', '')))} - {escape(format_datetime_local_label(season_entry.get('end_at', '')))}</div>
                    <div class="small-muted mt-1">状态 {escape(season_status_label(season_entry))}</div>
                  </div>
                  <span class="chip">{'当前赛季' if season_entry['season_name'] == requested_season_name else escape(season_status_label(season_entry))}</span>
                </div>
                <p class="section-copy mt-3 mb-2">{escape(season_entry.get('notes') or '这个赛季还没有补充说明。')}</p>
                <div class="d-flex flex-wrap gap-2 mt-3">
                  <a class="btn btn-sm btn-outline-dark" href="{escape(season_detail_path)}">查看赛季</a>
                  {(f'<a class="btn btn-sm btn-outline-dark" href="{escape(season_edit_path)}">编辑赛季</a>' if can_manage_selected_seasons else '')}
                </div>
              </div>
            </div>
            """
        )

    season_section_html = ""
    if selected_entry:
        season_section_html = selected_season_overview_html + f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">赛季列表</h2>
              <p class="section-copy mb-0">赛季信息默认只读展示。点击某个赛季的编辑按钮后，再单独修改该赛季。</p>
            </div>
            <div class="d-flex flex-wrap gap-2">
              {(f'<a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition_name, current_form["next"], None, "season"))}">新建赛季</a>' if can_manage_selected_seasons else '')}
            </div>
          </div>
          <div class="row g-3 g-lg-4">{''.join(season_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">这个赛事页还没有配置赛季，请先创建第一个赛季。</div></div>'}</div>
        </section>
        """
        if season_editor_active:
            if can_manage_selected_seasons:
                delete_season_form_html = ""
                delete_season_helper_html = '<div class="small text-secondary">当前正在新建赛季，保存后会回到正常展示状态。</div>'
                if season_form["original_season_name"]:
                    target_season_name = season_form["original_season_name"]
                    selected_season_has_matches = any(get_match_competition_name(match) == selected_competition_name and str(match.get("season") or "").strip() == target_season_name for match in data["matches"])
                    delete_button_disabled = ""
                    delete_button_confirm = " onclick=\"return confirm('确认强制删除当前赛季吗？这会一并删除该赛季相关数据，且不可恢复。')\""
                    if can_force_delete_selected_season:
                        if selected_season_has_matches:
                            delete_season_helper_html = '<div class="small text-secondary">仅管理员可强制删除赛季。当前操作会同步删除该赛季下的全部比赛记录，并清理相关赛季数据。</div>'
                        else:
                            delete_season_helper_html = '<div class="small text-secondary">当前赛季还没有比赛记录，管理员可以直接删除。</div>'
                    else:
                        delete_button_disabled = " disabled"
                        delete_button_confirm = ""
                        delete_season_helper_html = '<div class="small text-secondary">只有管理员可以强制删除赛季；赛事负责人不能删除赛季。</div>'
                    if can_force_delete_selected_season:
                        delete_season_form_html = f"""
                        <form method="post" action="/series-manage" class="m-0">
                          <input type="hidden" name="action" value="delete_season">
                          <input type="hidden" name="competition_name" value="{escape(selected_competition_name)}">
                          <input type="hidden" name="season_name" value="{escape(target_season_name)}">
                          <input type="hidden" name="next" value="{escape(current_form['next'])}">
                          <input class="form-control mb-2" name="delete_confirmation" placeholder="输入 删除赛季 确认">
                          <button type="submit" class="btn btn-outline-danger"{delete_button_disabled}{delete_button_confirm}>强制删除当前赛季</button>
                        </form>
                        """
                season_form_title = "编辑赛季档期" if season_form["original_season_name"] else "新建赛季档期"
                season_cancel_path = build_series_manage_path(selected_competition_name, current_form["next"], season_form["original_season_name"] or requested_season_name or None)
                stage_window_inputs_html = "".join(
                    f"""
                    <div class="col-12 col-lg-6">
                      <div class="team-link-card shadow-sm p-3 h-100">
                        <div class="fw-semibold mb-3">{escape(stage_label)}</div>
                        <div class="row g-2">
                          <div class="col-12 col-md-6">
                            <label class="form-label">开始时间</label>
                            <input class="form-control" name="stage_{escape(stage_key)}_start_at" type="datetime-local" value="{escape(season_form[f'stage_{stage_key}_start_at'])}">
                          </div>
                          <div class="col-12 col-md-6">
                            <label class="form-label">结束时间</label>
                            <input class="form-control" name="stage_{escape(stage_key)}_end_at" type="datetime-local" value="{escape(season_form[f'stage_{stage_key}_end_at'])}">
                          </div>
                        </div>
                      </div>
                    </div>
                    """
                    for stage_key, stage_label in STAGE_OPTIONS.items()
                )
                season_section_html = f"""
                <section class="form-panel shadow-sm p-3 p-lg-4 mb-4">
                  <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-4">
                    <div>
                      <h2 class="section-title mb-2">{season_form_title}</h2>
                      <p class="section-copy mb-0">赛季信息与列表页分开编辑，保存后会回到正常展示状态。</p>
                    </div>
                  </div>
                  <form method="post" action="/series-manage">
                    <input type="hidden" name="action" value="save_season">
                    <input type="hidden" name="edit_mode" value="season">
                    <input type="hidden" name="competition_name" value="{escape(selected_competition_name)}">
                    <input type="hidden" name="original_season_name" value="{escape(season_form['original_season_name'])}">
                    <input type="hidden" name="next" value="{escape(current_form['next'])}">
                    <div class="row g-3">
                      <div class="col-12 col-md-4"><label class="form-label">赛季名称</label><input class="form-control" name="season_name" value="{escape(season_form['season_name'])}" placeholder="例如：2026春季联赛" required></div>
                      <div class="col-12 col-md-4"><label class="form-label">开始时间</label><input class="form-control" name="start_at" type="datetime-local" value="{escape(season_form['start_at'])}" required></div>
                      <div class="col-12 col-md-4"><label class="form-label">结束时间</label><input class="form-control" name="end_at" type="datetime-local" value="{escape(season_form['end_at'])}" required></div>
                      <div class="col-12"><label class="form-label">赛季说明</label><textarea class="form-control" name="notes" rows="3" placeholder="可写赛季定位、档期说明或补充备注。">{escape(season_form['notes'])}</textarea></div>
                      {render_scoring_rule_editor(season_form.get('scoring_rule'), 'season', allow_inherit=True, inherited_rule=(selected_entry or {}).get('scoring_rule'))}
                      <div class="col-12">
                        <div class="d-flex flex-column flex-lg-row justify-content-between gap-2 mt-2">
                          <div>
                            <h3 class="h5 mb-1">赛段时间</h3>
                            <div class="small text-secondary">以下时间均按北京时间保存；赛事页会用当前北京时间自动显示赛段状态。</div>
                          </div>
                        </div>
                      </div>
                      {stage_window_inputs_html}
                    </div>
                    <div class="d-flex flex-wrap gap-2 mt-4">
                      <button type="submit" class="btn btn-dark">保存赛季档期</button>
                      <a class="btn btn-outline-dark" href="{escape(season_cancel_path)}">取消编辑</a>
                    </div>
                  </form>
                  <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-2 mt-2">
                    <div>{delete_season_helper_html}</div>
                    <div class="d-flex flex-wrap gap-2">{delete_season_form_html}</div>
                  </div>
                </section>
                """ + season_section_html
            else:
                season_section_html = """
                <section class="panel shadow-sm p-3 p-lg-4 mb-4">
                  <div class="alert alert-secondary mb-0">你当前可以查看这个地区系列赛，但没有赛季档期管理权限。</div>
                </section>
                """ + season_section_html

    catalog_form_html = ""
    if catalog_editor_active:
        if editing_existing and can_edit_selected_catalog:
            catalog_cancel_path = build_series_manage_path(selected_competition_name, current_form["next"], requested_season_name or None)
            catalog_form_html = f"""
            <section class="form-panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-4">
                <div>
                  <h2 class="section-title mb-2">{form_heading}</h2>
                  <p class="section-copy mb-0">{form_copy}</p>
                </div>
              </div>
              <form method="post" action="/series-manage">
                <input type="hidden" name="original_competition_name" value="{escape(current_form['original_competition_name'])}">
                <input type="hidden" name="edit_mode" value="catalog">
                <input type="hidden" name="next" value="{escape(current_form['next'])}">
                <div class="row g-3">
                  <div class="col-12 col-md-6"><label class="form-label">系列赛名称</label><input class="form-control" name="series_name" value="{escape(current_form['series_name'])}" required></div>
                  <div class="col-12 col-md-6"><label class="form-label">系列编码</label><input class="form-control" name="series_code" value="{escape(current_form['series_code'])}" placeholder="可选，留空则自动生成"></div>
                  <div class="col-12 col-md-4"><label class="form-label">地区</label>{region_name_field}</div>
                  <div class="col-12 col-md-8"><label class="form-label">地区赛事页名称</label>{competition_name_field}</div>
                  <div class="col-12"><label class="form-label">专题说明</label><textarea class="form-control" name="summary" rows="3">{escape(current_form['summary'])}</textarea></div>
                  <div class="col-12 col-md-6"><label class="form-label">赛事页顶部标识</label><input class="form-control" name="page_badge" value="{escape(current_form['page_badge'])}" placeholder="例如：广州 · 春季公开赛官方页"></div>
                  <div class="col-12 col-md-6"><label class="form-label">赛事页主标题</label><input class="form-control" name="hero_title" value="{escape(current_form['hero_title'])}" placeholder="留空则默认显示赛事页名称"></div>
                  <div class="col-12"><label class="form-label">赛事页导语</label><textarea class="form-control" name="hero_intro" rows="3" placeholder="展示在赛事页头部左侧，适合写当前赛事定位、浏览方式和亮点。">{escape(current_form['hero_intro'])}</textarea></div>
                  <div class="col-12"><label class="form-label">赛事页说明备注</label><textarea class="form-control" name="hero_note" rows="3" placeholder="展示在赛事页头部右侧信息卡，适合写这个赛区、本赛季或该赛事页的说明。">{escape(current_form['hero_note'])}</textarea></div>
                  {render_scoring_rule_editor(current_form.get('scoring_rule'), 'catalog')}
                </div>
                <div class="d-flex flex-wrap gap-2 mt-4">
                  <button type="submit" class="btn btn-dark">保存赛事页信息</button>
                  <a class="btn btn-outline-dark" href="{escape(catalog_cancel_path)}">取消编辑</a>
                </div>
              </form>
            </section>
            """
        elif editing_existing:
            catalog_form_html = """
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="alert alert-secondary mb-0">你当前可以查看这个地区系列赛，但没有赛事页信息编辑权限。</div>
            </section>
            """
        elif is_admin_user(ctx.current_user):
            catalog_form_html = f"""
            <section class="form-panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-4">
                <div>
                  <h2 class="section-title mb-2">{form_heading}</h2>
                  <p class="section-copy mb-0">{form_copy}</p>
                </div>
              </div>
              <form method="post" action="/series-manage">
                <input type="hidden" name="original_competition_name" value="{escape(current_form['original_competition_name'])}">
                <input type="hidden" name="edit_mode" value="create">
                <input type="hidden" name="next" value="{escape(current_form['next'])}">
                <div class="row g-3">
                  <div class="col-12 col-md-6"><label class="form-label">系列赛名称</label><input class="form-control" name="series_name" value="{escape(current_form['series_name'])}" required></div>
                  <div class="col-12 col-md-6"><label class="form-label">系列编码</label><input class="form-control" name="series_code" value="{escape(current_form['series_code'])}" placeholder="可选，留空则自动生成"></div>
                  <div class="col-12 col-md-4"><label class="form-label">地区</label>{region_name_field}</div>
                  <div class="col-12 col-md-8"><label class="form-label">地区赛事页名称</label>{competition_name_field}</div>
                  <div class="col-12"><label class="form-label">专题说明</label><textarea class="form-control" name="summary" rows="3">{escape(current_form['summary'])}</textarea></div>
                  <div class="col-12 col-md-6"><label class="form-label">赛事页顶部标识</label><input class="form-control" name="page_badge" value="{escape(current_form['page_badge'])}" placeholder="例如：广州 · 春季公开赛官方页"></div>
                  <div class="col-12 col-md-6"><label class="form-label">赛事页主标题</label><input class="form-control" name="hero_title" value="{escape(current_form['hero_title'])}" placeholder="留空则默认显示赛事页名称"></div>
                  <div class="col-12"><label class="form-label">赛事页导语</label><textarea class="form-control" name="hero_intro" rows="3" placeholder="展示在赛事页头部左侧，适合写当前赛事定位、浏览方式和亮点。">{escape(current_form['hero_intro'])}</textarea></div>
                  <div class="col-12"><label class="form-label">赛事页说明备注</label><textarea class="form-control" name="hero_note" rows="3" placeholder="展示在赛事页头部右侧信息卡，适合写这个赛区、本赛季或该赛事页的说明。">{escape(current_form['hero_note'])}</textarea></div>
                  {render_scoring_rule_editor(current_form.get('scoring_rule'), 'catalog')}
                </div>
                <div class="d-flex flex-wrap gap-2 mt-4">
                  <button type="submit" class="btn btn-dark">保存系列赛目录</button>
                  <a class="btn btn-outline-dark" href="/series-manage">取消创建</a>
                </div>
              </form>
            </section>
            """
        else:
            catalog_form_html = """
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="alert alert-secondary mb-0">当前账号没有新建地区赛事页的权限；如需新增目录，请使用管理员账号操作。</div>
            </section>
            """

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">系列赛目录管理</div>
          <h1 class="hero-title mb-3">系列赛与赛季分开管理</h1>
          <p class="hero-copy mb-0">这里先展示全部地区系列赛；赛事页信息和赛季信息默认只读，只有点击编辑按钮时才进入修改模式。赛事负责人只能修改自己被分配到的地区系列赛范围。</p>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Series Catalog</div>
          <div class="hero-stage-label">Manager Access</div>
          <div class="hero-stage-title">{len(competition_rows)}</div>
          <div class="hero-stage-note">当前目录中的地区赛事页数量。相同系列赛只要保持相同系列编码，就会自动聚合到同一个专题页。</div>
        </div>
      </div>
    </section>
    {('<section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-3"><div><h2 class="section-title mb-2">新增系列赛</h2><p class="section-copy mb-0">新建入口与现有系列赛的查看页分开，避免在列表页误改已有数据。</p></div><div><a class="btn btn-dark" href="/series-manage?edit=create">新建系列赛</a></div></div></section>' if is_admin_user(ctx.current_user) and not catalog_editor_active else '')}
    {selected_overview_html}
    {catalog_form_html}
    {season_section_html}
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">当前系列赛目录</h2>
          <p class="section-copy mb-0">这里展示已经配置好的地区赛事页。先查看详情，再按需进入赛事页编辑或赛季编辑。</p>
        </div>
      </div>
      <div class="row g-3 g-lg-4">{''.join(existing_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">目前还没有系列赛目录。</div></div>'}</div>
    </section>
    """
    return layout("系列赛管理", body, ctx, alert=alert)


def handle_series_manage(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_series_manage_page(ctx))
    data = load_validated_data()
    catalog = load_series_catalog(data)
    season_catalog = load_season_catalog(data)
    action = form_value(ctx.form, "action").strip() or "save_catalog"
    if action == "save_season":
        edit_mode = form_value(ctx.form, "edit_mode").strip() or "season"
        competition_name = form_value(ctx.form, "competition_name").strip()
        original_season_name = form_value(ctx.form, "original_season_name").strip()
        season_name = form_value(ctx.form, "season_name").strip()
        start_at = form_value(ctx.form, "start_at").strip()
        end_at = form_value(ctx.form, "end_at").strip()
        notes = form_value(ctx.form, "notes").strip()
        season_scoring_rule = collect_scoring_rule_from_form(ctx.form, "season", allow_inherit=True)
        next_path = form_value(ctx.form, "next").strip()
        stage_windows = collect_stage_windows_from_form(ctx.form)
        permission_guard = require_competition_season_manager(ctx, start_response, data, competition_name, "你只能编辑自己负责地区系列赛下的赛季。")
        if permission_guard is not None:
            return permission_guard
        selected_entry = get_series_entry_by_competition(catalog, competition_name)
        series_slug = selected_entry["series_slug"] if selected_entry else ""
        form_values = {
            "competition_name": competition_name,
            "original_season_name": original_season_name,
            "season_name": season_name,
            "start_at": start_at,
            "end_at": end_at,
            "notes": notes,
            "season_scoring_rule": season_scoring_rule,
            "original_competition_name": competition_name,
            "next": next_path,
            "edit_mode": edit_mode,
            **{
                f"stage_{window['stage']}_{field}": window.get(f"{field}", "")
                for window in stage_windows
                for field in ("start_at", "end_at")
            },
        }
        error = legacy.validate_season_catalog_form(series_slug, season_name, start_at, end_at)
        error = error or validate_stage_windows(stage_windows)
        error = error or validate_scoring_rule_labels(season_scoring_rule)
        if error:
            return start_response_html(start_response, "200 OK", get_series_manage_page(ctx, alert=error, form_values=form_values))
        lookup_season_name = original_season_name or season_name
        existing_entry = get_season_entry(season_catalog, series_slug, lookup_season_name, competition_name=competition_name)
        season_scoring_rule = version_scoring_rule(
            season_scoring_rule,
            existing_entry.get("scoring_rule") if existing_entry else None,
            allow_inherit=True,
        )
        new_entry = normalize_season_catalog_entry({"series_slug": series_slug, "series_name": selected_entry["series_name"] if selected_entry else "", "series_code": selected_entry["series_code"] if selected_entry else "", "competition_name": competition_name, "season_name": season_name, "start_at": start_at, "end_at": end_at, "stage_windows": stage_windows, "scoring_rule": season_scoring_rule, "notes": notes, "registered_team_ids": existing_entry.get("registered_team_ids", []) if existing_entry else [], "created_by": existing_entry.get("created_by") if existing_entry else (ctx.current_user["username"] if ctx.current_user else "system"), "created_on": existing_entry.get("created_on", china_today_label()) if existing_entry else china_today_label()})
        if not new_entry:
            return start_response_html(start_response, "200 OK", get_series_manage_page(ctx, alert="赛季保存失败。", form_values=form_values))
        updated_catalog = [item for item in season_catalog if not (item["series_slug"] == series_slug and item.get("competition_name", "") == competition_name and item["season_name"] == lookup_season_name)]
        updated_catalog.append(new_entry)
        save_season_catalog(updated_catalog)
        if lookup_season_name and lookup_season_name != season_name:
            for match in data["matches"]:
                if get_match_competition_name(match) == competition_name and str(match.get("season") or "").strip() == lookup_season_name:
                    match["season"] = season_name
            for team in data["teams"]:
                if str(team.get("competition_name") or "").strip() == competition_name and str(team.get("season_name") or "").strip() == lookup_season_name:
                    team["season_name"] = season_name
            requests = [{**item, "scope_season_name": (season_name if item.get("scope_competition_name") == competition_name and item.get("scope_season_name") == lookup_season_name else item.get("scope_season_name", ""))} for item in load_membership_requests()]
            errors = save_repository_state(data, load_users())
            if errors:
                return start_response_html(start_response, "200 OK", get_series_manage_page(ctx, alert="赛季改名失败：" + "；".join(errors[:3]), form_values=form_values))
            save_membership_requests(requests)
        return start_response_html(start_response, "200 OK", get_series_manage_page(RequestContext(method="GET", path=ctx.path, query={"competition_name": [competition_name], "season_name": [season_name], **({"next": [next_path]} if next_path else {})}, form={}, files={}, current_user=ctx.current_user, now_label=ctx.now_label), alert=f"{competition_name} / {season_name} 的赛季档期已保存。"))
    if action == "delete_season":
        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season_name").strip()
        next_path = form_value(ctx.form, "next").strip()
        if not is_admin_user(ctx.current_user):
            return start_response_html(start_response, "403 Forbidden", get_series_manage_page(ctx, alert="只有管理员可以强制删除赛季。"))
        if form_value(ctx.form, "delete_confirmation").strip() != "删除赛季":
            return start_response_html(start_response, "200 OK", get_series_manage_page(ctx, alert="强制删除赛季前，请在确认框输入：删除赛季。"))
        selected_entry = get_series_entry_by_competition(catalog, competition_name)
        if not selected_entry:
            return start_response_html(start_response, "200 OK", get_series_manage_page(ctx, alert="没有找到对应的地区系列赛。"))
        # Persist the current series directory before deleting the last season/matches,
        # so the competition page remains visible even when its data is temporarily empty.
        save_series_catalog(catalog)
        target_entry = get_season_entry(season_catalog, selected_entry["series_slug"], season_name, competition_name=competition_name)
        if not target_entry:
            return start_response_html(start_response, "200 OK", get_series_manage_page(ctx, alert="没有找到要删除的赛季。"))
        data["matches"] = [
            match
            for match in data["matches"]
            if not (
                get_match_competition_name(match) == competition_name
                and str(match.get("season") or "").strip() == season_name
            )
        ]
        requests = [
            item
            for item in load_membership_requests()
            if not (
                item.get("scope_competition_name", "") == competition_name
                and item.get("scope_season_name", "") == season_name
            )
        ]
        updated_catalog = [item for item in season_catalog if not (item["series_slug"] == selected_entry["series_slug"] and item.get("competition_name", "") == competition_name and item["season_name"] == season_name)]
        save_season_catalog(updated_catalog)
        errors = save_repository_state(data, load_users())
        if errors:
            return start_response_html(start_response, "200 OK", get_series_manage_page(ctx, alert="强制删除赛季失败：" + "；".join(errors[:3])))
        save_membership_requests(requests)
        audit_action(
            ctx,
            "season.delete",
            target_type="competition",
            target_id=competition_name,
            summary=f"强制删除 {competition_name} / {season_name} 赛季",
            metadata={"competition_name": competition_name, "season_name": season_name},
        )
        return start_response_html(start_response, "200 OK", get_series_manage_page(RequestContext(method="GET", path=ctx.path, query={"competition_name": [competition_name], **({"next": [next_path]} if next_path else {})}, form={}, files={}, current_user=ctx.current_user, now_label=ctx.now_label), alert=f"{competition_name} / {season_name} 已强制删除，并清理了该赛季相关数据。"))
    series_name = form_value(ctx.form, "series_name").strip()
    series_code = form_value(ctx.form, "series_code").strip()
    region_name = form_value(ctx.form, "region_name").strip()
    competition_name = form_value(ctx.form, "competition_name").strip()
    summary = form_value(ctx.form, "summary").strip()
    page_badge = form_value(ctx.form, "page_badge").strip()
    hero_title = form_value(ctx.form, "hero_title").strip()
    hero_intro = form_value(ctx.form, "hero_intro").strip()
    hero_note = form_value(ctx.form, "hero_note").strip()
    catalog_scoring_rule = collect_scoring_rule_from_form(ctx.form, "catalog")
    original_competition_name = form_value(ctx.form, "original_competition_name").strip()
    next_path = form_value(ctx.form, "next").strip()
    edit_mode = form_value(ctx.form, "edit_mode").strip() or ("catalog" if original_competition_name else "create")
    form_values = {"series_name": series_name, "series_code": series_code, "region_name": region_name, "competition_name": competition_name, "summary": summary, "page_badge": page_badge, "hero_title": hero_title, "hero_intro": hero_intro, "hero_note": hero_note, "catalog_scoring_rule": catalog_scoring_rule, "original_competition_name": original_competition_name, "next": next_path, "edit_mode": edit_mode}
    error = legacy.validate_series_catalog_form(series_name, region_name, competition_name)
    error = error or validate_scoring_rule_labels(catalog_scoring_rule)
    if not error and original_competition_name and original_competition_name != competition_name:
        error = "已有赛事页名称暂不支持直接修改，请保留原名称并编辑页面信息。"
    existing_entry = get_series_entry_by_competition(catalog, original_competition_name) if original_competition_name else None
    if not original_competition_name and not is_admin_user(ctx.current_user):
        error = error or "只有管理员可以创建新的地区系列赛目录。"
    if original_competition_name:
        permission_guard = require_competition_catalog_manager(ctx, start_response, data, original_competition_name, "你只能编辑自己负责地区系列赛下的赛事页信息。")
        if permission_guard is not None:
            return permission_guard
        if existing_entry and region_name != existing_entry["region_name"]:
            error = error or "已有地区赛事页的所属地区不能直接修改。"
    if error:
        return start_response_html(start_response, "200 OK", get_series_manage_page(ctx, alert=error, form_values=form_values))
    catalog_scoring_rule = version_scoring_rule(
        catalog_scoring_rule,
        existing_entry.get("scoring_rule") if existing_entry else None,
    )
    new_entry = normalize_series_catalog_entry({"series_name": series_name, "series_code": series_code, "region_name": region_name, "competition_name": competition_name, "series_slug": existing_entry["series_slug"] if existing_entry else "", "summary": summary, "page_badge": page_badge, "hero_title": hero_title, "hero_intro": hero_intro, "hero_note": hero_note, "scoring_rule": catalog_scoring_rule, "active": True, "created_by": existing_entry.get("created_by") if existing_entry else (ctx.current_user["username"] if ctx.current_user else "system"), "created_on": existing_entry.get("created_on", china_today_label()) if existing_entry else china_today_label()})
    if not new_entry:
        return start_response_html(start_response, "200 OK", get_series_manage_page(ctx, alert="系列赛目录保存失败。", form_values=form_values))
    updated_catalog = [item for item in catalog if item["competition_name"] != (original_competition_name or competition_name)]
    updated_catalog.append(new_entry)
    save_series_catalog(updated_catalog)
    return start_response_html(start_response, "200 OK", get_series_manage_page(RequestContext(method="GET", path=ctx.path, query={"competition_name": [new_entry["competition_name"]], **({"next": [next_path]} if next_path else {})}, form={}, files={}, current_user=ctx.current_user, now_label=ctx.now_label), alert=(f"{competition_name} 的赛事页信息已更新。" if original_competition_name else f"{competition_name} 已写入系列赛目录。")))
