"""Generate and maintain collection-aware grandparent → parent → runner projects."""
from collections import Counter
from uuid import uuid4
import json

from uma_workbench.core import canonical, utc_now
from uma_workbench.collection import collection_facets
from uma_workbench.planning import APTITUDES, catalog_for, find_setups, matching_veterans, requirements_aptitudes
from uma_workbench.roster_viewer import owned_veterans


def describe_spark_targets(master,targets):
    labels={f"{ {1:'Blue',2:'Pink',3:'Green',4:'Skill',5:'Race',6:'Scenario'}.get(row.get('factor_type'),'Other')}:{row.get('factor_group_id')}":
        master.names.get((147,identity),'Spark name unavailable') for identity,row in master.factors.items()}
    return ' · '.join(('Any blue stat spark' if key=='color:Blue' else labels.get(key,'Inheritance spark'))+' '+'★'*int(stars) for key,stars in targets.items()) or 'Plan skills / stats'


def result_matches(store,master,requirements):
    rows=matching_veterans(store,master,requirements)
    answer=[]
    for row in rows:
        facets=collection_facets(master,'veterans',row)
        wanted=requirements.get('required_sparks',{})
        sparks=facets['sparks']
        if all(sparks.get(key,0)>=stars for key,stars in wanted.items()):answer.append(row)
    return sorted(answer,key=lambda r:-int(r.get('rank_score',0)))


def generate_project(store,master,requirements,*,name='',depth=2,root_goal_id=None,checkpoint=None,progress=None,logger=None):
    checkpoint=checkpoint or (lambda:None)
    if root_goal_id is not None:
        root=next((row for row in store.goals(include_removed=False) if row['id']==root_goal_id),None)
        if not root:raise ValueError('The selected plan no longer exists')
        if root['details'].get('project_id'):
            project=store.setting('project:'+root['details']['project_id'],{})
            return {**project,'stages':len(project.get('goal_ids',[])),'existing':True}
    if depth not in (1,2):raise ValueError('Choose one or two generations of parent preparation')
    report=find_setups(store,master,{**requirements,'career_forecast':False},limit=1,checkpoint=checkpoint)
    if not report['setups']:raise ValueError('Import owned trainees and supports, or clear fixed choices, before creating a training project')
    chosen=report['setups'][0]
    project_id=str(uuid4())
    name=name.strip() or 'Build '+master.card_name(chosen['card_id'])
    trainees=store.entities('trainees')
    by_character={}
    for row in trainees:by_character.setdefault(master.character_id(row['card_id']),[]).append(row)
    target_character=master.character_id(chosen['card_id'])
    pool=[row for row in trainees if master.character_id(row['card_id'])!=target_character]
    if len({master.character_id(row['card_id']) for row in pool})<2:
        raise ValueError('A lineage project needs two other owned parent characters')
    catalog=catalog_for(master)
    targets=requirements_aptitudes(requirements)
    groups={column:group for column,_label,group in APTITUDES}
    base_aptitudes={row['column']:row.get('base') or 0 for row in chosen['aptitudes']}
    red=[f'Pink:{groups[key]}' for key,target in targets.items()
        if target==8 or base_aptitudes.get(key,0)<min(7,target)]
    selected_parents=chosen['parents'][:2]
    parent_cards=[]
    used={target_character}
    for index in range(2):
        preferred=selected_parents[index]['card_id'] if index<len(selected_parents) else None
        candidates=[row for row in pool if master.character_id(row['card_id']) not in used]
        candidates.sort(key=lambda row:(row['card_id']!=preferred,-len(catalog.base_skills(master,row)&set(requirements.get('skill_ids',[]))),row['card_id']))
        row=candidates[0];parent_cards.append(row);used.add(master.character_id(row['card_id']))
    specs=[]
    baseline=[int(r['trained_chara_id']) for r in owned_veterans(store)]
    for branch,parent in enumerate(parent_cards):
        prerequisites=[]
        parent_character=master.character_id(parent['card_id'])
        if depth==2:
            gps=[row for row in trainees if master.character_id(row['card_id']) not in (target_character,parent_character)]
            gp_chars=set()
            for side in range(2):
                choices=[row for row in gps if master.character_id(row['card_id']) not in gp_chars]
                if not choices:break
                gp=min(choices,key=lambda row:(row['card_id']==parent['card_id'],row['card_id']))
                gp_chars.add(master.character_id(gp['card_id']))
                identity=f'gp-{branch}-{side}'
                gp_req={**requirements,'card_id':gp['card_id'],'role':'Grandparent','stats':{},'skill_ids':[],
                    'surface':'Any surface','distance_type':'Any distance','distance':None,'style':'Any style','aptitudes':{},
                    'parent_ids':[],'deck_ids':[],'borrowed_support_id':None,'prerequisites':[],
                    'required_sparks':{(red[(branch+side)%len(red)] if red else 'color:Blue'):3},
                    'project_id':project_id,'auto_track':True,'baseline_veterans':baseline,
                    'stop_condition':'Keep a veteran with the requested inheritance spark; reuse it as a parent seed',
                    'project_stage':identity,'source_stages':[]}
                matches=result_matches(store,master,gp_req)
                specs.append({'key':identity,'title':master.card_name(gp['card_id'])+' · grandparent seed',
                    'details':gp_req,'matches':matches,'dependencies':[]})
                prerequisites.append(identity)
        key=f'parent-{branch}'
        parent_req={**requirements,'card_id':parent['card_id'],'role':'Parent','stats':{},'skill_ids':[],
            'surface':'Any surface','distance_type':'Any distance','distance':None,'style':'Any style','aptitudes':{},
            'parent_ids':[],'deck_ids':[],'borrowed_support_id':None,'prerequisites':[],
            'required_sparks':{(red[branch%len(red)] if red else 'color:Blue'):3},
            'project_id':project_id,'auto_track':True,'baseline_veterans':baseline,
            'stop_condition':'Keep a reusable parent carrying the requested spark and review its lineage',
            'project_stage':key,'source_stages':prerequisites}
        matches=result_matches(store,master,parent_req)
        if matches:
            specs=[row for row in specs if row['key'] not in prerequisites]
            prerequisites=[]
            parent_req['source_stages']=[]
        specs.append({'key':key,'title':master.card_name(parent['card_id'])+' · reusable parent',
            'details':parent_req,'matches':matches,'dependencies':prerequisites})
    final_req={**requirements,'card_id':chosen['card_id'],'parent_ids':[],'prerequisites':[],
        'deck_ids':[r['support_card_id'] for r in chosen['supports']],
        'borrowed_support_id':next((r['support_card_id'] for r in chosen['supports'] if r.get('borrowed')),None),
        'project_id':project_id,'project_stage':'runner','source_stages':['parent-0','parent-1'],
        'auto_track':True,'baseline_veterans':baseline}
    specs.append({'key':'runner','title':master.card_name(chosen['card_id'])+' · final runner',
        'details':final_req,'matches':result_matches(store,master,final_req),'dependencies':['parent-0','parent-1']})
    # Build the complete DAG in one transaction, with only backwards edges.
    ids={}
    with store.connection() as con:
        if root_goal_id is not None:
            current=con.execute('SELECT payload FROM goals WHERE id=?',(root_goal_id,)).fetchone()
            if current is None or json.loads(current[0])!=root['details']:
                raise ValueError('The plan changed while generating its project. Generate it again with the current requirements.')
        for spec in specs:
            checkpoint()
            details={**spec['details'],'prerequisites':[ids[key] for key in spec['dependencies']]}
            if spec['key']=='runner':
                details['prerequisites']=list(dict.fromkeys([*requirements.get('prerequisites',[]),*details['prerequisites']]))
            if spec['matches']:details['matched_veteran_id']=int(spec['matches'][0]['trained_chara_id'])
            if spec['key']=='runner' and root_goal_id is not None:
                con.execute('UPDATE goals SET status=?,payload=? WHERE id=?',
                    ('Complete' if spec['matches'] else 'Planned',canonical(details),root_goal_id))
                ids[spec['key']]=root_goal_id
            else:
                cursor=con.execute('INSERT INTO goals(title,status,payload,created_at) VALUES(?,?,?,?)',
                    (spec['title'],'Complete' if spec['matches'] else 'Planned',canonical(details),utc_now()))
                ids[spec['key']]=cursor.lastrowid
        con.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('project:'+project_id,canonical({'id':project_id,'name':name,'goal_ids':list(ids.values())})))
    sync_projects(store,master)
    return {'id':project_id,'name':name,'goal_ids':list(ids.values()),'stages':len(specs)}


def sync_projects(store,master):
    goals=store.goals(include_removed=False)
    stages={(r['details'].get('project_id'),r['details'].get('project_stage')):r for r in goals if r['details'].get('project_id')}
    updates=[]
    for goal in goals:
        req=goal['details']
        original=canonical(req);original_status=goal['status']
        if not req.get('auto_track') or goal['status']=='Abandoned':continue
        matches=result_matches(store,master,req)
        changed=False
        if matches:
            veteran=int(matches[0]['trained_chara_id'])
            if req.get('matched_veteran_id')!=veteran:req['matched_veteran_id']=veteran;changed=True
            if goal['status']!='Complete':goal['status']='Complete';changed=True
        sources=[stages.get((req.get('project_id'),key)) for key in req.get('source_stages',[])]
        parent_ids=[int(row['details']['matched_veteran_id']) for row in sources if row and row['details'].get('matched_veteran_id')]
        if sources and len(parent_ids)==len(sources) and req.get('parent_ids')!=parent_ids:
            req['parent_ids']=parent_ids;changed=True
        attempted=[r for r in owned_veterans(store) if r.get('card_id')==req.get('card_id')
            and int(r['trained_chara_id']) not in req.get('baseline_veterans',[])]
        if req.get('attempts_recorded')!=len(attempted):req['attempts_recorded']=len(attempted);changed=True
        if changed:updates.append((goal['status'],canonical(req),goal['id'],original,original_status))
    if updates:
        with store.connection() as con:con.executemany('UPDATE goals SET status=?,payload=? WHERE id=? AND payload=? AND status=?',updates)
    return {'updated':len(updates),'goals':len(goals)}


def project_status(store,master):
    sync_projects(store,master)
    goals=store.goals(include_removed=False)
    by_id={g['id']:g for g in store.goals()}
    ready=[];blocked=[];finished=[]
    for row in goals:
        if row['status']=='Complete':finished.append(row);continue
        if row['status']=='Abandoned':continue
        req=row['details']
        exhausted=req.get('attempts_recorded',0)>=req.get('max_attempts',10)
        waiting=[by_id.get(int(i)) for i in req.get('prerequisites',[]) if by_id.get(int(i),{}).get('status')!='Complete']
        row={**row,'waiting':[g['title'] if g else 'Removed prerequisite' for g in waiting],
            'attempt_limit_reached':exhausted}
        (blocked if waiting or exhausted else ready).append(row)
    ready.sort(key=lambda row:(row['status']!='In progress',row['details'].get('role') not in ('Grandparent','Parent'),row['id']))
    return {'ready':ready,'blocked':blocked,'finished':finished,'next':ready[0] if ready else None}
