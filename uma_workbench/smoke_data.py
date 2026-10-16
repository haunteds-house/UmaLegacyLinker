"""Synthetic records for packaged smoke checks and layout auditing only."""
import json
from pathlib import Path
from uma_workbench.core import MasterData, Store
from uma_workbench.game_data import GameData
from uma_workbench.planning import APTITUDES, PlanningCatalog
from uma_workbench.training import TrainingData, COMMANDS, SUMMER

def training_data():
    data = TrainingData()
    early = {
        101: {"speed": 11, "power": 6, "skill_points": 4, "energy": -21},
        105: {"stamina": 10, "guts": 6, "skill_points": 4, "energy": -19},
        102: {"stamina": 6, "power": 9, "skill_points": 4, "energy": -20},
        103: {"speed": 5, "power": 5, "guts": 8, "skill_points": 4, "energy": -22},
        106: {"speed": 2, "wiz": 10, "skill_points": 5, "energy": 5},
    }
    late = {
        101: {"speed": 15, "power": 8, "skill_points": 4, "energy": -27},
        105: {"stamina": 14, "guts": 8, "skill_points": 4, "energy": -25},
        102: {"stamina": 8, "power": 13, "skill_points": 4, "energy": -26},
        103: {"speed": 6, "power": 5, "guts": 13, "skill_points": 4, "energy": -28},
        106: {"speed": 4, "wiz": 14, "skill_points": 5, "energy": 5},
    }
    for command in COMMANDS:
        data.bases[1, command] = early[command]
        data.bases[1, SUMMER[command]] = late[command]
    data.effects = {1: [{"type": 8, "init": 0}]}
    return data

def make_profile(directory):
    store=Store(Path(directory)/'profile');master=MasterData();catalog=PlanningCatalog()
    master.cards={identity:{'chara_id':identity//100,'default_rarity':3,'talent_group_id':identity,
        'available_skill_set_id':identity,'talent_speed':10} for identity in (100101,100201,100301,100401)}
    master.names={(4,identity):name for identity,name in zip(master.cards,('Special Week','Silence Suzuka','Tokai Teio','Maruzensky'))}
    catalog.training_data=training_data()
    for scenario in (2,3,4):
        catalog.training_data.bases.update({(scenario,command):dict(values) for (s,command),values in list(catalog.training_data.bases.items()) if s==1})
    for identity in master.cards:
        catalog.rarities[identity]={3:{**dict.fromkeys((key for key,_,_ in APTITUDES),7),
            **dict.fromkeys(('speed','stamina','pow','guts','wiz'),100),**dict.fromkeys(('max_speed','max_stamina','max_pow','max_guts','max_wiz'),1200)}}
    master.supports={i:{'chara_id':2000+i,'rarity':3,'effect_table_id':1,'command_id':command}
        for i,command in enumerate((101,101,105,102,103,106,106),1)}
    master.support_limits={3:{'limit_4':50}}
    master.factors={3203:{'factor_type':2,'factor_group_id':32,'rarity':3},103:{'factor_type':1,'factor_group_id':1,'rarity':3}}
    master.names.update({(147,3203):'Mile',(147,103):'Speed',(47,101):'Corner Adept',(47,102):'Right-Handed'})
    catalog.skills={101:{'group_id':1,'group_rate':1,'condition_1':'phase==1','float_ability_time_1':30000,
        'ability_type_1_1':27,'float_ability_value_1_1':2000,'target_type_1_1':1},
        102:{'group_id':2,'group_rate':1,'condition_1':'rotation==1','ability_type_1_1':1,
            'float_ability_value_1_1':400000,'target_type_1_1':1}}
    catalog.costs={101:100,102:100};catalog.available_skills={100101:{101:1}}
    catalog.hint_data_available=True;catalog.support_hints={1:{101}}
    master._planning_catalog=catalog
    for name,rows in (('card_data.json',[{'card_id':i,'rarity':3,'talent_level':1} for i in master.cards]),
            ('support_card_data.json',[{'support_card_id':i,'level':50,'limit_break_count':4} for i in master.supports]),
            ('trained_chara_data.json',[{'trained_chara_id':i,'card_id':card,**dict.fromkeys(('speed','stamina','power','guts','wiz'),700),
                **dict.fromkeys((key for key,_,_ in APTITUDES),7),'factor_info_array':[{'factor_id':3203},{'factor_id':103}],
                'skill_array':[{'skill_id':101}]} for i,card in enumerate((100201,100301,100401),10)])):
        store.import_bytes(name,json.dumps(rows).encode())
    game=GameData()
    game.lessons=[{'id':1,'square_type':4,'master_bonus_id':1,'perf_type_1':1,'perf_value_1':10,
        'square_title_text_id':1,'square_content_text_id':1},
        {'id':2,'square_type':3,'master_bonus_id':2,'perf_type_1':2,'perf_value_1':5,'square_title_text_id':2,'square_content_text_id':2}]
    game.bonuses={1:{'master_bonus_gain_type_1':5,'master_bonus_gain_value_1_1':1,'master_bonus_gain_value_1_2':2},
        2:{'master_bonus_gain_type_1':3,'master_bonus_gain_value_1_1':20}}
    game.texts={(209,1):'Test song',(207,1):'Training Speed +2',(209,2):'Rest lesson',(207,2):'Energy +20',(23,59):'Monies'}
    game.concerts=[{'turn_num':24,'great_success_num':3}]
    game.programs=[{'id':1,'race_instance_id':1,'name':'Example race','reward_set_id':1}]
    game.rewards={1:[{'item_id':59,'item_num':100,'odds':500000,'order_min':1,'order_max':1,'bonus':0}]}
    master._extended_game_data=((str(master.path),master.sha256),game)
    catalog.upgrades=[{'talent_group_id':100101,'talent_level':2,'item_id_1':59,'item_num_1':200}]
    catalog.available_skills[100101][102]=2
    catalog.texts[(23,59)]='Monies'
    return store,master
