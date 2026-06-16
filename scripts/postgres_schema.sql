-- PostgreSQL target schema for werewolf-stats.
-- This is intentionally close to the current SQLite schema so migration can be
-- rehearsed before the application runtime is switched to PostgreSQL.

BEGIN;

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    player_id TEXT UNIQUE,
    linked_player_ids_json TEXT NOT NULL DEFAULT '[]',
    manager_scope_keys_json TEXT NOT NULL DEFAULT '[]',
    permissions_json TEXT NOT NULL DEFAULT '[]',
    role TEXT NOT NULL DEFAULT 'member',
    province_name TEXT NOT NULL DEFAULT '',
    region_name TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    bio TEXT NOT NULL DEFAULT '',
    photo TEXT NOT NULL DEFAULT 'assets/players/default-player.svg',
    wechat_openid TEXT NOT NULL DEFAULT '',
    wechat_web_openid TEXT NOT NULL DEFAULT '',
    wechat_unionid TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS app_meta (
    meta_key TEXT PRIMARY KEY,
    meta_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    scope_type TEXT NOT NULL DEFAULT '',
    scope_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error_message TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS ai_job_steps (
    step_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES ai_jobs(job_id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    step_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL DEFAULT '',
    input_summary TEXT NOT NULL DEFAULT '',
    output_summary TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS access_logs (
    log_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL,
    method TEXT NOT NULL,
    query_string TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL DEFAULT '',
    ip_address TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_conversations (
    conversation_id TEXT PRIMARY KEY,
    competition_name TEXT NOT NULL DEFAULT '',
    season_name TEXT NOT NULL DEFAULT '',
    region_name TEXT NOT NULL DEFAULT '',
    series_slug TEXT NOT NULL DEFAULT '',
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS user_sessions (
    session_token TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS guilds (
    guild_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    logo TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    founded_on TEXT NOT NULL,
    leader_username TEXT NOT NULL,
    manager_usernames_json TEXT NOT NULL DEFAULT '[]',
    honors_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    logo TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    founded_on TEXT NOT NULL,
    competition_name TEXT NOT NULL DEFAULT '',
    season_name TEXT NOT NULL DEFAULT '',
    guild_id TEXT NOT NULL DEFAULT '',
    captain_player_id TEXT,
    stage_groups_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id TEXT NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    player_id TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY (team_id, player_id)
);

CREATE TABLE IF NOT EXISTS players (
    player_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    team_id TEXT NOT NULL REFERENCES teams(team_id),
    photo TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    joined_on TEXT NOT NULL,
    notes TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    competition_name TEXT NOT NULL,
    season TEXT NOT NULL,
    stage TEXT NOT NULL,
    round INTEGER NOT NULL,
    game_no INTEGER NOT NULL,
    score_model TEXT NOT NULL DEFAULT 'standard',
    exclude_from_team_scores INTEGER NOT NULL DEFAULT 0,
    played_on TEXT NOT NULL,
    group_label TEXT NOT NULL DEFAULT '',
    table_label TEXT NOT NULL,
    format TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    winning_camp TEXT NOT NULL,
    mvp_player_id TEXT NOT NULL DEFAULT '',
    svp_player_id TEXT NOT NULL DEFAULT '',
    scapegoat_player_id TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_players (
    match_id TEXT NOT NULL REFERENCES matches(match_id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL,
    player_id TEXT NOT NULL REFERENCES players(player_id),
    team_id TEXT NOT NULL REFERENCES teams(team_id),
    seat INTEGER NOT NULL,
    role TEXT NOT NULL,
    camp TEXT NOT NULL,
    survived INTEGER NOT NULL CHECK (survived IN (0, 1)),
    result TEXT NOT NULL,
    points_earned DOUBLE PRECISION NOT NULL,
    result_points DOUBLE PRECISION NOT NULL DEFAULT 0,
    vote_points DOUBLE PRECISION NOT NULL DEFAULT 0,
    behavior_points DOUBLE PRECISION NOT NULL DEFAULT 0,
    special_points DOUBLE PRECISION NOT NULL DEFAULT 0,
    adjustment_points DOUBLE PRECISION NOT NULL DEFAULT 0,
    points_available DOUBLE PRECISION NOT NULL,
    stance_pick TEXT NOT NULL,
    stance_correct INTEGER NOT NULL CHECK (stance_correct IN (0, 1)),
    notes TEXT NOT NULL,
    PRIMARY KEY (match_id, sort_order)
);

CREATE TABLE IF NOT EXISTS season_player_dimension_stats (
    competition_name TEXT NOT NULL,
    season_name TEXT NOT NULL,
    played_on TEXT NOT NULL,
    player_id TEXT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    team_id TEXT NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    seat INTEGER NOT NULL DEFAULT 0,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (competition_name, season_name, played_on, player_id)
);

CREATE TABLE IF NOT EXISTS season_team_dimension_stats (
    competition_name TEXT NOT NULL,
    season_name TEXT NOT NULL,
    played_on TEXT NOT NULL,
    team_id TEXT NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
    seat INTEGER NOT NULL DEFAULT 0,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (competition_name, season_name, played_on, team_id, seat)
);

CREATE TABLE IF NOT EXISTS membership_requests (
    request_id TEXT PRIMARY KEY,
    request_type TEXT NOT NULL,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    player_id TEXT,
    source_team_id TEXT,
    target_team_id TEXT NOT NULL,
    target_guild_id TEXT NOT NULL DEFAULT '',
    scope_competition_name TEXT NOT NULL DEFAULT '',
    scope_season_name TEXT NOT NULL DEFAULT '',
    request_payload_json TEXT NOT NULL DEFAULT '{}',
    created_on TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_team_members_team_order
ON team_members(team_id, sort_order);

CREATE INDEX IF NOT EXISTS idx_match_players_match_order
ON match_players(match_id, sort_order);

CREATE INDEX IF NOT EXISTS idx_ai_jobs_created_at
ON ai_jobs(created_at);

CREATE INDEX IF NOT EXISTS idx_ai_job_steps_job_order
ON ai_job_steps(job_id, step_order);

CREATE INDEX IF NOT EXISTS idx_access_logs_created_at
ON access_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_access_logs_path_created_at
ON access_logs(path, created_at);

CREATE INDEX IF NOT EXISTS idx_ai_conversations_created_at
ON ai_conversations(created_at);

CREATE INDEX IF NOT EXISTS idx_ai_conversations_scope
ON ai_conversations(competition_name, season_name, created_at);

CREATE INDEX IF NOT EXISTS idx_season_player_dimension_stats_scope
ON season_player_dimension_stats(competition_name, season_name, played_on, player_id);

CREATE INDEX IF NOT EXISTS idx_season_team_dimension_stats_scope
ON season_team_dimension_stats(competition_name, season_name, played_on, team_id, seat);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_player_id
ON users(player_id)
WHERE player_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wechat_openid
ON users(wechat_openid)
WHERE wechat_openid != '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wechat_web_openid
ON users(wechat_web_openid)
WHERE wechat_web_openid != '';

COMMIT;
