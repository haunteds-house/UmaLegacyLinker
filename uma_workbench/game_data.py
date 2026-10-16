"""Read-only game records shared by planning tools; never download game data."""
from collections import defaultdict
from dataclasses import dataclass, field
from contextlib import closing
import re
import sqlite3

from uma_legacy_linker.parent_optimizer import AffinityResolver


@dataclass
class GameData:
    texts: dict = field(default_factory=dict)
    programs: list = field(default_factory=list)
    rewards: dict = field(default_factory=dict)
    fans: dict = field(default_factory=dict)
    turns: dict = field(default_factory=dict)
    lessons: list = field(default_factory=list)
    bonuses: dict = field(default_factory=dict)
    concerts: list = field(default_factory=list)
    training: list = field(default_factory=list)
    tt_scores: list = field(default_factory=list)
    _objectives: dict = field(default_factory=dict)

    @classmethod
    def load(cls, master):
        result = cls()
        if not master.path:
            return result
        with master.connection() as con:
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            def rows(name):
                return [dict(row) for row in con.execute('SELECT * FROM "' + name + '"')] if name in tables else []
            result.texts = {(row['category'], row['index']): re.sub(r'<[^>]*>', '', row['text']) for row in rows('text_data')}
            races = {row['id']: row for row in rows('race')}
            instances = {row['id']: row for row in rows('race_instance')}
            courses = {row['id']: row for row in rows('race_course_set')}
            for row in rows('single_mode_program'):
                instance = instances.get(row['race_instance_id'], {})
                race = races.get(instance.get('race_id'), {})
                course = courses.get(race.get('course_set'), {})
                result.programs.append({**row, 'name': result.texts.get((28, row['race_instance_id']), 'Career race'),
                    'distance': course.get('distance'), 'ground': course.get('ground'),
                    'course_id': course.get('id'), 'grade': race.get('grade'), 'track': course.get('race_track_id'),
                    'rotation':course.get('turn',1)})
            for row in rows('single_mode_reward_set'):
                result.rewards.setdefault(row['reward_set_id'], []).append(row)
            for row in rows('single_mode_fan_count'):
                if row['order'] == 1:
                    result.fans[row['fan_set_id']] = row['fan_count']
            for row in rows('single_mode_turn'):
                result.turns.setdefault(row['turn_set_id'], {})[row['turn']] = row
            result.lessons = rows('single_mode_live_square')
            result.bonuses = {row['id']: row for row in rows('single_mode_live_master_bonus')}
            result.concerts = rows('single_mode_live_live_data')
            result.training = rows('single_mode_training_effect')
            result.tt_scores = rows('team_stadium_raw_score')
        return result

    def name(self, category, identity, fallback='Name unavailable'):
        return self.texts.get((category, identity), fallback)

    def objectives(self, master, card_id):
        if card_id not in self._objectives:
            self._objectives[card_id] = []
            if master.path:
                try:
                    with closing(AffinityResolver(master.path)) as resolver:
                        self._objectives[card_id] = resolver.objective_races(master.character_id(card_id))
                except (ValueError, RuntimeError, sqlite3.Error):
                    pass
        return self._objectives[card_id]


def game_data(master):
    cached = getattr(master, '_extended_game_data', None)
    key = str(master.path), master.sha256
    if not cached or cached[0] != key:
        cached = master._extended_game_data = key, GameData.load(master)
    return cached[1]


def reward_routes(master, item_ids, *, finish=1):
    """Expected item drops per race entry, using MDB millionth probabilities."""
    data = game_data(master)
    wanted = set(map(int, item_ids))
    routes = []
    seen = set()
    for program in data.programs:
        expected = defaultdict(float)
        for reward in data.rewards.get(program.get('reward_set_id'), []):
            if (reward.get('item_id') in wanted and reward.get('order_min', 1) <= finish <= reward.get('order_max', 18)
                    and not reward.get('bonus')):
                expected[reward['item_id']] += reward.get('item_num', 0) * min(1., max(0., reward.get('odds', 0) / 1000000))
        signature = program['race_instance_id'], tuple(sorted(expected.items()))
        if expected and signature not in seen:
            seen.add(signature)
            routes.append({**program, 'items': dict(expected), 'provenance': 'Local game reward table', 'finish': finish})
    return routes
