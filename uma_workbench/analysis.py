"""End-to-end operations shared by native planning screens and setup search."""
from uma_workbench.core import fingerprint
from uma_workbench.career import CareerModel
from uma_workbench.planning import find_setups
from uma_workbench.racing import optimize_collection, simulate_field, race_profile


def collection_sha(store):
    return fingerprint({kind:store.setting('snapshot:'+kind) for kind in ('trainees','supports','veterans')})


def forecast_plan(store,master,goal,*,overrides=None,checkpoint=None,progress=None,logger=None):
    req={**goal['details'],'career':{**goal['details'].get('career',{}),**(overrides or {})},'career_forecast':False}
    report=find_setups(store,master,req,limit=1,checkpoint=checkpoint)
    if not report['setups']:raise ValueError('No legal setup matches this plan. Clear fixed choices or import the missing collection.')
    setup=report['setups'][0]
    forecast=CareerModel(store,master,req).forecast(setup['trainee'],setup['supports'],setup['parents'],
        checkpoint=checkpoint,progress=progress)
    if not forecast.get('available'):raise ValueError(forecast.get('reason','Career forecast unavailable'))
    return {'goal_id':goal['id'],'requirements_sha':fingerprint(goal['details']),'collection_sha':collection_sha(store),
        'master_sha256':master.sha256,'setup':setup,'forecast':forecast}


def retain_forecast(store,result):
    # Only retain a result that still belongs to the same plan inputs.
    goal=next((row for row in store.goals() if row['id']==result['goal_id']),None)
    if not goal or fingerprint(goal['details'])!=result['requirements_sha'] or collection_sha(store)!=result['collection_sha']:
        raise ValueError('This plan changed during forecasting. Run the forecast again.')
    prior=store.setting('career_forecasts',{})
    prior[str(goal['id'])]={'goal_id':goal['id'],'requirements_sha':result['requirements_sha'],
        'collection_sha':result['collection_sha'],
        'master_sha256':result['master_sha256'],'forecast':{key:value for key,value in result['forecast'].items() if key not in ('samples','timeline')},
        'setup':{key:result['setup'][key] for key in ('trainee','supports','parents')}}
    store.set_setting('career_forecasts',prior)


def forecast_runners(store,master):
    goals={str(g['id']):g for g in store.goals(include_removed=False)}
    answer=[]
    for key,row in store.setting('career_forecasts',{}).items():
        if key not in goals or row['requirements_sha']!=fingerprint(goals[key]['details']) or row['master_sha256']!=master.sha256 or row.get('collection_sha')!=collection_sha(store):continue
        answer.append({**row['forecast']['projected'],'plan_id':row['goal_id'],'plan_name':goals[key]['title']})
    return answer


def build_team(store,master,requirements=None,*,include_plans=True,opponents=(),checkpoint=None,progress=None,logger=None):
    req={**(requirements or {}),'opponents':list(opponents)}
    result=optimize_collection(store,master,req,trained=forecast_runners(store,master) if include_plans else (),
        checkpoint=checkpoint,progress=progress)
    if result['mode']=='CM' and result['selected']:
        own=[{**r['record'],'running_style':r['style'],'team':0} for r in result['selected']]
        rivals=[{**r,'team':i//3+1} for i,r in enumerate(opponents)]
        if len(own)+len(rivals)<=18:
            result['meeting']=simulate_field(master,[*own,*rivals],req,runs=32,checkpoint=checkpoint,progress=progress)
            result['team_win_rate']=sum(r['win_rate'] for r in result['meeting']['runners'][:len(own)])
    return result
