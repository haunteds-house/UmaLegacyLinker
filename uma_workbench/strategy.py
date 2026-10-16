"""Native Grand Concert shopping and account resource recommendations."""
from collections import Counter
from math import ceil, isfinite

from uma_workbench.calculators import awakening_costs, PERFORMANCE
from uma_workbench.game_data import game_data, reward_routes
from uma_workbench.planning import catalog_for, _skill_incompatible
from uma_workbench.training import STATS


def concert_catalog(master):
    data=game_data(master)
    answer=[]
    keys=(*STATS,'skill_points')
    for row in data.lessons:
        bonus=data.bonuses.get(row.get('master_bonus_id'),{})
        costs=[0]*5
        for i in range(1,6):
            kind=row.get(f'perf_type_{i}',0)
            if 1<=kind<=5:costs[kind-1]+=row.get(f'perf_value_{i}',0)
        gains,training=Counter(),Counter()
        unknown=[]
        for i in range(1,4):
            kind=bonus.get(f'master_bonus_gain_type_{i}',0)
            a,b,c,d=[bonus.get(f'master_bonus_gain_value_{i}_{j}',0) for j in range(1,5)]
            if kind==1 and 1<=a<=6:gains[keys[a-1]]+=c
            elif kind==3:gains['energy']+=a
            elif kind==5 and 1<=a<=6:training[keys[a-1]]+=b
            elif kind:unknown.append(kind)
        identity=row['id']
        effect=data.name(207,row.get('square_content_text_id'),'Effect unavailable')
        name=data.name(209,row.get('square_title_text_id'),'')
        if not name:name=('Song' if row.get('square_type')==4 else 'Lesson')+' · '+effect
        answer.append({'id':identity,'name':name,'effect':effect,'costs':costs,'gains':dict(gains),
            'training':dict(training),'song':row.get('square_type')==4,'kind':row.get('square_type'),
            'unknown_effects':unknown,'source':'Local game Concert tables'})
    return answer


def plan_concert(master, offered, balances, *, bought=(), wanted=(), turn=1, energy=70,
        practices_left=40, weights=None, beam=128):
    if len(balances)!=5 or any(not isfinite(float(x)) or x<0 for x in balances):
        raise ValueError('Enter five nonnegative performance balances')
    if not 1<=int(turn)<=78 or not 0<=energy<=200:
        raise ValueError('Enter a valid career turn and energy')
    weights={**dict.fromkeys(STATS,1.),'skill_points':.4,**(weights or {})}
    catalog={r['id']:r for r in concert_catalog(master)}
    offered=list(dict.fromkeys(map(int,offered)))
    if len(offered)>24:
        raise ValueError('Choose up to 24 currently available shop offers')
    if any(i not in catalog for i in [*offered,*bought,*wanted]):
        raise ValueError('A selected lesson is missing from the game data')
    bought=set(bought)
    wanted=set(wanted)-bought
    options=[catalog[i] for i in offered if i not in bought]
    next_concert=next((r['turn_num'] for r in sorted(game_data(master).concerts,key=lambda r:r['turn_num']) if r['turn_num']>=turn),78)
    # A finite subset search: no future shop offering is treated as available.
    def value(lesson):
        immediate=sum(weights.get(k,0)*v for k,v in lesson['gains'].items() if k!='energy')
        recovery=min(max(0,100-energy),lesson['gains'].get('energy',0))*.6
        lasting=sum(weights.get(k,0)*v for k,v in lesson['training'].items())*max(0,practices_left)
        priority=80 if lesson['id'] in wanted else 0
        deadline=30 if lesson['song'] and next_concert-turn<=6 else 10 if lesson['song'] else 0
        return immediate+recovery+lasting+priority+deadline
    states=[(0.,tuple(float(x) for x in balances),())]
    for lesson in sorted(options,key=lambda r:(not r['song'],r['id'])):
        added=[]
        for score,left,ids in states:
            if all(left[i]>=lesson['costs'][i] for i in range(5)):
                added.append((score+value(lesson),tuple(left[i]-lesson['costs'][i] for i in range(5)),ids+(lesson['id'],)))
        # Dominance for identical remaining resources; retain distinct reserves.
        unique={}
        for state in [*states,*added]:
            key=state[1]
            if key not in unique or state[0]>unique[key][0]:unique[key]=state
        states=sorted(unique.values(),key=lambda s:(-s[0],-sum(s[1]),s[2]))[:beam]
    score,left,ids=states[0]
    selected=[catalog[i] for i in ids]
    reserves=[]
    for identity in sorted(wanted-set(ids)):
        lesson=catalog[identity]
        reserves.append({'lesson':lesson,'missing':[max(0,lesson['costs'][i]-left[i]) for i in range(5)],
            'available':identity in offered})
    deadline_target=next((r.get('great_success_num',3) for r in game_data(master).concerts if r['turn_num']==next_concert),3)
    return {'purchases':selected,'remaining':list(left),'value':score,'reserves':reserves,
        'next_concert':next_concert,'song_target':deadline_target,
        'songs_selected':sum(row['song'] for row in selected),'search_bounded':len(options)>7,
        'notes':['Only the offers you marked available can be purchased. Costs and decoded effects come from your game data.',
            'Values weight permanent bonuses by practices left; shop refreshes, song availability and unrecognised effects are not guaranteed.']}


def spending_advice(store,master,requirements=None,*,balances=None,minutes_per_run=10):
    requirements=requirements or {}
    balances={int(k):float(v) for k,v in (balances or {}).items()}
    if any(not isfinite(v) or v<0 for v in balances.values()) or minutes_per_run<=0:
        raise ValueError('Enter nonnegative balances and a positive time per run')
    catalog=catalog_for(master)
    wanted=set(requirements.get('skill_ids',[]))
    upgrades=[]
    item_ids=set()
    for trainee in store.entities('trainees'):
        current=int(trainee.get('talent_level',1))
        if current>=5:continue
        current_skills=catalog.base_skills(master,trainee)
        for level in range(current+1,6):
            available=catalog.base_skills(master,{**trainee,'talent_level':level})-current_skills
            relevant={i for i in available if not _skill_incompatible(catalog.skills.get(i,{}),requirements)}
            needed=awakening_costs(master,trainee['card_id'],current,level)
            item_ids.update(row['item_id'] for row in needed['items'])
            wanted_new=sorted(wanted&relevant)
            value=100*len(wanted_new)+10*len(relevant)
            if requirements.get('card_id')==trainee['card_id']:value+=25
            upgrades.append({'card_id':trainee['card_id'],'from_level':current,'to_level':level,
                'skills':sorted(relevant),'wanted_skills':wanted_new,'costs':needed,'benefit':value})
    routes=reward_routes(master,item_ids)
    by_item={identity:sorted([r for r in routes if r['items'].get(identity,0)>0],
        key=lambda r:-r['items'][identity]) for identity in item_ids}
    for upgrade in upgrades:
        requirements_items=[]
        total_runs=0
        unknown=False
        for item in upgrade['costs']['items']:
            identity=item['item_id'];missing=max(0,item['needed']-balances.get(identity,0))
            route=by_item.get(identity,[None])[0] if by_item.get(identity) else None
            runs=ceil(missing/route['items'][identity]) if missing and route else 0 if not missing else None
            unknown|=runs is None
            total_runs+=runs or 0
            requirements_items.append({**item,'balance':balances.get(identity,0),'missing':missing,'runs':runs,
                'route':route})
        upgrade.update({'items':requirements_items,'estimated_runs':None if unknown else total_runs,
            'minutes':None if unknown else total_runs*minutes_per_run,
            'priority':upgrade['benefit']/(1+total_runs) if not unknown else None})
    upgrades.sort(key=lambda r:(-bool(r['wanted_skills']),r['priority'] is None,-(r['priority'] or 0),-r['benefit'],r['card_id'],r['to_level']))
    return {'upgrades':upgrades,'routes':routes,'notes':['Upgrade priorities favour your required skills, then useful unlocks per estimated run.',
        'Drop rates are expected yields conditional on the entered race finish, excluding campaign bonuses. Separate item run totals are a conservative budget; one race can yield multiple items.',
        'No route is invented when the local game database does not expose one. Keep unbudgeted currency reserved.']}
