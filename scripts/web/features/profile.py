from __future__ import annotations

from html import escape
from typing import Any
import web_app as legacy

RequestContext = legacy.RequestContext
DEFAULT_PROVINCE_NAME = legacy.DEFAULT_PROVINCE_NAME
DEFAULT_PLAYER_PHOTO = legacy.DEFAULT_PLAYER_PHOTO
DEFAULT_TEAM_LOGO = legacy.DEFAULT_TEAM_LOGO
GENDER_OPTIONS = legacy.GENDER_OPTIONS
build_bound_player_summary = legacy.build_bound_player_summary
build_player_edit_form = legacy.build_player_edit_form
build_player_photo_html = legacy.build_player_photo_html
build_profile_binding_summary = legacy.build_profile_binding_summary
build_region_picker = legacy.build_region_picker
build_unique_slug = legacy.build_unique_slug
can_access_series_management = legacy.can_access_series_management
can_manage_guild = legacy.can_manage_guild
can_manage_matches = legacy.can_manage_matches
build_guild_honor_rows = legacy.build_guild_honor_rows
china_now_label = legacy.china_now_label
china_today_label = legacy.china_today_label
file_value = legacy.file_value
form_value = legacy.form_value
get_team_season_status = legacy.get_team_season_status
get_user_player = legacy.get_user_player
is_admin_user = legacy.is_admin_user
layout = legacy.layout
load_membership_requests = legacy.load_membership_requests
load_users = legacy.load_users
load_validated_data = legacy.load_validated_data
normalize_user_gender = legacy.normalize_user_gender
normalize_user_location = legacy.normalize_user_location
option_tags = legacy.option_tags
parse_aliases_text = legacy.parse_aliases_text
parse_username_list_text = legacy.parse_username_list_text
redirect = legacy.redirect
save_repository_state = legacy.save_repository_state
save_uploaded_user_photo = legacy.save_uploaded_user_photo
start_response_html = legacy.start_response_html
update_user_account_fields = legacy.update_user_account_fields
user_has_permission = legacy.user_has_permission
validate_guild_creation = legacy.validate_guild_creation
validate_profile_update = legacy.validate_profile_update
validate_uploaded_photo = legacy.validate_uploaded_photo


def can_manage_guild_honors(user: dict[str, Any] | None) -> bool:
    return is_admin_user(user) or user_has_permission(user, "guild_honor_manage")
def get_profile_page(
    ctx: RequestContext,
    alert: str = "",
    account_values: dict[str, str] | None = None,
    player_values: dict[str, Any] | None = None,
    guild_form_values: dict[str, str] | None = None,
) -> str:
    current_user = ctx.current_user
    if not current_user:
        return layout("未登录", '<div class="alert alert-danger">请先登录后再访问个人中心。</div>', ctx)

    data = load_validated_data()
    current_player = get_user_player(data, current_user)
    current_account_name = account_values.get("account_display_name") if account_values else (
        current_user.get("display_name") or current_user["username"]
    )
    current_province_name = account_values.get("province_name") if account_values else (
        normalize_user_location(
            str(current_user.get("province_name") or ""),
            str(current_user.get("region_name") or ""),
        )[0]
        or DEFAULT_PROVINCE_NAME
    )
    current_region_name = account_values.get("region_name") if account_values else (
        normalize_user_location(
            str(current_user.get("province_name") or ""),
            str(current_user.get("region_name") or ""),
        )[1]
        or "广州市"
    )
    current_gender = account_values.get("gender") if account_values else (
        normalize_user_gender(str(current_user.get("gender") or "")) or "prefer_not_to_say"
    )
    current_bio = account_values.get("bio") if account_values else str(current_user.get("bio") or "")
    current_account_photo = (
        account_values.get("photo")
        if account_values and account_values.get("photo")
        else str(current_user.get("photo") or DEFAULT_PLAYER_PHOTO)
    )
    current_guild_form = guild_form_values or {
        "name": "",
        "short_name": "",
        "manager_usernames": "",
        "notes": "",
    }
    bound_summary = build_bound_player_summary(data, current_user)
    binding_button = '<a class="btn btn-outline-dark" href="/bindings">管理赛季参赛ID</a>'

    if current_player:
        player_form = {
            **current_player,
            **(player_values or {}),
        }
        editor_html = build_player_edit_form(
            player_form,
            "/profile",
            "保存我的资料",
            account_display_name=current_account_name,
            username=current_user["username"],
            password_note="如不需要修改密码，可以留空。",
            show_account_fields=True,
            account_province_name=current_province_name,
            account_region_name=current_region_name,
            account_gender=current_gender,
            account_bio=current_bio,
            player_section_copy="可以修改当前绑定主档案的名称、别名、备注。头像属于账号资料，不会写回赛季档案。",
            photo_field_label="上传账号头像",
            photo_help_text="账号头像独立于赛季档案保存，支持 PNG、JPG、JPEG、WEBP、GIF、SVG，大小不超过 5 MB。",
            photo_preview_path=current_account_photo,
            photo_preview_name=current_account_name,
            photo_preview_path_label="当前账号头像路径",
        )
        body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="eyebrow mb-3">个人中心</div>
          <h1 class="display-6 fw-semibold mb-3">编辑我的账号与队员资料</h1>
          <p class="mb-0 opacity-75">这里可以修改你的账号显示名称、密码、队员信息，并上传新的照片。</p>
          <div class="d-flex flex-wrap gap-2 mt-3">{binding_button}</div>
        </section>
        {build_profile_binding_summary(bound_summary) if bound_summary else ''}
        {editor_html}
        """
    else:
        body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="eyebrow mb-3">个人中心</div>
          <h1 class="display-6 fw-semibold mb-3">账号资料</h1>
          <p class="mb-0 opacity-75">当前账号还没有绑定队员档案。你可以先上传个人头像，后续再去绑定历史参赛档案，或者认领自己负责的赛季战队。</p>
          <div class="d-flex flex-wrap gap-2 mt-3">{binding_button}</div>
        </section>
        {build_profile_binding_summary(bound_summary) if bound_summary else ''}
        <section class="panel shadow-sm p-3 p-lg-4">
          <div class="form-panel p-3 p-lg-4">
            <form method="post" action="/profile" enctype="multipart/form-data">
              <div class="row g-4">
                <div class="col-12 col-xl-7">
                  <div class="mb-3">
                    <label class="form-label">用户名</label>
                    <input class="form-control" value="{escape(current_user['username'])}" disabled>
                  </div>
                  <div class="mb-3">
                    <label class="form-label">账号显示名称</label>
                    <input class="form-control" name="account_display_name" value="{escape(current_account_name)}">
                  </div>
                  <div class="mb-3">
                    <label class="form-label">所在地区</label>
                    {build_region_picker(current_province_name, current_region_name, "profile-basic", "先选择省份，再选择城市。")}
                  </div>
                  <div class="mb-3">
                    <label class="form-label">性别</label>
                    <select class="form-select" name="gender">
                      {option_tags(GENDER_OPTIONS, current_gender)}
                    </select>
                  </div>
                  <div class="mb-3">
                    <label class="form-label">自我介绍</label>
                    <textarea class="form-control" name="bio" rows="4">{escape(current_bio)}</textarea>
                  </div>
                  <div class="mb-3">
                    <label class="form-label">上传头像</label>
                    <input class="form-control" name="photo_file" type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.svg,image/*">
                    <div class="small text-secondary mt-2">即使还没有绑定队员，也可以先上传个人头像；后续首次绑定主队员时会自动沿用这张头像。</div>
                  </div>
                  <div class="mb-3">
                    <label class="form-label">新密码</label>
                    <input class="form-control" name="password" type="password" autocomplete="new-password">
                  </div>
                  <div class="mb-4">
                    <label class="form-label">确认新密码</label>
                    <input class="form-control" name="password_confirm" type="password" autocomplete="new-password">
                  </div>
                </div>
                <div class="col-12 col-xl-5">
                  <div class="panel h-100 shadow-sm p-3 p-lg-4">
                    <h2 class="section-title mb-3">当前头像预览</h2>
                    <div class="mb-3">{build_player_photo_html(current_account_photo, current_account_name)}</div>
                    <div class="mb-2"><strong>当前头像路径：</strong>{escape(current_account_photo)}</div>
                    <div class="mb-0"><strong>状态：</strong>尚未绑定队员档案</div>
                  </div>
                </div>
              </div>
              <div class="d-flex flex-wrap gap-2 mt-4">
                <button type="submit" class="btn btn-dark">保存账号资料</button>
                <a class="btn btn-outline-dark" href="/team-center">去认领战队</a>
              </div>
            </form>
          </div>
        </section>
        """

    shortcut_links = [
        '<a class="btn btn-outline-dark" href="/team-center">战队认领</a>',
        '<a class="btn btn-outline-dark" href="/bindings">赛季 ID 管理</a>',
    ]
    if can_manage_matches(current_user):
        shortcut_links.append('<a class="btn btn-outline-dark" href="/matches/new">比赛管理</a>')
    if can_access_series_management(current_user):
        shortcut_links.append('<a class="btn btn-outline-dark" href="/series-manage">系列赛管理</a>')
    if is_admin_user(current_user):
        shortcut_links.append('<a class="btn btn-outline-dark" href="/permissions">权限控制</a>')

    manageable_guilds = [
        guild for guild in sorted(data.get("guilds", []), key=lambda item: item["name"])
        if can_manage_guild(current_user, guild) or can_manage_guild_honors(current_user)
    ]
    pending_requests = load_membership_requests()
    guild_management_cards = []
    for guild in manageable_guilds:
        guild_team_rows = [
            team
            for team in data["teams"]
            if str(team.get("guild_id") or "").strip() == guild["guild_id"]
        ]
        ongoing_team_count = sum(
            1 for team in guild_team_rows if get_team_season_status(data, team) == "ongoing"
        )
        pending_count = sum(
            1
            for item in pending_requests
            if item.get("request_type") == "guild_join"
            and item.get("target_guild_id") == guild["guild_id"]
        )
        honor_count = len(build_guild_honor_rows(data, guild["guild_id"]))
        can_manage_team_ops = can_manage_guild(current_user, guild)
        guild_management_cards.append(
            f"""
            <div class="col-12 col-xl-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">门派管理</div>
                    <h3 class="h5 mb-1">{escape(guild['name'])}</h3>
                    <div class="small-muted">{escape(guild.get('notes') or '长期存在的门派组织。')}</div>
                  </div>
                  <span class="chip">待审申请 {pending_count}</span>
                </div>
                <div class="row g-3 mt-2">
                  <div class="col-6"><div class="small text-secondary">进行中战队</div><div class="fw-semibold">{ongoing_team_count}</div></div>
                  <div class="col-3"><div class="small text-secondary">历届战队</div><div class="fw-semibold">{max(len(guild_team_rows) - ongoing_team_count, 0)}</div></div>
                  <div class="col-3"><div class="small text-secondary">荣誉</div><div class="fw-semibold">{honor_count}</div></div>
                </div>
                <div class="d-flex flex-wrap gap-2 mt-3">
                  <a class="btn btn-sm btn-dark" href="/guilds/{escape(guild['guild_id'])}?view=manage">{'管理门派' if can_manage_team_ops else '维护荣誉'}</a>
                  <a class="btn btn-sm btn-outline-dark" href="/guilds/{escape(guild['guild_id'])}">查看对外页面</a>
                </div>
              </div>
            </div>
            """
        )

    guild_create_panel = ""
    if user_has_permission(current_user, "guild_manage"):
        guild_create_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">创建门派</h2>
              <p class="section-copy mb-0">门派创建入口现在放在个人中心里，对外门派页只保留展示内容。</p>
            </div>
          </div>
          <form method="post" action="/profile">
            <input type="hidden" name="action" value="create_guild">
            <div class="row g-3">
              <div class="col-12 col-lg-6">
                <label class="form-label">门派名称</label>
                <input class="form-control" name="name" value="{escape(current_guild_form['name'])}">
              </div>
              <div class="col-12 col-lg-6">
                <label class="form-label">门派简称</label>
                <input class="form-control" name="short_name" value="{escape(current_guild_form['short_name'])}">
              </div>
              <div class="col-12">
                <label class="form-label">门派管理员账号</label>
                <input class="form-control" name="manager_usernames" value="{escape(current_guild_form['manager_usernames'])}" placeholder="可填多个用户名，用逗号或换行分隔">
              </div>
              <div class="col-12">
                <label class="form-label">门派说明</label>
                <textarea class="form-control" name="notes" rows="3">{escape(current_guild_form['notes'])}</textarea>
              </div>
            </div>
            <button type="submit" class="btn btn-dark mt-4">创建门派</button>
          </form>
        </section>
        """

    guild_management_section = ""
    if guild_management_cards:
        guild_management_section = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">我的门派管理</h2>
              <p class="section-copy mb-0">这里只放门派管理入口；对外门派页默认展示当前正在进行的赛季战队。</p>
            </div>
          </div>
          <div class="row g-3">{''.join(guild_management_cards)}</div>
        </section>
        """

    management_center_html = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">管理入口</h2>
          <p class="section-copy mb-0">把战队、门派、赛事和数据维护入口集中放在这里，对外页面只展示公开信息。</p>
        </div>
      </div>
      <div class="d-flex flex-wrap gap-2">{''.join(shortcut_links)}</div>
    </section>
    {guild_create_panel}
    {guild_management_section}
    """
    body += management_center_html

    return layout("个人中心", body, ctx, alert=alert)

def handle_profile(ctx: RequestContext, start_response):
    current_user = ctx.current_user
    if not current_user:
        return redirect(start_response, "/login?next=/profile")

    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_profile_page(ctx))

    data = load_validated_data()
    users = load_users()
    current_player = get_user_player(data, current_user)
    action = form_value(ctx.form, "action").strip() or "save_profile"
    if action == "create_guild":
        if not user_has_permission(current_user, "guild_manage"):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有具备门派管理权限的账号才能创建门派。</div>', ctx),
            )
        name = form_value(ctx.form, "name").strip()
        short_name = form_value(ctx.form, "short_name").strip()
        manager_usernames_text = form_value(ctx.form, "manager_usernames")
        notes = form_value(ctx.form, "notes").strip()
        manager_usernames = [
            username
            for username in parse_username_list_text(manager_usernames_text)
            if username != current_user["username"]
        ]
        error = validate_guild_creation(
            name,
            short_name,
            manager_usernames,
            data.get("guilds", []),
            users,
        )
        if error:
            return start_response_html(
                start_response,
                "200 OK",
                get_profile_page(
                    ctx,
                    alert=error,
                    guild_form_values={
                        "name": name,
                        "short_name": short_name,
                        "manager_usernames": manager_usernames_text,
                        "notes": notes,
                    },
                ),
            )
        data.setdefault("guilds", []).append(
            {
                "guild_id": build_unique_slug(
                    {guild["guild_id"] for guild in data.get("guilds", [])},
                    "guild",
                    name,
                    "guild",
                ),
                "name": name,
                "short_name": short_name,
                "logo": DEFAULT_TEAM_LOGO,
                "active": True,
                "founded_on": china_today_label(),
                "leader_username": current_user["username"],
                "manager_usernames": manager_usernames,
                "honors": [],
                "notes": notes or "由网站创建的长期门派组织。",
            }
        )
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_profile_page(ctx, alert="创建门派失败：" + "；".join(errors[:3])),
            )
        refreshed_ctx = RequestContext(
            method="GET",
            path="/profile",
            query={},
            form={},
            files={},
            current_user=current_user,
            now_label=china_now_label(),
        )
        return start_response_html(
            start_response,
            "200 OK",
            get_profile_page(refreshed_ctx, alert=f"门派 {name} 已创建。"),
        )

    account_display_name = form_value(ctx.form, "account_display_name").strip()
    province_name = form_value(ctx.form, "province_name", DEFAULT_PROVINCE_NAME).strip()
    region_name = form_value(ctx.form, "region_name", "广州市").strip()
    gender = form_value(ctx.form, "gender", "prefer_not_to_say").strip()
    bio = form_value(ctx.form, "bio").strip()
    password = form_value(ctx.form, "password")
    password_confirm = form_value(ctx.form, "password_confirm")
    player_display_name = form_value(ctx.form, "player_display_name").strip()
    aliases_raw = form_value(ctx.form, "aliases")
    notes = form_value(ctx.form, "notes").strip()
    upload = file_value(ctx.files, "photo_file")

    error = validate_profile_update(
        account_display_name,
        province_name,
        region_name,
        gender,
        bio,
        password,
        password_confirm,
        player_display_name if current_player else "",
    )
    if not error:
        error = validate_uploaded_photo(upload)
    if error:
        player_values = None
        if current_player:
            player_values = {
                **current_player,
                "display_name": player_display_name or current_player["display_name"],
                "aliases": parse_aliases_text(aliases_raw),
                "notes": notes,
            }
        return start_response_html(
            start_response,
            "200 OK",
            get_profile_page(
                ctx,
                alert=error,
                account_values={
                    "account_display_name": account_display_name,
                    "province_name": province_name or DEFAULT_PROVINCE_NAME,
                    "region_name": region_name or "广州市",
                    "gender": gender or "prefer_not_to_say",
                    "bio": bio,
                },
                player_values=player_values,
            ),
        )

    new_account_photo = save_uploaded_user_photo(current_user["username"], upload)
    users = update_user_account_fields(
        users,
        current_user["username"],
        account_display_name,
        province_name,
        region_name,
        gender,
        bio,
        password,
        new_account_photo,
    )
    if current_player:
        for player in data["players"]:
            if player["player_id"] != current_player["player_id"]:
                continue
            player["display_name"] = player_display_name
            player["aliases"] = parse_aliases_text(aliases_raw)
            player["notes"] = notes
            break

    errors = save_repository_state(data, users)
    if errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_profile_page(ctx, alert="保存失败：" + "；".join(errors[:3])),
        )

    refreshed_user = next((user for user in users if user["username"] == current_user["username"]), current_user)
    refreshed_ctx = RequestContext(
        method="GET",
        path="/profile",
        query={},
        form={},
        files={},
        current_user=refreshed_user,
        now_label=china_now_label(),
    )
    message = "账号资料已更新。" if not current_player else "账号资料和队员资料已更新。"
    return start_response_html(start_response, "200 OK", get_profile_page(refreshed_ctx, alert=message))
