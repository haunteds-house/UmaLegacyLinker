"""Seeded local race comparisons, skill effects and constrained team selection.

The phase/energy model uses community-observed equations. Field positioning is
an approximation; unknown skill conditions are disclosed instead of assumed true.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import exp, isfinite, log10, sqrt
from random import Random
from statistics import mean, pstdev
import operator

from uma_legacy_linker.skill_catalog import parse_condition
from uma_workbench.planning import catalog_for, distance_group, _skill_incompatible
from uma_workbench.training import STATS

STYLE_SPEED = {1: (1., .98, .962), 2: (.978, .991, .975), 3: (.938, .998, .994), 4: (.931, 1., 1.)}
STYLE_ENERGY = {1: .95, 2: .89, 3: 1., 4: .995}
STYLE_COLUMN = {1: 'nige', 2: 'senko', 3: 'sashi', 4: 'oikomi'}
FIT = (0., .1, .2, .4, .6, .8, .9, 1., 1.05)
OPS = {'==': operator.eq, '!=': operator.ne, '>': operator.gt, '>=': operator.ge, '<': operator.lt, '<=': operator.le}


def quantile(values, fraction):
    values = sorted(values)
    if not values:
        return 0.
    index = (len(values) - 1) * fraction
    low = int(index)
    return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)


def race_profile(requirements=None):
    r = requirements or {}
    group = distance_group(r)
    distance = int(r.get('distance') or {'Sprint': 1200, 'Mile': 1600, 'Medium': 2000, 'Long': 3000}.get(group, 2000))
    style = r.get('running_style', r.get('style', 2))
    style = {'Front Runner': 1, 'Pace Chaser': 2, 'Late Surger': 3, 'End Closer': 4}.get(style, style)
    if not isinstance(style, int) or style not in STYLE_SPEED:
        style = 2
    profile = {**r, 'distance': distance, 'style': style, 'ground_type': 2 if r.get('surface') == 'Dirt' else 1,
        'distance_type': 1 if distance <= 1400 else 2 if distance <= 1800 else 3 if distance <= 2400 else 4,
        'weather': int(r.get('weather', 1)), 'season': int(r.get('season', 1)),
        'ground_condition': int(r.get('ground_condition', 1)), 'rotation': int(r.get('rotation', 1)),
        'track_id': int(r.get('track_id', 0)), 'motivation': int(r.get('motivation', 3))}
    if not 800 <= distance <= 5000 or not 1 <= profile['ground_condition'] <= 4 or not 1 <= profile['motivation'] <= 5:
        raise ValueError('Choose a valid race distance, ground condition and mood')
    return profile


def condition_matches(groups, values):
    if not groups:
        return True
    for group in groups:
        if all(atom.get('parsed') and atom.get('variable') in values
                and OPS[atom['operator']](values[atom['variable']], atom['value']) for atom in group):
            return True
    return False


def static_possible(conditions,profile):
    values={**profile,'running_style':profile['style'],'is_basis_distance':int(profile['distance']%400==0)}
    return all(any(not any(atom.get('parsed') and atom.get('variable') in values and
        not OPS[atom['operator']](values[atom['variable']],atom['value']) for atom in group) for group in groups)
        for groups in conditions)


def passive_bonuses(catalog,record,profile):
    result=Counter()
    for item in record.get('skill_array',[]):
        programs,unknown=skill_program(catalog,item['skill_id'],profile)
        for program in programs:
            if unknown or not static_possible(program['conditions'],profile):continue
            variables={atom.get('variable') for groups in program['conditions'] for group in groups for atom in group}
            if not variables.issubset(set(profile)|{'running_style','is_basis_distance'}):continue
            for kind,value,target in program['effects']:
                if kind in range(1,6) and target==1:result[STATS[kind-1]]+=value/10000
    return result


def skill_program(catalog, identity, profile):
    row = catalog.skills.get(int(identity))
    if not row:
        return [], {'Skill data missing'}
    if _skill_incompatible(row, {**profile, 'surface': 'Dirt' if profile['ground_type'] == 2 else 'Turf',
            'style': {1:'Front Runner',2:'Pace Chaser',3:'Late Surger',4:'End Closer'}[profile['style']]}):
        return [], set()
    programs, unsupported = [], set()
    known = set(profile) | {'running_style','is_basis_distance','phase','phase_random','phase_firsthalf_random',
        'phase_laterhalf_random','distance_rate','distance_rate_after_random','remain_distance','order','order_rate',
        'is_lastspurt','lastspurt','is_badstart','random_lot','random_lot2','hp_per','elapsed_time','always',
        'is_overtake','distance_diff_top','bashin_diff_behind','bashin_diff_infront','near_count'}
    for slot in (1, 2):
        groups = []
        for prefix in ('precondition', 'condition'):
            expression = row.get(f'{prefix}_{slot}', '')
            if expression:
                parsed = parse_condition(expression)
                groups.append(parsed['or_groups'])
                unsupported.update(atom.get('variable', 'Unparsed condition') for group in parsed['or_groups'] for atom in group
                    if not atom.get('parsed') or atom.get('variable') not in known)
        effects = [(int(row.get(f'ability_type_{slot}_{i}', 0)), float(row.get(f'float_ability_value_{slot}_{i}', 0)),
            int(row.get(f'target_type_{slot}_{i}', 1))) for i in (1,2,3) if row.get(f'ability_type_{slot}_{i}')]
        unsupported.update('Effect ' + str(kind) for kind, _, _ in effects if kind not in (1,2,3,4,5,9,21,27,28,31))
        if effects:
            programs.append({'id': int(identity), 'slot': slot, 'conditions': groups, 'effects': effects,
                'duration': max(.5, float(row.get(f'float_ability_time_{slot}', 0)) / 10000 * profile['distance'] / 1000),
                'cooldown': float(row.get(f'float_cooldown_time_{slot}', 0)) / 10000,
                'rarity': row.get('rarity', 1)})
    return programs, unsupported


def _parameters(record, profile,bonuses=None):
    style = int(record.get('running_style', profile['style']))
    if style not in STYLE_SPEED:
        style = profile['style']
    mood = 1 + .02 * (profile['motivation'] - 3)
    stats = {key: max(1., float(record.get(key, 0))) for key in STATS}
    if any(not isfinite(value) or value > 10000 for value in stats.values()):
        raise ValueError('Runner stats must be finite and below 10000')
    stats = {key: (min(value,1200) + max(0,value-1200)/2) * mood for key,value in stats.items()}
    for key,value in (bonuses or {}).items():stats[key]+=value
    column = ('short','mile','middle','long')[profile['distance_type'] - 1]
    aptitude = lambda key: max(1, min(8, int(record.get(key, 7))))
    distance_fit = FIT[aptitude('proper_distance_' + column)]
    surface_fit = FIT[aptitude('proper_ground_' + ('dirt' if profile['ground_type']==2 else 'turf'))]
    style_fit = (0,.1,.2,.4,.6,.75,.85,1.,1.1)[aptitude('proper_running_style_' + STYLE_COLUMN[style])]
    stats['wiz'] *= style_fit
    base = 20 - (profile['distance'] - 2000) / 1000
    speeds = [base * (factor + stats['wiz'] * log10(max(1., stats['wiz']/10)) / 550000 - .00325) for factor in STYLE_SPEED[style]]
    speeds[2] += sqrt(stats['speed']/500) * distance_fit
    spurt = (base * (STYLE_SPEED[style][2] + .01) + sqrt(stats['speed']/500) * distance_fit)*1.05 + sqrt(500*stats['speed'])*distance_fit*.002 + (450*stats['guts'])**.597 * .0001
    return {'stats':stats,'style':style,'base':base,'speeds':speeds,'spurt':spurt,
        'acceleration':.0006*sqrt(500*stats['power'])*surface_fit,
        'hp':profile['distance'] + .8*stats['stamina']*STYLE_ENERGY[style],
        'burn':1+200/sqrt(600*stats['guts'])}


def quick_evaluation(master, record, requirements=None):
    profile = race_profile(requirements)
    profile['style']=int(record.get('running_style',profile['style']))
    catalog = catalog_for(master)
    p = _parameters(record, profile,passive_bonuses(catalog,record,profile))
    speeds = p['speeds'][:2] + [p['spurt']]
    times = [profile['distance']*fraction/max(1,speed) for fraction,speed in zip((1/6,1/2,1/3),speeds)]
    consumption = sum(20*(v-p['base']+12)**2/144*t*(p['burn'] if i==2 else 1)
        for i,(v,t) in enumerate(zip(speeds,times)))
    deficit = max(0, consumption - p['hp']) / max(1,consumption)
    time = sum(times) + 1.2 + deficit*profile['distance']/80
    skill_value, healing, unknown = 0., 0., []
    for skill in record.get('skill_array', []):
        identity = skill.get('skill_id')
        programs, unsupported = skill_program(catalog,identity,profile)
        if unsupported:
            unknown.append(identity)
            continue
        activation = max(.2, min(1., 1 - 90/max(100,p['stats']['wiz'])))
        for program in programs:
            if not static_possible(program['conditions'],profile):continue
            for kind,value,target in program['effects']:
                if target != 1:
                    continue
                magnitude=value/10000
                if kind in (27,31):
                    skill_value += max(0,magnitude)*program['duration']*activation/max(1,p['base'])
                elif kind == 28:
                    skill_value += max(0,magnitude)*activation*.5
                elif kind == 9:
                    healing += max(0,magnitude)*p['hp']*activation
    deficit=max(0,consumption-p['hp']-healing)/max(1,consumption)
    time=sum(times)+1.2+deficit*profile['distance']/80
    time = max(1.,time-skill_value)
    return {'time':time,'index':profile['distance']/time,'stamina_margin':p['hp']-consumption,
        'unknown_skills':unknown,'skill_seconds':skill_value,'profile':profile}


def simulate_field(master, runners, requirements=None, *, runs=64, seed=2026, checkpoint=None, progress=None, logger=None):
    if not 1 <= len(runners) <= 18 or not 1 <= int(runs) <= 512:
        raise ValueError('Use 1–18 runners and 1–512 race samples')
    checkpoint = checkpoint or (lambda: None)
    progress = progress or (lambda *_: None)
    profile = race_profile(requirements)
    catalog = catalog_for(master)
    compiled, unknown = [], set()
    for row in runners:
        local = {**profile,'style':int(row.get('running_style',profile['style']))}
        programs = []
        for skill in row.get('skill_array', []):
            items, unsupported = skill_program(catalog,skill['skill_id'],local)
            if unsupported:
                unknown.add(skill['skill_id'])
            else:
                programs.extend(items)
        compiled.append(programs)
    results = [[] for _ in runners]
    wins, activations, exhausted = Counter(), [Counter() for _ in runners], Counter()
    timeline = []
    for trial in range(int(runs)):
        checkpoint()
        rng = Random(seed + trial)
        states=[]
        for i,record in enumerate(runners):
            local={**profile,'style':int(record.get('running_style',profile['style']))}
            p=_parameters(record,local,passive_bonuses(catalog,record,local))
            states.append({**p,'position':0.,'velocity':3.,'remaining':p['hp'],'finish':None,
                'delay':rng.uniform(0,.15),'variation':rng.uniform(-.003,.003),'used':set(),'active':[],
                'gate':i,'rolls':{s['id']:rng.random() for s in compiled[i]}})
        elapsed, dt = 0., .5
        while elapsed < profile['distance'] / 5 + 30 and any(s['finish'] is None for s in states):
            if int(elapsed*2) % 60 == 0:
                checkpoint()
            order=sorted(range(len(states)),key=lambda i:-states[i]['position'])
            ranks={identity:rank+1 for rank,identity in enumerate(order)}
            positions=[s['position'] for s in states]
            for i,s in enumerate(states):
                if s['finish'] is not None or elapsed < s['delay']:
                    continue
                fraction=s['position']/profile['distance']
                phase=0 if fraction<1/6 else 1 if fraction<2/3 else 2
                previous=s['position']
                values={**profile,'running_style':s['style'],'is_basis_distance':int(profile['distance']%400==0),
                    'phase':phase,'phase_random':phase,'phase_firsthalf_random':phase,'phase_laterhalf_random':phase,
                    'distance_rate':fraction*100,'distance_rate_after_random':fraction*100,'remain_distance':profile['distance']-previous,
                    'order':ranks[i],'order_rate':ranks[i]/len(states)*100,'is_lastspurt':int(phase==2),'lastspurt':int(phase==2),
                    'hp_per':max(0,s['remaining']/s['hp']*100),'elapsed_time':elapsed,'is_badstart':int(s['delay']>.1),
                    'is_overtake':int(ranks[i]>1),'distance_diff_top':max(positions)-previous,
                    'near_count':sum(abs(p-previous)<2.5 for j,p in enumerate(positions) if j!=i),'always':1,
                    'bashin_diff_behind':0,'bashin_diff_infront':0,'random_lot':50,'random_lot2':50}
                for program in compiled[i]:
                    key=program['id'],program['slot']
                    if key in s['used'] or not all(condition_matches(group,values) for group in program['conditions']):
                        continue
                    s['used'].add(key)
                    if s['rolls'][program['id']] > max(.2,1-90/max(100,s['stats']['wiz'])):
                        continue
                    activations[i][program['id']]+=1
                    for kind,value,target in program['effects']:
                        affected=[i] if target==1 else [j for j,r in enumerate(runners) if j!=i and r.get('team',j)!=runners[i].get('team',i)]
                        for j in affected:
                            if kind==9:
                                states[j]['remaining']=min(states[j]['hp'],states[j]['remaining']+states[j]['hp']*value/10000)
                            else:
                                states[j]['active'].append((elapsed+program['duration'],kind,value/10000))
                s['active']=[item for item in s['active'] if item[0]>elapsed]
                speed_bonus=sum(value for _,kind,value in s['active'] if kind in (27,31))
                acceleration=s['acceleration']+sum(value for _,kind,value in s['active'] if kind==28)
                target=(s['spurt'] if phase==2 and s['remaining']>0 else s['speeds'][phase])+speed_bonus+s['base']*s['variation']
                if s['remaining']<=0:
                    target=.85*s['base']+.001*sqrt(s['stats']['guts']*200)
                # A close runner ahead can delay overtaking; power/wit increase
                # the chance to find room. This affects teammates as well.
                ahead=[(positions[j]-previous,j) for j in range(len(states)) if 0<positions[j]-previous<1.8]
                if phase<2 and ahead and rng.random()>min(.95,(s['stats']['power']+s['stats']['wiz'])/2800):
                    target=min(target,states[min(ahead)[1]]['velocity'])
                accel=24+acceleration if s['velocity']<.85*s['base'] else acceleration
                s['velocity']=max(3.,min(target,s['velocity']+max(.01,accel)*dt)) if target>=s['velocity'] else max(target,s['velocity']-.8*dt)
                burn=20*(s['velocity']-s['base']+12)**2/144*(s['burn'] if phase==2 else 1)
                if profile['ground_condition']>=3:
                    burn*=1.02
                s['remaining']-=burn*dt
                s['position']+=s['velocity']*dt
                if s['position']>=profile['distance']:
                    s['finish']=elapsed+dt*(profile['distance']-previous)/max(.01,s['position']-previous)
            if trial==0 and int(elapsed*2)%10==0:
                timeline.append({'time':elapsed,'positions':[round(s['position'],1) for s in states]})
            elapsed+=dt
        winner=min(range(len(states)),key=lambda i:states[i]['finish'] or float('inf'))
        wins[winner]+=1
        for i,s in enumerate(states):
            results[i].append(s['finish'] or elapsed)
            exhausted[i]+=s['remaining']<=0
        progress(int((trial+1)/runs*100),'Comparing race outcomes…')
    return {'model':'race-comparison-1','runs':runs,'seed':seed,'profile':profile,'timeline':timeline,
        'runners':[{'runner':row,'mean_time':mean(results[i]),'p10':quantile(results[i],.1),'p90':quantile(results[i],.9),
            'win_rate':wins[i]/runs,'exhausted_rate':exhausted[i]/runs,
            'skills':{sid:count/runs for sid,count in activations[i].items()}} for i,row in enumerate(runners)],
        'unknown_skills':sorted(unknown),'notes':['Phase/energy comparison with approximate field positioning. Outcomes are conditional on this entered field.',
            'Unsupported skill effects and conditions are excluded; race geometry and blocking remain approximations.']}


def assign_team(candidates, *, slots=3, divisions=(1,2,3,4,5), distinct_styles=True):
    """Exact assignment for supplied candidate values, unique characters globally."""
    graph=defaultdict(list)
    def edge(a,b,capacity,cost,payload=None):
        forward={'to':b,'cap':capacity,'cost':cost,'rev':len(graph[b]),'payload':payload}
        graph[a].append(forward);graph[b].append({'to':a,'cap':0,'cost':-cost,'rev':len(graph[a])-1,'payload':None})
        return forward
    source,sink=('source',),('sink',)
    edges=[]
    for chara in sorted({r['character_id'] for r in candidates}):
        edge(source,('chara',chara),1,0)
    for row in candidates:
        role=('role',row['division'],row['style'] if distinct_styles else 0)
        edges.append(edge(('chara',row['character_id']),role,1,-float(row['value']),row))
    for div in divisions:
        for style in sorted({r['style'] if distinct_styles else 0 for r in candidates if r['division']==div}):
            edge(('role',div,style),('div',div),1 if distinct_styles else slots,0)
        edge(('div',div),sink,slots,0)
    for _ in range(slots*len(divisions)):
        costs,previous={source:0.},{}
        for _ in range(len(graph)-1):
            changed=False
            for a in list(graph):
                if a not in costs:continue
                for i,e in enumerate(graph[a]):
                    value=costs[a]+e['cost']
                    if e['cap'] and value<costs.get(e['to'],float('inf'))-1e-9:
                        costs[e['to']]=value;previous[e['to']]=(a,i);changed=True
            if not changed:break
        if sink not in previous:break
        b=sink
        while b!=source:
            a,i=previous[b];e=graph[a][i];e['cap']-=1;graph[b][e['rev']]['cap']+=1;b=a
    selected=[e['payload'] for e in edges if e['cap']==0]
    return {'selected':sorted(selected,key=lambda r:(r['division'],-r['value'])),
        'vacancies':{d:slots-sum(r['division']==d for r in selected) for d in divisions},'value':sum(r['value'] for r in selected)}


def optimize_collection(store, master, requirements=None, *, trained=(), checkpoint=None, progress=None, logger=None):
    from uma_workbench.roster_viewer import owned_veterans
    checkpoint=checkpoint or (lambda:None)
    profile=requirements or {}
    cm=profile.get('role')=='CM'
    divisions=(profile.get('division',1),) if cm else (1,2,3,4,5)
    pool=[*owned_veterans(store),*trained]
    candidates=[]
    best={}
    for record in pool:
        checkpoint()
        if any(not record.get(stat) for stat in STATS):continue
        for division in divisions:
            req={**profile,'distance':profile.get('distance') if cm else {1:1200,2:1600,3:2000,4:3000,5:1600}[division],
                'surface':profile.get('surface','Turf') if cm else ('Dirt' if division==5 else 'Turf')}
            for style in range(1,5):
                result=quick_evaluation(master,{**record,'running_style':style},{**req,'style':style})
                row={'record':record,'character_id':master.character_id(record['card_id']),'division':division,'style':style,
                    'value':result['index'],'evaluation':result,'projected':bool(record.get('projected'))}
                key=row['character_id'],division,style
                if key not in best or row['value']>best[key]['value']:best[key]=row
    candidates=list(best.values())
    result=assign_team(candidates,divisions=divisions,distinct_styles=not cm)
    selected=result['selected']
    refinements=0
    rivals=profile.get('opponents',[])[:15]
    # Coordinate refinement checks the selected field jointly. It is bounded,
    # with common random seeds so alternatives share the same trial conditions.
    for division in divisions:
        req={**profile,'distance':profile.get('distance') if cm else {1:1200,2:1600,3:2000,4:3000,5:1600}[division],
            'surface':profile.get('surface','Turf') if cm else ('Dirt' if division==5 else 'Turf')}
        def field_value(rows):
            field=[{**r['record'],'running_style':r['style'],'team':0} for r in rows]
            field.extend({**r,'team':i//3+1} for i,r in enumerate(rivals[:18-len(field)]))
            report=simulate_field(master,field,req,runs=4,seed=4103,checkpoint=checkpoint)
            own=report['runners'][:len(rows)]
            return sum(r['win_rate'] for r in own)*10-mean(r['mean_time'] for r in own) if rivals else -mean(r['mean_time'] for r in own)
        field=[r for r in selected if r['division']==division]
        if len(field)!=3:continue
        score=field_value(field)
        for position,current in enumerate(list(field)):
            occupied={r['character_id'] for r in selected if r is not current}
            alternatives=sorted((r for r in candidates if r['division']==division and r['character_id'] not in occupied
                and (cm or r['style']==current['style'])),key=lambda r:-r['value'])[:3]
            best=current
            for candidate in alternatives:
                checkpoint()
                if candidate==current:continue
                value=field_value([candidate if i==position else row for i,row in enumerate(field)])
                refinements+=1
                if value>score+.00001:best=candidate;score=value
            if best is not current:
                selected[selected.index(current)]=best;field[position]=best
    result['value']=sum(r['value'] for r in selected)
    result['joint_comparisons']=refinements
    # Jointly evaluate each selected field, including blocking and teammate
    # skills, rather than treating the solo assignment as a race simulation.
    fields=[]
    for division in divisions:
        selected=[r for r in result['selected'] if r['division']==division]
        if not selected:continue
        req={**profile,'distance':profile.get('distance') if cm else {1:1200,2:1600,3:2000,4:3000,5:1600}[division],
            'surface':profile.get('surface','Turf') if cm else ('Dirt' if division==5 else 'Turf')}
        field=[{**r['record'],'running_style':r['style'],'team':0} for r in selected]
        fields.append({'division':division,'result':simulate_field(master,field,req,runs=16,checkpoint=checkpoint)})
    calibration=point_calibration(store,master)
    for row in selected:
        fit=calibration.get(row['division'])
        row['points']=None if not fit else {'mean':max(0,fit['intercept']+fit['slope']*row['value']),
            'error':fit['error'],'runners':fit['runners']}
    return {**result,'candidates':len(candidates),'fields':fields,'mode':'CM' if cm else 'TT',
        'notes':['Assignment maximizes model race speed with unique characters; Team Trials uses distinct styles.',
            'Joint field results compare your selected runners. Add opponents in Race lab for opponent-dependent win rates.',
            'Point forecasts require a positive fitted relationship across at least three recorded runners in that division. Uncalibrated divisions show race index only.',
            'Assignment is followed by bounded joint-field refinement. This is a recommendation, not a proof of the globally strongest team.']}


def point_calibration(store,master):
    """Fit distinct runner averages, so repeated replays do not inflate sample size."""
    from uma_workbench.roster_viewer import owned_veterans
    veterans={str(r['trained_chara_id']):r for r in owned_veterans(store)}
    groups=defaultdict(list)
    for metric in store.metrics():
        veteran=veterans.get(metric['veteran_id'])
        if not veteran or metric['races']<3:continue
        division=metric['division']
        profile={'distance':{1:1200,2:1600,3:2000,4:3000,5:1600}[division],
            'surface':'Dirt' if division==5 else 'Turf','style':metric['style']}
        value=quick_evaluation(master,{**veteran,'running_style':metric['style']},profile)['index']
        groups[division].append((value,metric['mean']))
    answer={}
    for division,rows in groups.items():
        if len(rows)<3:continue
        x,y=mean(r[0] for r in rows),mean(r[1] for r in rows)
        variance=sum((r[0]-x)**2 for r in rows)
        if variance<1e-8:continue
        slope=sum((a-x)*(b-y) for a,b in rows)/variance
        if slope<=0:continue
        intercept=y-slope*x
        error=sqrt(sum((b-intercept-slope*a)**2 for a,b in rows)/max(1,len(rows)-2))
        answer[division]={'intercept':intercept,'slope':slope,'error':error,'runners':len(rows)}
    return answer
