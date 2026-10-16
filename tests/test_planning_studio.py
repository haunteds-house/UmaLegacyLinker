"""End-to-end planning acceptance checks, without private game files."""
import itertools
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from uma_workbench.core import MasterData,Store
from uma_workbench.career import CareerModel,career_options,inheritance_profile,validate_careers
from uma_workbench.game_data import GameData,reward_routes
from uma_workbench.planning import APTITUDES,PlanningCatalog
from uma_workbench.projects import generate_project,project_status,sync_projects
from uma_workbench.reference import skill_profile,rank_skills,compare_supports
from uma_workbench.racing import assign_team,quick_evaluation,simulate_field
from uma_workbench.strategy import concert_catalog,plan_concert,spending_advice
from uma_workbench.analysis import forecast_plan,retain_forecast,forecast_runners
from tests.test_workbench_training import training_data


from uma_workbench.smoke_data import make_profile as fixture


class PlanningStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store,self.master=fixture(self.temp.name)
        self.req={'scenario':'URA','role':'TT','surface':'Turf','distance_type':'Mile','style':'Pace Chaser',
            'card_id':100101,'stats':{},'skill_ids':[],'max_attempts':10,'stop_condition':'Meet targets',
            'career':{'runs':4,'race_success':1.,'event_frequency':0.}}
        self.trainee=self.store.entities('trainees')[0]
        self.deck=[{**row,'borrowed':i==5} for i,row in enumerate(self.store.entities('supports')[:6])]

    def tearDown(self):self.temp.cleanup()

    def test_career_seeded_ranges_turns_energy_and_caps(self):
        model=CareerModel(self.store,self.master,self.req)
        a=model.forecast(self.trainee,self.deck);b=model.forecast(self.trainee,self.deck)
        self.assertEqual(a,b);self.assertTrue(a['available']);self.assertTrue(a['complete_deck'])
        self.assertEqual(len(a['timeline']),78)
        self.assertTrue(all(0<=r['energy']<=100 for r in a['timeline']))
        self.assertTrue(all(0<=r[key]<=1200 for r in a['samples'] for key in ('speed','stamina','power','guts','wiz')))
        self.assertGreater(a['actions'].get('rests',0),0)
        self.assertEqual(a['completion_rate'],1.)

    def test_failed_required_race_exhausts_continues(self):
        req={**self.req,'career':{**self.req['career'],'race_success':0.,'continues':0}}
        result=CareerModel(self.store,self.master,req).forecast(self.trainee,self.deck)
        self.assertEqual(result['completion_rate'],0.)
        self.assertEqual(result['target_rate'],0.)

    def test_full_deck_rejects_six_owned_and_duplicate_characters(self):
        model=CareerModel(self.store,self.master,self.req)
        with self.assertRaisesRegex(ValueError,'five owned'):model.forecast(self.trainee,[{**r,'borrowed':False} for r in self.deck])
        with self.assertRaisesRegex(ValueError,'one slot'):model.forecast(self.trainee,[self.deck[0],self.deck[0]])

    def test_all_four_scenarios_and_concert_schedule_are_executable(self):
        for name in ('URA','Unity Cup','Trackblazer','Our Grand Concert'):
            req={**self.req,'scenario':name,'career':{**self.req['career'],'concert_purchases':[{'id':1,'turn':1}]}}
            result=CareerModel(self.store,self.master,req).forecast(self.trainee,self.deck)
            self.assertTrue(result['available'],name)
            self.assertEqual(len(result['samples']),4)

    def test_invalid_assumptions_and_unaffordable_skill_are_not_claimed(self):
        with self.assertRaises(ValueError):career_options({'career':{'continues':-1}})
        self.master._planning_catalog.costs[101]=100000
        result=CareerModel(self.store,self.master,{**self.req,'skill_ids':[101]}).forecast(self.trainee,self.deck)
        self.assertEqual(result['skill_rates'][101],0.)
        self.assertNotIn({'skill_id':101},result['projected']['skill_array'])

    def test_inheritance_s_probability_combines_two_rolls(self):
        parent=self.store.entities('veterans')[0]
        report=inheritance_profile(self.master,self.trainee,[parent])
        self.assertAlmostEqual(report['probabilities']['proper_distance_mile']['S'],1-.95**2)
        self.assertEqual(report['initial_stats']['speed'],21)

    def test_race_comparison_seeded_and_finish_order_is_consistent(self):
        runner={**self.store.entities('veterans')[0],'skill_array':[]}
        better={**runner,'speed':1200,'stamina':1200,'power':1200,'wiz':1200}
        a=simulate_field(self.master,[runner,better],{'distance':1600},runs=8)
        b=simulate_field(self.master,[runner,better],{'distance':1600},runs=8)
        self.assertEqual(a,b)
        self.assertLess(a['runners'][1]['mean_time'],a['runners'][0]['mean_time'])
        self.assertAlmostEqual(sum(row['win_rate'] for row in a['runners']),1.)

    def test_skills_respect_course_conditions_and_unknowns_stay_unranked(self):
        runner={**self.store.entities('veterans')[0],'skill_array':[]}
        equipped={**runner,'skill_array':[{'skill_id':102}]}
        self.assertLess(quick_evaluation(self.master,equipped,{'rotation':1})['time'],quick_evaluation(self.master,runner,{'rotation':1})['time'])
        self.assertEqual(quick_evaluation(self.master,equipped,{'rotation':2})['time'],quick_evaluation(self.master,runner,{'rotation':2})['time'])
        self.master._planning_catalog.skills[101]['condition_1']='unrecognised_condition==1'
        result=skill_profile(self.master,101,{},runner=runner)
        self.assertFalse(result['modelled']);self.assertIsNone(result['seconds_saved'])

    def test_assignment_matches_exhaustive_oracle_with_character_conflicts(self):
        candidates=[{'character_id':c,'division':d,'style':style,'value':(c*7+d*3+style)%13}
            for c in range(1,5) for d in (1,2) for style in (1,2)]
        result=assign_team(candidates,slots=1,divisions=(1,2),distinct_styles=False)
        oracle=max(a['value']+b['value'] for a,b in itertools.product(candidates,candidates)
            if a['division']==1 and b['division']==2 and a['character_id']!=b['character_id'])
        self.assertEqual(result['value'],oracle)
        self.assertEqual(len({r['character_id'] for r in result['selected']}),2)

    def test_concert_never_spends_unavailable_or_unaffordable_offers(self):
        result=plan_concert(self.master,[1],[0,50,0,0,0],wanted=[1])
        self.assertFalse(result['purchases']);self.assertEqual(result['reserves'][0]['missing'][0],10)
        result=plan_concert(self.master,[1,2],[10,5,0,0,0],wanted=[1])
        self.assertEqual({r['id'] for r in result['purchases']},{1,2})
        self.assertTrue(all(x>=0 for x in result['remaining']))
        result=plan_concert(self.master,[1],[10,5,0,0,0],bought=[1])
        self.assertFalse(result['purchases'])

    def test_verified_rewards_and_currency_advice(self):
        routes=reward_routes(self.master,[59])
        self.assertEqual(routes[0]['items'][59],50.)
        self.assertEqual(reward_routes(self.master,[59],finish=2),[])
        result=spending_advice(self.store,self.master,{'skill_ids':[102]},balances={59:100},minutes_per_run=5)
        upgrade=next(r for r in result['upgrades'] if r['card_id']==100101 and r['to_level']==2)
        self.assertEqual(upgrade['estimated_runs'],2);self.assertEqual(upgrade['minutes'],10)

    def test_reference_profiles_explain_owned_sources_and_costs(self):
        p=skill_profile(self.master,101,self.req,store=self.store)
        self.assertTrue(p['sources']);self.assertEqual(p['cost'],100)
        report=compare_supports(self.store,self.master,self.trainee,self.req)
        self.assertTrue(report['available']);self.assertEqual(len(report['rows']),7)

    def test_project_dag_reuses_existing_parents_and_tracks_new_runner(self):
        result=generate_project(self.store,self.master,self.req,depth=2)
        goals=[g for g in self.store.goals() if g['details'].get('project_id')==result['id']]
        by_id={g['id']:g for g in goals}
        for goal in goals:self.assertTrue(all(dep<goal['id'] for dep in goal['details'].get('prerequisites',[])))
        runner=next(g for g in goals if g['details']['project_stage']=='runner')
        self.assertEqual(len(runner['details']['parent_ids']),2)
        self.assertTrue(all(by_id[i]['status']=='Complete' for i in runner['details']['prerequisites']))
        self.assertEqual(project_status(self.store,self.master)['next']['id'],runner['id'])
        veteran={**self.store.entities('veterans')[0],'trained_chara_id':99,'card_id':100101}
        self.store.import_bytes('trained_chara_data.json',json.dumps([*self.store.entities('veterans'),veteran]).encode())
        sync_projects(self.store,self.master)
        runner=next(g for g in self.store.goals() if g['id']==runner['id'])
        self.assertEqual(runner['status'],'Complete');self.assertEqual(runner['details']['matched_veteran_id'],99)

    def test_forecasts_become_stale_after_plan_or_game_data_changes(self):
        identity=self.store.save_goal('Runner',self.req)
        goal=self.store.goals()[0]
        result=forecast_plan(self.store,self.master,goal,overrides={'runs':4})
        retain_forecast(self.store,result);self.assertEqual(len(forecast_runners(self.store,self.master)),1)
        self.store.update_goal(identity,'Runner',{**self.req,'skill_ids':[101]})
        self.assertEqual(forecast_runners(self.store,self.master),[])
        with self.assertRaisesRegex(ValueError,'changed'):retain_forecast(self.store,result)

    def test_backtest_requires_the_same_career_and_minimum_separation(self):
        self.assertEqual(validate_careers(self.store,self.master,self.req)['count'],0)

    def test_project_conversion_preserves_root_and_is_idempotent(self):
        identity=self.store.save_goal('My runner',self.req)
        first=generate_project(self.store,self.master,self.req,root_goal_id=identity)
        before=len(self.store.goals())
        current=next(r for r in self.store.goals() if r['id']==identity)
        second=generate_project(self.store,self.master,current['details'],root_goal_id=identity)
        self.assertEqual(first['id'],second['id']);self.assertEqual(len(self.store.goals()),before)
        self.assertEqual(current['title'],'My runner')

    def test_collection_update_invalidates_a_retained_forecast(self):
        self.store.save_goal('Runner',self.req)
        result=forecast_plan(self.store,self.master,self.store.goals()[0],overrides={'runs':4})
        retain_forecast(self.store,result)
        supports=self.store.entities('supports');supports[0]['level']=30
        self.store.import_bytes('support_card_data.json',json.dumps(supports).encode())
        self.assertEqual(forecast_runners(self.store,self.master),[])
