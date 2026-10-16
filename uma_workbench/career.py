"""Turn-based career forecasts and recorded-run checks, with saved assumptions."""
from collections import Counter, defaultdict
from math import isfinite
from random import Random
from statistics import mean
import json
import re

from uma_workbench.game_data import game_data
from uma_workbench.planning import catalog_for, APTITUDES, requirements_aptitudes
from uma_workbench.roster_viewer import immediate_ancestors, lineage_preview
from uma_workbench.racing import quantile, quick_evaluation
from uma_workbench.training import (
    COMMANDS, STATS, OUTPUTS, SCENARIOS, TrainingModel, session_gains,
    placement_probability, options_for,
)

DEFAULT_CAREER = {'runs':32,'seed':2026,'turns':78,'rest_below':45,'max_failure':.08,
    'event_frequency':.45,'event_stat':5,'event_skill_points':10,'event_energy':5,
    'race_stat':5,'race_skill_points':35,'extra_race_turns':[],
    'unity_team_bonus':10,'trackblazer_shop_bonus':10,'concert_purchases':[],
    'hint_access':.8,'event_skill_access':.65,'race_success':.95,'continues':3}


def career_options(requirements):
    result={**DEFAULT_CAREER,**requirements.get('career',{})}
    for key,low,high in (('runs',1,256),('seed',0,2147483647),('turns',1,78),('rest_below',0,100),
            ('event_stat',0,100),('event_skill_points',0,300),('event_energy',-30,50),
            ('race_stat',0,100),('race_skill_points',0,300),('unity_team_bonus',0,100),('trackblazer_shop_bonus',0,100)):
        value=result[key]
        if not isinstance(value,(int,float)) or not isfinite(value) or not low<=value<=high:
            raise ValueError('Check the career assumptions and sample count')
    if any(not 0<=result[key]<=1 for key in ('event_frequency','max_failure','hint_access','event_skill_access','race_success')):
        raise ValueError('Use event and failure probabilities from zero to one')
    if not isinstance(result['continues'],int) or not 0<=result['continues']<=10:
        raise ValueError('Use zero to ten allowed continues')
    turns=result['extra_race_turns']
    if any(not isinstance(turn,int) or not 1<=turn<=78 for turn in turns) or len(set(turns))!=len(turns):
        raise ValueError('Extra race turns must be distinct whole turns from 1 to 78')
    return result


def recorded_events(store,card_id=None,scenario=None):
    """Deduplicate English exported outcome text; never mix practice/race gains."""
    if store is None or card_id is None:return []
    seen=set(); by_turn=defaultdict(Counter)
    with store.connection() as con:
        rows=con.execute("SELECT source,payload FROM artifacts WHERE kind='career'").fetchall()
    labels={'Speed':'speed','Stamina':'stamina','Power':'power','Guts':'guts','Wit':'wiz','Skill Pts':'skill_points','Energy':'energy'}
    for source,payload in rows:
        document=json.loads(payload)
        info=document.get('single_mode_load_common',{}).get('chara_info',{})
        # A detached event log without an explicit trainee/scenario identity
        # cannot calibrate this setup's rewards.
        if info.get('card_id')!=card_id or info.get('scenario_id')!=scenario:continue
        for event in document.get('events',[]):
            for effect in event.get('effects',[]):
                if effect.get('playing_state') not in ('TurnStart','Event','EventResult'):continue
                text=effect.get('text','')
                key=(str(source).split('/career/')[0],effect.get('turn'),effect.get('sequence'),text)
                if key in seen:continue
                seen.add(key)
                gains=Counter()
                for label,stat in labels.items():
                    for sign,number in re.findall(re.escape(label)+r' (?:went|was) (up|down) by (\d+)',text):
                        gains[stat]+=int(number)*(1 if sign=='up' else -1)
                if gains:by_turn[key[:2]].update(gains)
    return [dict(gains) for gains in by_turn.values()]


def inheritance_profile(master, trainee, parents):
    """Guaranteed start and two independent inspiration opportunities per factor."""
    from uma_legacy_linker.parent_optimizer import _aptitude_proc_rate, _pair_inheritance_affinities
    from uma_workbench.roster_viewer import _resolvers
    preview=lineage_preview(master,trainee,parents)
    coefficients={}
    resolvers=_resolvers(master) if parents else None
    if len(parents)==2 and resolvers and all(resolvers):
        races,resolver=resolvers
        def member(row):
            return {'chara_id':master.character_id(row['card_id']),
                'g1_wins':races.resolve_g1_saddles(row.get('win_saddle_id_array'))} if row else None
        branches=[]
        for parent in parents:
            row=member(parent);row['when_used_as_parent']={f'grandparent_{i+1}':member(gp) for i,gp in enumerate(immediate_ancestors(parent))};branches.append(row)
        coefficients=_pair_inheritance_affinities(resolver,master.character_id(trainee['card_id']),*branches,3)['values']
    factors=[]
    initial=Counter()
    skill_misses=defaultdict(lambda:1.)
    catalog=catalog_for(master)
    for parent_index,parent in enumerate(parents):
        for member_index,member in enumerate([parent,*immediate_ancestors(parent)]):
            if not member:continue
            role=f'parent_{parent_index+1}'+(f'_grandparent_{member_index}' if member_index else '')
            affinity=coefficients.get(role,0.)
            for factor in member.get('factor_info_array',[]):
                row=master.factors.get(int(factor.get('factor_id',0)),{})
                stars=int(row.get('rarity',0));kind=row.get('factor_type');group=row.get('factor_group_id')
                if kind==1 and group in (1,2,3,4,5):
                    initial[STATS[group-1]]+={1:5,2:12,3:21}.get(stars,0)
                if kind==2:
                    factors.append({'group':group,'chance':_aptitude_proc_rate(stars,affinity,{})[1]})
                if kind==4:
                    rate=min(1.,{1:.03,2:.06,3:.09}.get(stars,0)*(1+max(0,affinity)/100))
                    for sid,skill in catalog.skills.items():
                        if skill.get('group_id')==group and skill.get('group_rate')==1:skill_misses[sid]*=(1-rate)**2
    aptitudes={key:next(row['initial'] for row in preview['aptitudes'] if row['label']==label)
        for key,label,_ in APTITUDES}
    probabilities={}
    for key,label,group in APTITUDES:
        distribution={aptitudes[key] or 1:1.}
        for factor in factors:
            if factor['group']!=group:continue
            for _ in range(2):
                next_distribution=defaultdict(float)
                for grade,chance in distribution.items():
                    next_distribution[grade]+=chance*(1-factor['chance'])
                    next_distribution[min(8,grade+1)]+=chance*factor['chance']
                distribution=dict(next_distribution)
        probabilities[key]={'A':sum(p for rank,p in distribution.items() if rank>=7),'S':distribution.get(8,0.)}
    return {'initial_stats':dict(initial),'aptitudes':aptitudes,'probabilities':probabilities,
        'factors':factors,'affinity':preview['affinity'],'coefficients':coefficients,
        'possible_skills':preview['skills'],'skill_probabilities':{sid:1-miss for sid,miss in skill_misses.items()}}


class CareerModel:
    def __init__(self,store,master,requirements):
        self.store,self.master,self.requirements=store,master,requirements
        self.options=career_options(requirements)
        self.catalog=catalog_for(master)
        self.data=game_data(master)
        training={**requirements,'training':{**requirements.get('training',{}),'enabled':True}}
        self.training=TrainingModel(master,self.catalog.training_data,training)
        self.events=[]

    def forecast(self,trainee,deck,parents=(),*,snapshot=None,checkpoint=None,progress=None,logger=None):
        checkpoint=checkpoint or (lambda:None);progress=progress or (lambda *_:None)
        if not self.training.available:
            return {'available':False,'reason':'The selected scenario or support-effect tables are missing from this game database.'}
        o=self.options;scenario=self.training.scenario
        self.events=recorded_events(self.store,trainee['card_id'],scenario)
        if len(deck)>6 or sum(bool(r.get('borrowed')) for r in deck)>1 or sum(not r.get('borrowed') for r in deck)>5:
            raise ValueError('Use five owned supports and one borrowed support')
        if len({r['support_card_id'] for r in deck})!=len(deck):raise ValueError('Each support card can fill only one slot')
        characters=[self.master.supports.get(r['support_card_id'],{}).get('chara_id',r['support_card_id']) for r in deck]
        if len(characters)!=len(set(characters)) or self.master.character_id(trainee['card_id']) in characters:
            raise ValueError('Support characters must differ from each other and the trainee')
        profiles=[self.training.profile(row) for row in deck]
        complete=len(deck)==6 and sum(bool(r.get('borrowed')) for r in deck)==1
        rarity=self.catalog.rarity_row(self.master,trainee)
        if not rarity:return {'available':False,'reason':'Starting stats for this owned rarity are missing.'}
        lineage=inheritance_profile(self.master,trainee,list(parents))
        initial=self.training.estimate(trainee,deck)['baseline']
        caps={stat:rarity.get('max_'+('pow' if stat=='power' else stat),1200)+
            self.catalog.training_data.scenarios.get(scenario,{}).get('max_'+('pow' if stat=='power' else stat),0) for stat in STATS}
        card=self.master.cards.get(trainee['card_id'],{})
        growth={stat:card.get('talent_'+('pow' if stat=='power' else stat),0) for stat in STATS}
        targets={key:value for key,value in self.requirements.get('stats',{}).items() if value}
        wanted=set(self.requirements.get('skill_ids',[]))
        access={sid:1. for sid in self.catalog.base_skills(self.master,trainee)}
        for p in profiles:
            for sid in self.catalog.hint_skills(self.master,p.identity):access[sid]=max(access.get(sid,0),o['hint_access'])
            for sid in self.catalog.event_skills(p.identity):access[sid]=max(access.get(sid,0),o['event_skill_access'])
        for sid,chance in lineage['skill_probabilities'].items():access[sid]=max(access.get(sid,0),chance)
        weights={stat:(1/max(100,target)) for stat,target in targets.items()} if targets else dict(zip(STATS,(1.,.6,.8,.35,.8)))
        objectives={int(row['turn']):row for row in self.data.objectives(self.master,trainee['card_id'])}
        if scenario==4:objectives={k:v for k,v in objectives.items() if k==12}
        for turn in o['extra_race_turns']:objectives.setdefault(turn,{'name':'Planned optional race'})
        for turn in (74,76,78):objectives.setdefault(turn,{'name':'Scenario final'})
        snapshot=snapshot or {}
        start_turn=max(0,int(snapshot.get('turn',0)))
        samples=[];all_actions=[];one_timeline=[]
        for trial in range(int(o['runs'])):
            checkpoint();rng=Random(int(o['seed'])+trial)
            stats={s:float(snapshot.get(s,initial[s]+lineage['initial_stats'].get(s,0))) for s in STATS}
            skill_points=float(snapshot.get('skill_point',0));energy=float(snapshot.get('vital',100));max_energy=float(snapshot.get('max_vital',100))
            mood=int(snapshot.get('motivation',5));fans=int(snapshot.get('fans',0))
            bonds=[min(100,p.base.get(14,0)+p.unique.get(14,0)) for p in profiles]
            if snapshot.get('evaluation_info_array'):
                values={r.get('training_partner_id',r.get('target_id')):r.get('evaluation',0) for r in snapshot['evaluation_info_array']}
                bonds=[values.get(i+1,bonds[i]) for i in range(len(profiles))]
            counts=Counter();purchases=[];permanent=Counter();actions=[];continues=int(o['continues']);finished=True
            aptitudes={key:snapshot.get(key,value or 1) for key,value in lineage['aptitudes'].items()}
            for turn in range(start_turn+1,int(o['turns'])+1):
                if turn%6==0:checkpoint()
                before=dict(stats)
                if turn in (30,54):
                    for factor in lineage['factors']:
                        if rng.random()<factor['chance']:
                            column=next((key for key,_,group in APTITUDES if group==factor['group']),None)
                            if column:aptitudes[column]=min(8,aptitudes.get(column,1)+1)
                # Scenario shopping is a saved purchase schedule, not a claim
                # that a particular random offer will appear on that turn.
                if scenario==3:
                    from uma_workbench.strategy import concert_catalog
                    if not purchases:
                        purchases={r['id']:r for r in concert_catalog(self.master)}
                    for purchase in o['concert_purchases']:
                        if int(purchase.get('turn',1))!=turn:continue
                        item=purchases.get(purchase.get('id'))
                        if item:
                            for key,value in item['gains'].items():
                                if key in stats:stats[key]+=value
                                elif key=='skill_points':skill_points+=value
                                elif key=='energy':energy=min(max_energy,energy+value)
                            permanent.update(item['training'])
                if turn in objectives:
                    while rng.random()>o['race_success']:
                        counts['race_failures']+=1
                        if continues<=0:finished=False;break
                        continues-=1
                    if not finished:break
                    bonus=1+sum(p.base.get(15,0)+p.unique.get(15,0) for p in profiles)/100
                    for stat in STATS:stats[stat]+=o['race_stat']*bonus
                    skill_points+=o['race_skill_points']*bonus
                    energy=max(0,energy-15)
                    fans+=5000
                    action='Race · '+objectives[turn].get('name','Scheduled race');counts['races']+=1
                else:
                    boards={command:[] for command in COMMANDS}
                    for i,p in enumerate(profiles):
                        specialty=(1+p.base.get(19,0)/100)*(1+p.unique.get(19,0)/100)
                        weights_placement=[specialty if p.kind==stat else 1 for stat in COMMANDS.values()]+[.5]
                        command=rng.choices([*COMMANDS,None],weights=weights_placement)[0]
                        if command:boards[command].append(i)
                    options=[]
                    for command,ids in boards.items():
                        ids=ids[:5];stat=COMMANDS[command]
                        level=min(5,1+counts[stat]//4)
                        calendar=self.data.turns.get(scenario,{}).get(turn,{})
                        if calendar.get('month') in (7,8) and calendar.get('year',1)>=2:level=5
                        gains=session_gains(self.catalog.training_data,scenario,command,level,[profiles[i] for i in ids],growth,
                            motivation=mood,bonds=[bonds[i] for i in ids],deck_types=Counter(p.kind for p in profiles),
                            total_bond=sum(bonds),energy=energy,max_energy=max_energy,fans=fans,current=stats)
                        # Failure is a policy assumption until actual board
                        # previews are available; no failed practice is hidden.
                        failure=max(0,(55-energy)/55)**2
                        if gains['energy']>=0:failure*=.35
                        failure=min(.99,failure)
                        value=sum(gains[key]*weights.get(key,0)*(max(.1,1-stats[key]/targets[key]) if key in targets else 1) for key in STATS)
                        value+=gains['skill_points']*(.0005 if targets else .25)
                        value+=sum(max(0,80-bonds[i]) for i in ids)*(.0004 if targets else .12)
                        value+=(max(0,gains['energy'])*(.002 if targets else .5))
                        if failure>o['max_failure']:value=-1
                        options.append((value,command,ids,gains,failure))
                    value,command,ids,gains,failure=max(options,key=lambda row:row[0])
                    if value<0 or (energy<o['rest_below'] and gains['energy']<=0):
                        recovery=rng.choices((30,50,70),weights=(.25,.5,.25))[0]
                        energy=min(max_energy,energy+recovery);counts['rests']+=1;action='Rest'
                    elif mood<=2:
                        mood=min(5,mood+1);energy=min(max_energy,energy+20);counts['outings']+=1;action='Outing'
                    else:
                        stat=COMMANDS[command];counts[stat]+=1
                        if rng.random()<failure:
                            stats[stat]=max(0,stats[stat]-5);energy=max(0,energy-10);counts['failures']+=1;action='Failed '+stat+' practice'
                        else:
                            for key in STATS:
                                extra=permanent.get(key,0) if gains[key]>0 else 0
                                scenario_bonus=(o['unity_team_bonus'] if scenario==2 and turn>=24 else
                                    o['trackblazer_shop_bonus'] if scenario==4 and counts['races']>=6 else 0)/100
                                stats[key]+=(gains[key]+extra)*(1+scenario_bonus)
                            skill_points+=gains['skill_points']+permanent.get('skill_points',0)
                            energy=max(0,min(max_energy,energy+gains['energy']))
                            for i in ids:bonds[i]=min(100,bonds[i]+7)
                            action=('Wit' if stat=='wiz' else stat.capitalize())+' practice'
                if rng.random()<o['event_frequency']:
                    event=rng.choice(self.events) if self.events else {rng.choice(STATS):o['event_stat'],
                        'skill_points':o['event_skill_points'],'energy':o['event_energy']}
                    for key,value in event.items():
                        if key in stats:stats[key]+=value
                        elif key=='skill_points':skill_points+=value
                        elif key=='energy':energy=min(max_energy,max(0,energy+value))
                    counts['events']+=1
                stats={key:min(caps[key],max(0,value)) for key,value in stats.items()}
                actions.append({'turn':turn,'action':action,'energy':round(energy),'stats':{k:round(v) for k,v in stats.items()},
                    'gains':{key:round(stats[key]-before[key]) for key in STATS}})
            if trial==0:one_timeline=actions
            all_actions.append(counts)
            counts['completed']=int(finished)
            learned=set()
            budget=skill_points
            for identity in sorted(wanted,key=lambda sid:self.catalog.costs.get(sid,1000000)):
                if rng.random()>access.get(identity,0):continue
                steps=self.catalog.lower_skills([identity])-learned
                if any(sid not in self.catalog.costs for sid in steps):continue
                cost=sum(self.catalog.costs[sid] for sid in steps)
                if cost<=budget:learned|=steps;budget-=cost
            row={**{k:round(v) for k,v in stats.items()},**aptitudes,'skill_points':round(skill_points)}
            row['learned']=sorted(learned);row['completed']=finished
            samples.append(row)
            progress(int((trial+1)/o['runs']*100),'Forecasting careers…')
        distribution={key:{'mean':mean(r[key] for r in samples),'p10':quantile([r[key] for r in samples],.1),
            'p90':quantile([r[key] for r in samples],.9)} for key in OUTPUTS}
        apt_targets=requirements_aptitudes(self.requirements)
        success=mean(r['completed'] and all(r[key]>=target for key,target in targets.items())
            and all(r.get(key,0)>=target for key,target in apt_targets.items()) and wanted.issubset(r['learned']) for r in samples)
        requirements_skills=set(self.requirements.get('skill_ids',[]))
        learned=[{'skill_id':sid} for sid in requirements_skills if mean(sid in r['learned'] for r in samples)>=.5]
        projected={'card_id':trainee['card_id'],**{key:round(distribution[key]['mean']) for key in STATS},
            **{key:Counter(s[key] for s in samples).most_common(1)[0][0] for key,_,_ in APTITUDES},
            'skill_array':learned,'projected':True,'scenario_id':scenario}
        uncertainty=sorted({note for p in profiles for note in p.notes})
        return {'available':True,'model':'career-1','scenario':scenario,'options':o,'complete_deck':complete,
            'distribution':distribution,'samples':samples,'timeline':one_timeline,'projected':projected,
            'target_rate':success,'lineage':lineage,'race':quick_evaluation(self.master,projected,self.requirements),
            'completion_rate':mean(r['completed'] for r in samples),
            'skill_rates':{sid:mean(sid in r['learned'] for r in samples) for sid in wanted},
            'actions':{k:mean(c[k] for c in all_actions) for k in set().union(*(set(c) for c in all_actions))},
            'master_sha256':self.master.sha256,'event_samples':len(self.events),
            'notes':uncertainty+['Forecast ranges describe the entered policy and assumptions, not a guaranteed career.',
                'Race rewards, event frequency and scenario adjustments are editable assumptions. Required races use local routes.',
                'Skill access is sampled and prerequisite costs are paid once. Unknown skill costs remain unavailable.']}


def forecast_setup(store,master,setup,requirements=None,**callbacks):
    return CareerModel(store,master,requirements or setup.get('requirements',{})).forecast(
        setup['trainee'],setup.get('supports',[]),setup.get('parents',[]),**callbacks)


def validate_careers(store,master,requirements,*,limit=8,checkpoint=None):
    """Held-out later snapshots of the SAME career; no name/deck-only matching."""
    checkpoint=checkpoint or (lambda:None)
    with store.connection() as con:
        artifacts=[json.loads(row[0]) for row in con.execute("SELECT payload FROM artifacts WHERE kind='career'")]
    careers=defaultdict(dict)
    for doc in artifacts:
        info=doc.get('single_mode_load_common',{}).get('chara_info',{})
        if info.get('single_mode_chara_id') and info.get('turn'):
            careers[info['single_mode_chara_id']][info['turn']]=info
    checks=[]
    for identity,observations in careers.items():
        checkpoint()
        turns=sorted(observations)
        if len(turns)<2 or turns[-1]-turns[0]<12:continue
        early,last=observations[turns[0]],observations[turns[-1]]
        scenario=next((name for name,value in SCENARIOS.items() if value==early.get('scenario_id')),None)
        if not scenario:continue
        deck=[{**row,'borrowed':i==5} for i,row in enumerate(early.get('support_card_array',[]))]
        req={**requirements,'scenario':scenario,'career':{**requirements.get('career',{}),'runs':8,'turns':turns[-1]}}
        forecast=CareerModel(None,master,req).forecast(early,deck,snapshot=early,checkpoint=checkpoint)
        if not forecast.get('available'):continue
        checks.append({'start_turn':turns[0],'end_turn':turns[-1],'card_id':early['card_id'],
            'errors':{stat:forecast['distribution'][stat]['mean']-last.get(stat,0) for stat in STATS}})
        if len(checks)>=limit:break
    return {'count':len(checks),'checks':checks,'mae':{stat:mean(abs(r['errors'][stat]) for r in checks) if checks else None for stat in STATS},
        'note':'Earlier-to-later snapshots of the same career; actual later decisions can differ from the forecast policy.'}
