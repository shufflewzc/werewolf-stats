"""Public, date-paginated MVP reports from recorded match awards."""
from collections import defaultdict
from datetime import date

import web_app as legacy


def build_reports(data, competition, season, offset=0, limit=10):
    players = {p['player_id']: p for p in data.get('players', [])}
    teams = {t['team_id']: t for t in data.get('teams', [])}
    guilds = {g['guild_id']: g for g in data.get('guilds', [])}
    days = defaultdict(list)
    for match in data.get('matches', []):
        if (legacy.match_in_scope(match, competition, season)
                and legacy.is_match_counted_as_played(match)
                and match.get('winning_camp') in ('villagers', 'werewolves')
                and legacy.parse_match_day(str(match.get('played_on') or ''))):
            days[match['played_on']].append(match)
    dates = sorted(days, reverse=True)
    reports = []
    for played_on in dates[offset:offset + limit]:
        sections = {}
        for match in sorted(days[played_on], key=lambda m: (
                str(m.get('stage') or ''), int(m.get('round') or 0),
                int(m.get('game_no') or 0), str(m.get('table_label') or ''), m['match_id'])):
            stage = str(match.get('stage') or '')
            if stage not in sections:
                sections[stage] = {'stage': stage, 'stage_label': legacy.resolve_stage_label_for_scope(
                    data, competition, season, stage), 'matches': []}
            player_id = str(match.get('mvp_player_id') or '').strip()
            participant = next((p for p in match.get('players', []) if p.get('player_id') == player_id), {})
            player = players.get(player_id, {})
            team = teams.get(participant.get('team_id'), {})
            guild = guilds.get(team.get('guild_id'), {})
            sections[stage]['matches'].append({
                'match_id': match['match_id'], 'round': match.get('round'),
                'game_no': match.get('game_no'), 'table_label': match.get('table_label') or '',
                'winning_camp': match['winning_camp'],
                'winner_label': '好人胜利' if match['winning_camp'] == 'villagers' else '狼人胜利',
                'mvp': {'player_id': player_id,
                        'name': player.get('display_name') or match.get('mvp_player_name') or player_id,
                        'photo': player.get('photo') or '', 'guild_logo': guild.get('logo') or ''},
            })
        reports.append({'played_on': played_on, 'weekday': '周' + '一二三四五六日'[date.fromisoformat(played_on).weekday()],
                        'sections': list(sections.values())})
    return {'scope': {'competition': competition, 'season': season}, 'reports': reports,
            'pagination': {'offset': offset, 'limit': limit, 'total': len(dates),
                           'has_more': offset + limit < len(dates)}}


def handle_api(ctx, start_response):
    if ctx.method != 'GET':
        return legacy.start_response_json(start_response, '405 Method Not Allowed',
            {'error': 'battle reports only supports GET'}, headers=[('Allow', 'GET')])
    competition = legacy.form_value(ctx.query, 'competition').strip()
    season = legacy.form_value(ctx.query, 'season').strip()
    if not competition or not season:
        return legacy.start_response_json(start_response, '400 Bad Request',
            {'code': 'SCOPE_REQUIRED', 'error': '请先选择赛事和赛季。'})
    data = legacy.load_validated_data()
    _, error = legacy.resolve_api_scope_request(ctx, data)
    if error:
        return legacy.start_response_json(start_response, *error)
    offset, limit = legacy.parse_api_pagination(ctx, default_limit=10, max_limit=30) or (0, 10)
    return legacy.start_cached_public_api_json(ctx, start_response,
        legacy.build_public_api_cache_key(ctx, 'battle_reports'),
        lambda: build_reports(data, competition, season, offset, limit))
