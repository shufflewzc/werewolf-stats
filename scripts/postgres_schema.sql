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
    status_code INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    query_string TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL DEFAULT '',
    ip_address TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

ALTER TABLE access_logs
    ADD COLUMN IF NOT EXISTS request_id TEXT NOT NULL DEFAULT '';
ALTER TABLE access_logs
    ADD COLUMN IF NOT EXISTS status_code INTEGER NOT NULL DEFAULT 0;
ALTER TABLE access_logs
    ADD COLUMN IF NOT EXISTS duration_ms INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    target_type TEXT NOT NULL DEFAULT '',
    target_id TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    ip_address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
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
    team_id TEXT NOT NULL,
    photo TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    is_star_player INTEGER NOT NULL DEFAULT 0 CHECK (is_star_player IN (0, 1)),
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
    scoring_rule_json TEXT NOT NULL DEFAULT '{}',
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
    -- Allows non-profile participants such as NPC while season dimension tables
    -- still keep strict player references.
    player_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
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
    score_breakdown_json TEXT NOT NULL DEFAULT '{}',
    points_available DOUBLE PRECISION NOT NULL,
    stance_pick TEXT NOT NULL,
    stance_correct INTEGER NOT NULL CHECK (stance_correct IN (0, 1)),
    notes TEXT NOT NULL,
    PRIMARY KEY (match_id, sort_order)
);

ALTER TABLE matches
ADD COLUMN IF NOT EXISTS scoring_rule_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE players
DROP CONSTRAINT IF EXISTS players_team_id_fkey;

ALTER TABLE match_players
DROP CONSTRAINT IF EXISTS match_players_team_id_fkey;

ALTER TABLE match_players
ADD COLUMN IF NOT EXISTS score_breakdown_json TEXT NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS season_player_dimension_stats (
    competition_name TEXT NOT NULL,
    season_name TEXT NOT NULL,
    played_on TEXT NOT NULL,
    player_id TEXT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    team_id TEXT NOT NULL DEFAULT '',
    seat INTEGER NOT NULL DEFAULT 0,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (competition_name, season_name, played_on, player_id)
);

ALTER TABLE season_player_dimension_stats
DROP CONSTRAINT IF EXISTS season_player_dimension_stats_team_id_fkey;

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

CREATE INDEX IF NOT EXISTS idx_team_members_player
ON team_members(player_id);

CREATE INDEX IF NOT EXISTS idx_teams_scope
ON teams(competition_name, season_name, active, name);

CREATE INDEX IF NOT EXISTS idx_teams_guild_scope
ON teams(guild_id, competition_name, season_name);

CREATE INDEX IF NOT EXISTS idx_players_team_active
ON players(team_id, active, display_name);

CREATE INDEX IF NOT EXISTS idx_players_display_name
ON players(display_name);

CREATE INDEX IF NOT EXISTS idx_matches_scope_day
ON matches(competition_name, season, played_on, round, game_no);

CREATE INDEX IF NOT EXISTS idx_matches_day
ON matches(played_on, competition_name, season);

CREATE INDEX IF NOT EXISTS idx_matches_stage
ON matches(competition_name, season, stage, group_label);

CREATE INDEX IF NOT EXISTS idx_match_players_match_order
ON match_players(match_id, sort_order);

CREATE INDEX IF NOT EXISTS idx_match_players_player
ON match_players(player_id, match_id);

CREATE INDEX IF NOT EXISTS idx_match_players_team
ON match_players(team_id, match_id);

CREATE INDEX IF NOT EXISTS idx_match_players_camp_result
ON match_players(camp, result);

CREATE INDEX IF NOT EXISTS idx_ai_jobs_created_at
ON ai_jobs(created_at);

CREATE INDEX IF NOT EXISTS idx_ai_job_steps_job_order
ON ai_job_steps(job_id, step_order);

CREATE INDEX IF NOT EXISTS idx_access_logs_created_at
ON access_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_access_logs_path_created_at
ON access_logs(path, created_at);

CREATE INDEX IF NOT EXISTS idx_access_logs_status_created_at
ON access_logs(status_code, created_at);

CREATE INDEX IF NOT EXISTS idx_access_logs_duration_ms
ON access_logs(duration_ms);

CREATE INDEX IF NOT EXISTS idx_access_logs_request_id
ON access_logs(request_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at
ON audit_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_audit_logs_target
ON audit_logs(target_type, target_id, created_at);

CREATE INDEX IF NOT EXISTS idx_audit_logs_username
ON audit_logs(username, created_at);

CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id
ON audit_logs(request_id);

CREATE INDEX IF NOT EXISTS idx_ai_conversations_created_at
ON ai_conversations(created_at);

CREATE INDEX IF NOT EXISTS idx_ai_conversations_scope
ON ai_conversations(competition_name, season_name, created_at);

CREATE INDEX IF NOT EXISTS idx_season_player_dimension_stats_scope
ON season_player_dimension_stats(competition_name, season_name, played_on, player_id);

CREATE INDEX IF NOT EXISTS idx_season_player_dimension_stats_player_scope
ON season_player_dimension_stats(player_id, competition_name, season_name, played_on);

CREATE INDEX IF NOT EXISTS idx_season_player_dimension_stats_team_scope
ON season_player_dimension_stats(team_id, competition_name, season_name, played_on);

CREATE INDEX IF NOT EXISTS idx_season_team_dimension_stats_scope
ON season_team_dimension_stats(competition_name, season_name, played_on, team_id, seat);

CREATE INDEX IF NOT EXISTS idx_season_team_dimension_stats_team_scope
ON season_team_dimension_stats(team_id, competition_name, season_name, played_on);

CREATE INDEX IF NOT EXISTS idx_membership_requests_username
ON membership_requests(username, created_on);

CREATE INDEX IF NOT EXISTS idx_membership_requests_target_team
ON membership_requests(target_team_id, created_on);

CREATE INDEX IF NOT EXISTS idx_membership_requests_scope
ON membership_requests(scope_competition_name, scope_season_name, created_on);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_player_id
ON users(player_id)
WHERE player_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wechat_openid
ON users(wechat_openid)
WHERE wechat_openid != '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wechat_web_openid
ON users(wechat_web_openid)
WHERE wechat_web_openid != '';

ALTER TABLE players
ADD COLUMN IF NOT EXISTS is_star_player INTEGER NOT NULL DEFAULT 0;

INSERT INTO app_meta (meta_key, meta_value)
VALUES ('schema_version', '5')
ON CONFLICT (meta_key) DO UPDATE SET meta_value = EXCLUDED.meta_value;

COMMIT;
