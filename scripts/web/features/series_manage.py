from __future__ import annotations

import web_app as legacy

RequestContext = legacy.RequestContext
DEFAULT_REGION_NAME = legacy.DEFAULT_REGION_NAME
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
normalize_series_catalog_entry = legacy.normalize_series_catalog_entry
require_competition_catalog_manager = legacy.require_competition_catalog_manager
require_competition_season_manager = legacy.require_competition_season_manager
save_membership_requests = legacy.save_membership_requests
save_repository_state = legacy.save_repository_state
save_season_catalog = legacy.save_season_catalog
save_series_catalog = legacy.save_series_catalog
season_status_label = legacy.season_status_label
start_response_html = legacy.start_response_html


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
        "edit_mode": requested_edit_mode,
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
            }
        )
    if form_values:
        current_form.update(form_values)
        season_form.update(
            {
                key: form_values[key]
                for key in ("competition_name", "original_season_name", "season_name", "start_at", "end_at", "notes", "edit_mode")
                if key in form_values
            }
        )
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
          </div>
        </section>
        """

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    season_cards = []
    for season_entry in competition_season_entries:
        season_detail_path = build_series_manage_path(selected_competition_name, current_form["next"], season_entry["season_name"])
        season_edit_path = build_series_manage_path(selected_competition_name, current_form["next"], season_entry["season_name"], "season")
        registered_team_names = [team_lookup[team_id]["name"] for team_id in season_entry.get("registered_team_ids", []) if team_id in team_lookup]
        season_cards.append(
            f"""
            <div class="col-12 col-lg-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">赛季档期</div>
                    <h2 class="h5 mb-2">{escape(season_entry['season_name'])}</h2>
                    <div class="small-muted">起止时间 {escape(format_datetime_local_label(season_entry.get('start_at', '')))} - {escape(format_datetime_local_label(season_entry.get('end_at', '')))}</div>
                    <div class="small-muted mt-1">状态 {escape(season_status_label(season_entry))} · 已报名战队 {len(season_entry.get('registered_team_ids', []))} 支</div>
                  </div>
                  <span class="chip">{'当前赛季' if season_entry['season_name'] == requested_season_name else escape(season_status_label(season_entry))}</span>
                </div>
                <p class="section-copy mt-3 mb-2">{escape(season_entry.get('notes') or '这个赛季还没有补充说明。')}</p>
                <div class="small-muted">{escape('、'.join(registered_team_names) if registered_team_names else '当前还没有战队报名。')}</div>
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
                    target_season_entry = get_season_entry(season_catalog, selected_series_slug, target_season_name, competition_name=selected_competition_name)
                    selected_season_has_matches = any(get_match_competition_name(match) == selected_competition_name and str(match.get("season") or "").strip() == target_season_name for match in data["matches"])
                    selected_season_registered_team_count = len(target_season_entry.get("registered_team_ids", [])) if target_season_entry else 0
                    delete_button_disabled = ""
                    delete_button_confirm = " onclick=\"return confirm('确认强制删除当前赛季吗？这会一并删除该赛季的比赛记录和报名记录，且不可恢复。')\""
                    if can_force_delete_selected_season:
                        if selected_season_has_matches or selected_season_registered_team_count:
                            delete_season_helper_html = f'<div class="small text-secondary">仅管理员可强制删除赛季。当前操作会同步清掉 {selected_season_registered_team_count} 支已报名战队，以及该赛季下的全部比赛记录。</div>'
                        else:
                            delete_season_helper_html = '<div class="small text-secondary">当前赛季还没有比赛记录和报名记录，管理员可以直接删除。</div>'
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
                          <button type="submit" class="btn btn-outline-danger"{delete_button_disabled}{delete_button_confirm}>强制删除当前赛季</button>
                        </form>
                        """
                season_form_title = "编辑赛季档期" if season_form["original_season_name"] else "新建赛季档期"
                season_cancel_path = build_series_manage_path(selected_competition_name, current_form["next"], season_form["original_season_name"] or requested_season_name or None)
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
                      <div class="col-12"><label class="form-label">赛季说明</label><textarea class="form-control" name="notes" rows="3" placeholder="可写赛季定位、报名要求或档期说明。">{escape(season_form['notes'])}</textarea></div>
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
        next_path = form_value(ctx.form, "next").strip()
        permission_guard = require_competition_season_manager(ctx, start_response, data, competition_name, "你只能编辑自己负责地区系列赛下的赛季。")
        if permission_guard is not None:
            return permission_guard
        selected_entry = get_series_entry_by_competition(catalog, competition_name)
        series_slug = selected_entry["series_slug"] if selected_entry else ""
        form_values = {"competition_name": competition_name, "original_season_name": original_season_name, "season_name": season_name, "start_at": start_at, "end_at": end_at, "notes": notes, "original_competition_name": competition_name, "next": next_path, "edit_mode": edit_mode}
        error = legacy.validate_season_catalog_form(series_slug, season_name, start_at, end_at)
        if error:
            return start_response_html(start_response, "200 OK", get_series_manage_page(ctx, alert=error, form_values=form_values))
        lookup_season_name = original_season_name or season_name
        existing_entry = get_season_entry(season_catalog, series_slug, lookup_season_name, competition_name=competition_name)
        new_entry = normalize_season_catalog_entry({"series_slug": series_slug, "series_name": selected_entry["series_name"] if selected_entry else "", "series_code": selected_entry["series_code"] if selected_entry else "", "competition_name": competition_name, "season_name": season_name, "start_at": start_at, "end_at": end_at, "notes": notes, "registered_team_ids": existing_entry.get("registered_team_ids", []) if existing_entry else [], "created_by": existing_entry.get("created_by") if existing_entry else (ctx.current_user["username"] if ctx.current_user else "system"), "created_on": existing_entry.get("created_on", china_today_label()) if existing_entry else china_today_label()})
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
        return start_response_html(start_response, "200 OK", get_series_manage_page(RequestContext(method="GET", path=ctx.path, query={"competition_name": [competition_name], **({"next": [next_path]} if next_path else {})}, form={}, files={}, current_user=ctx.current_user, now_label=ctx.now_label), alert=f"{competition_name} / {season_name} 已强制删除，并清空了该赛季的比赛与报名记录。"))
    series_name = form_value(ctx.form, "series_name").strip()
    series_code = form_value(ctx.form, "series_code").strip()
    region_name = form_value(ctx.form, "region_name").strip()
    competition_name = form_value(ctx.form, "competition_name").strip()
    summary = form_value(ctx.form, "summary").strip()
    page_badge = form_value(ctx.form, "page_badge").strip()
    hero_title = form_value(ctx.form, "hero_title").strip()
    hero_intro = form_value(ctx.form, "hero_intro").strip()
    hero_note = form_value(ctx.form, "hero_note").strip()
    original_competition_name = form_value(ctx.form, "original_competition_name").strip()
    next_path = form_value(ctx.form, "next").strip()
    edit_mode = form_value(ctx.form, "edit_mode").strip() or ("catalog" if original_competition_name else "create")
    form_values = {"series_name": series_name, "series_code": series_code, "region_name": region_name, "competition_name": competition_name, "summary": summary, "page_badge": page_badge, "hero_title": hero_title, "hero_intro": hero_intro, "hero_note": hero_note, "original_competition_name": original_competition_name, "next": next_path, "edit_mode": edit_mode}
    error = legacy.validate_series_catalog_form(series_name, region_name, competition_name)
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
    new_entry = normalize_series_catalog_entry({"series_name": series_name, "series_code": series_code, "region_name": region_name, "competition_name": competition_name, "series_slug": existing_entry["series_slug"] if existing_entry else "", "summary": summary, "page_badge": page_badge, "hero_title": hero_title, "hero_intro": hero_intro, "hero_note": hero_note, "active": True, "created_by": existing_entry.get("created_by") if existing_entry else (ctx.current_user["username"] if ctx.current_user else "system"), "created_on": existing_entry.get("created_on", china_today_label()) if existing_entry else china_today_label()})
    if not new_entry:
        return start_response_html(start_response, "200 OK", get_series_manage_page(ctx, alert="系列赛目录保存失败。", form_values=form_values))
    updated_catalog = [item for item in catalog if item["competition_name"] != (original_competition_name or competition_name)]
    updated_catalog.append(new_entry)
    save_series_catalog(updated_catalog)
    return start_response_html(start_response, "200 OK", get_series_manage_page(RequestContext(method="GET", path=ctx.path, query={"competition_name": [new_entry["competition_name"]], **({"next": [next_path]} if next_path else {})}, form={}, files={}, current_user=ctx.current_user, now_label=ctx.now_label), alert=(f"{competition_name} 的赛事页信息已更新。" if original_competition_name else f"{competition_name} 已写入系列赛目录。")))
