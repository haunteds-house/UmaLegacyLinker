"""Readable local skill/card reference and contextual collection comparisons."""
from uma_workbench.game_data import game_data
from uma_workbench.planning import catalog_for, _skill_incompatible
from uma_workbench.racing import quick_evaluation, race_profile, skill_program
from uma_workbench.training import TrainingModel, support_profile, options_for, STATS

EFFECT_NAMES={1:'Speed',2:'Stamina',3:'Power',4:'Guts',5:'Wit',9:'Stamina recovery',21:'Lane movement',
    27:'Target speed',28:'Acceleration',31:'Current speed'}
SUPPORT_EFFECTS={1:'Friendship bonus',2:'Mood effect',3:'Speed bonus',4:'Stamina bonus',5:'Power bonus',6:'Guts bonus',7:'Wit bonus',
    8:'Training effect',9:'Starting Speed',10:'Starting Stamina',11:'Starting Power',12:'Starting Guts',13:'Starting Wit',
    14:'Starting bond',15:'Race bonus',16:'Fan bonus',17:'Hint levels',18:'Hint frequency',19:'Specialty priority',
    27:'Failure reduction',28:'Energy cost reduction',30:'Skill-point bonus',31:'Wit friendship recovery'}


def skill_profile(master,identity,requirements=None,*,store=None,runner=None):
    catalog=catalog_for(master);data=game_data(master)
    row=catalog.skills.get(int(identity),{})
    profile=race_profile(requirements)
    programs,unknown=skill_program(catalog,identity,profile)
    effects=[]
    for slot in (1,2):
        for index in (1,2,3):
            kind=row.get(f'ability_type_{slot}_{index}',0)
            if not kind:continue
            raw=row.get(f'float_ability_value_{slot}_{index}',0)
            unit='%' if kind==9 else ' m/s²' if kind==28 else ' m/s' if kind in (27,31) else ''
            amount=raw/100 if kind==9 else raw/10000
            effects.append(f"{EFFECT_NAMES.get(kind,'Additional effect')}: {amount:+g}{unit}")
    sources=[]
    if store:
        for card in store.entities('trainees'):
            if identity in catalog.base_skills(master,card):sources.append(master.card_name(card['card_id'])+' · available to trainee')
        for card in store.entities('supports'):
            sid=card['support_card_id']
            if identity in catalog.hint_skills(master,sid):sources.append(master.support_name(sid)+' · practice hint')
            if identity in catalog.event_skills(sid):sources.append(master.support_name(sid)+' · possible event reward')
    compatible=not _skill_incompatible(row,requirements or {})
    delta=None
    if runner and not unknown and compatible:
        base={**runner,'skill_array':[r for r in runner.get('skill_array',[]) if r['skill_id']!=identity]}
        after={**base,'skill_array':[*base['skill_array'],{'skill_id':identity}]}
        delta=quick_evaluation(master,base,requirements)['time']-quick_evaluation(master,after,requirements)['time']
    return {'id':int(identity),'name':master.names.get((47,int(identity)),'Skill name unavailable'),
        'description':data.name(48,int(identity),'No description in this game database'),
        'rarity':row.get('rarity'),'cost':catalog.costs.get(int(identity)),'effects':effects,'compatible':compatible,
        'prerequisites':sorted(catalog.lower_skills([identity])-{identity}),'sources':sources,
        'modelled':not bool(unknown),'seconds_saved':delta,'unknown':sorted(unknown),
        'conditions':[row.get(f'condition_{slot}','') for slot in (1,2) if row.get(f'condition_{slot}')],
        'note':'Estimated time value is specific to the entered course and runner. Unknown conditions/effects are not given an invented value.'}


def rank_skills(store,master,requirements,runner,*,limit=150,checkpoint=None,progress=None,logger=None):
    checkpoint=checkpoint or (lambda:None)
    catalog=catalog_for(master)
    available=set(requirements.get('skill_ids',[]))
    for row in store.entities('trainees'):available|=catalog.base_skills(master,row)
    for row in store.entities('supports'):
        available|=catalog.hint_skills(master,row['support_card_id'])|catalog.event_skills(row['support_card_id'])
    profiles=[]
    for identity in sorted(available):
        checkpoint()
        p=skill_profile(master,identity,requirements,store=store,runner=runner)
        price=p['cost']
        p['value_per_100_points']=(p['seconds_saved']*100/price) if price and p['seconds_saved'] is not None else None
        profiles.append(p)
    profiles.sort(key=lambda p:(not p['compatible'],p['value_per_100_points'] is None,-(p['value_per_100_points'] or 0),p['name'].casefold()))
    return profiles[:limit]


def card_profile(store,master,kind,record,requirements=None):
    requirements=requirements or {'scenario':'Unity Cup'}
    catalog=catalog_for(master)
    identity=record['support_card_id'] if kind=='supports' else record['card_id']
    if kind=='supports':
        p=support_profile(master,catalog.training_data,record,options_for(requirements))
        skills=catalog.hint_skills(master,identity)
        events=catalog.event_skills(identity)
        return {'name':master.support_name(identity),'kind':p.kind,'level':p.level,
            'effects':[(SUPPORT_EFFECTS.get(key,'Additional support effect'),value+p.unique.get(key,0)) for key,value in sorted(p.base.items()) if value or p.unique.get(key)],
            'skills':sorted(skills),'events':sorted(events),'notes':p.notes,
            'growth':{},'aptitudes':{}}
    card=master.cards.get(identity,{})
    rarity=catalog.rarity_row(master,record)
    return {'name':master.card_name(identity),'kind':'trainee','level':record.get('talent_level'),
        'effects':[],'skills':sorted(catalog.base_skills(master,record)),'events':[],
        'growth':{stat:card.get('talent_'+('pow' if stat=='power' else stat),0) for stat in STATS},
        'aptitudes':{key:value for key,value in rarity.items() if key.startswith('proper_')},'notes':[]}


def compare_supports(store,master,trainee,requirements=None,*,checkpoint=None,progress=None,logger=None):
    checkpoint=checkpoint or (lambda:None)
    requirements={**(requirements or {}),'training':{**(requirements or {}).get('training',{}),'enabled':True}}
    catalog=catalog_for(master);model=TrainingModel(master,catalog.training_data,requirements)
    if not model.available:return {'available':False,'rows':[]}
    baseline=model.estimate(trainee,[])['subtotal'];rows=[]
    wanted=set(requirements.get('skill_ids',[]))
    for card in store.entities('supports'):
        checkpoint();estimate=model.estimate(trainee,[card]);profile=card_profile(store,master,'supports',card,requirements)
        delta={stat:estimate['subtotal'][stat]-baseline[stat] for stat in STATS}
        coverage=sorted(wanted&(set(profile['skills'])|set(profile['events'])))
        rows.append({'record':card,'profile':profile,'delta':delta,'coverage':coverage,
            'value':sum(delta.values()),'skill_points':estimate['skill_points']})
    rows.sort(key=lambda row:(-len(row['coverage']),-row['value'],-row['skill_points']))
    return {'available':True,'rows':rows,'note':'Single-card marginal contribution under the same practice plan; complete decks can rank differently because of interactions.'}
