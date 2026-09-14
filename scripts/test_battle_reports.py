import copy
import json
import unittest
from unittest.mock import patch

import web_app
from web.features import battle_reports


def fixture():
    base = {'match_id': 'a', 'competition_name': '赛事甲', 'season': 'S1',
            'played_on': '2026-09-10', 'stage': 'regular_season', 'round': 1,
            'game_no': 1, 'table_label': 'A桌', 'format': '标准', 'winning_camp': 'villagers',
            'mvp_player_id': 'p1', 'players': [{'player_id': 'p1', 'team_id': 't1', 'points_earned': 1},
                                              {'player_id': 'p2', 'team_id': 't1', 'points_earned': 99}]}
    return {'matches': [dict(copy.deepcopy(base), match_id=f'm{i}', game_no=i) for i in range(1, 5)],
            'players': [{'player_id': 'p1', 'display_name': '真实MVP', 'photo': '/photos/one.jpg'}],
            'teams': [{'team_id': 't1', 'guild_id': 'g1'}],
            'guilds': [{'guild_id': 'g1', 'logo': '/logos/one.png'}]}


class BattleReportTests(unittest.TestCase):
    def setUp(self):
        self.stage_patch = patch.object(web_app, 'resolve_stage_label_for_scope', return_value='常规赛')
        self.stage_patch.start()
        self.addCleanup(self.stage_patch.stop)

    def test_all_matches_and_recorded_mvp_not_highest_score(self):
        data = fixture()
        payload = battle_reports.build_reports(data, '赛事甲', 'S1')
        day = payload['reports'][0]
        self.assertEqual(day['weekday'], '周四')
        matches = day['sections'][0]['matches']
        self.assertEqual([m['game_no'] for m in matches], [1, 2, 3, 4])
        self.assertEqual(matches[0]['mvp']['name'], '真实MVP')
        self.assertEqual(matches[0]['mvp']['guild_logo'], '/logos/one.png')
        self.assertEqual(payload['scope'], {'competition': '赛事甲', 'season': 'S1'})

    def test_scope_placeholders_missing_award_and_stage_groups(self):
        data = fixture()
        base = data['matches'][0]
        data['matches'] += [dict(base, match_id='other', competition_name='赛事乙'),
                            dict(base, match_id='season', season='S2'),
                            dict(base, match_id='placeholder', format='待补录'),
                            dict(base, match_id='unplayed', winning_camp='')]
        data['matches'][1].update(mvp_player_id='', winning_camp='werewolves')
        data['matches'][2]['stage'] = 'finals'
        data['matches'][3]['mvp_player_id'] = 'missing-profile'
        report = battle_reports.build_reports(data, '赛事甲', 'S1')['reports'][0]
        self.assertEqual(len(report['sections']), 2)
        matches = {m['match_id']: m for section in report['sections'] for m in section['matches']}
        self.assertEqual(len(matches), 4)
        self.assertEqual(matches['m2']['mvp']['name'], '')
        self.assertEqual(matches['m2']['winner_label'], '狼人胜利')
        self.assertEqual(matches['m4']['mvp']['photo'], '')

    def test_date_pagination_never_splits_day(self):
        data = fixture()
        data['matches'].append(dict(data['matches'][0], match_id='older', played_on='2026-09-09'))
        first = battle_reports.build_reports(data, '赛事甲', 'S1', 0, 1)
        second = battle_reports.build_reports(data, '赛事甲', 'S1', 1, 1)
        self.assertEqual(len(first['reports'][0]['sections'][0]['matches']), 4)
        self.assertTrue(first['pagination']['has_more'])
        self.assertEqual(second['reports'][0]['played_on'], '2026-09-09')
        self.assertFalse(second['pagination']['has_more'])
        self.assertEqual(battle_reports.build_reports(data, '赛事甲', 'S2')['reports'], [])

    def test_handler_requires_scope_and_get(self):
        statuses = []
        ctx = web_app.RequestContext(method='GET', path='/api/battle-reports', query={}, form={}, files={}, current_user=None, now_label='now')
        response = battle_reports.handle_api(ctx, lambda status, headers: statuses.append(status))
        self.assertEqual(json.loads(b''.join(response))['code'], 'SCOPE_REQUIRED')
        self.assertEqual(statuses[-1], '400 Bad Request')
        ctx.method = 'POST'
        battle_reports.handle_api(ctx, lambda status, headers: statuses.append(status))
        self.assertEqual(statuses[-1], '405 Method Not Allowed')
        self.assertTrue(web_app.public_api_requires_scope_validation('/api/battle-reports'))

    def test_handler_scoped_pagination_and_invalid_scope(self):
        ctx = web_app.RequestContext(method='GET', path='/api/battle-reports',
            query={'competition': ['赛事甲'], 'season': ['S1'], 'limit': ['1']},
            form={}, files={}, current_user=None, now_label='now')
        statuses = []
        with patch.object(web_app, 'load_validated_data', return_value=fixture()), \
             patch.object(web_app, 'resolve_api_scope_request', return_value=({'competition': '赛事甲', 'season': 'S1'}, None)), \
             patch.object(web_app, 'build_public_api_cache_key', return_value=None):
            result = battle_reports.handle_api(ctx, lambda status, headers: statuses.append(status))
            self.assertEqual(json.loads(b''.join(result))['pagination']['limit'], 1)
            self.assertEqual(statuses[-1], '200 OK')
        with patch.object(web_app, 'load_validated_data', return_value=fixture()), \
             patch.object(web_app, 'resolve_api_scope_request', return_value=(None, ('404 Not Found', {'code': 'SCOPE_NOT_FOUND'}))):
            result = battle_reports.handle_api(ctx, lambda status, headers: statuses.append(status))
            self.assertEqual(json.loads(b''.join(result))['code'], 'SCOPE_NOT_FOUND')


if __name__ == '__main__':
    unittest.main()
