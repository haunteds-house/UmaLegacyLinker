"""Exercise the packaged planning workflows with synthetic records, offline."""
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt

from ui_qt.image_assets import ImageRepository
from ui_qt.planning_tools import PlanningTools
from uma_workbench.analysis import forecast_plan,forecast_runners
from uma_workbench.projects import generate_project
from uma_workbench.racing import simulate_field
from uma_workbench.smoke_data import make_profile
from uma_workbench.strategy import spending_advice


def run_studio_smoke(application):
    with tempfile.TemporaryDirectory() as temporary:
        store,master=make_profile(temporary)
        req={'scenario':'URA','role':'TT','card_id':100101,'surface':'Turf','distance_type':'Mile','style':'Pace Chaser',
            'skill_ids':[],'stats':{},'max_attempts':10,'stop_condition':'Meet targets','career':{'runs':4,'race_success':1.}}
        identity=store.save_goal('Synthetic runner',req)
        widget=PlanningTools(store,master,ImageRepository(Path(temporary)/'images',enabled=False))
        widget.resize(1080,740);widget.show();application.processEvents()
        try:
            widget.goal.setCurrentIndex(1)
            result=forecast_plan(store,master,store.goals()[0])
            widget._forecast_ready(result);widget.keep_forecast()
            assert len(forecast_runners(store,master))==1,'Forecast did not reach team planning'
            assert widget.forecast_view.timeline.rowCount()==78,'Career timeline incomplete'
            project=generate_project(store,master,req,root_goal_id=identity)
            widget.refresh_projects()
            assert project['stages']>=3,'Lineage project incomplete'
            runners=store.entities('veterans')[:2]
            race=simulate_field(master,runners,{'distance':1600},runs=4)
            widget._race_ready(race)
            assert widget.race_results.rowCount()==2,'Race results missing'
            widget._resources_ready(spending_advice(store,master,{'skill_ids':[102]}))
            assert widget.resource_results.rowCount()>0,'Resource advice missing'
            for control in widget.performance:control.setValue(20)
            for i in range(widget.lessons.count()):widget.lessons.item(i).setCheckState(Qt.CheckState.Checked)
            widget.run_concert();assert widget._concert_report['purchases'],'Concert strategy missing'
            widget.buy_concert();assert store.setting('concert_bought'),'Purchase recording failed'
            for index in range(widget.tabs.count()):
                widget.tabs.setCurrentIndex(index);application.processEvents()
        except Exception as exc:
            print(f'Planning studio smoke check failed: {exc}',flush=True)
            return 1
        finally:
            widget.shutdown();widget.close();application.processEvents()
    print('Planning studio smoke check passed: career, race, project, reference, resources and Concert',flush=True)
    return 0
