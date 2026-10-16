"""Native career, race, project, reference and scenario planning workflows."""
from functools import partial
from html import escape

from PySide6.QtCore import Qt,QThreadPool,Signal,QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,QCheckBox,QComboBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QFormLayout,
    QGridLayout,QHBoxLayout,QHeaderView,QLabel,QLineEdit,QListWidget,QListWidgetItem,
    QProgressBar,QPushButton,QScrollArea,QSpinBox,QSplitter,QTabWidget,QTableWidget,QTableWidgetItem,
    QTextBrowser,QVBoxLayout,QWidget,
)

from ui_qt.collection_widgets import ArtworkLabel,describe_records,STAT_LABELS
from ui_qt.components import muted_label
from ui_qt.workers import FunctionWorker
from ui_qt.avatar import AsyncAvatarProvider
from ui_qt.asset_catalog import skill_icon_url
from uma_workbench.analysis import forecast_plan,retain_forecast,build_team
from uma_workbench.career import DEFAULT_CAREER,validate_careers
from uma_workbench.game_data import game_data
from uma_workbench.planning import GRADE_LABELS,APTITUDES
from uma_workbench.projects import generate_project,project_status
from uma_workbench.racing import simulate_field
from uma_workbench.reference import skill_profile,card_profile,rank_skills,compare_supports
from uma_workbench.roster_viewer import owned_veterans
from uma_workbench.strategy import concert_catalog,plan_concert,spending_advice
from uma_workbench.calculators import PERFORMANCE


def table(headers):
    widget=QTableWidget(0,len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.verticalHeader().hide()
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.setAlternatingRowColors(True)
    return widget


def fill(widget,rows):
    widget.setRowCount(len(rows))
    for index,(cells,payload) in enumerate(rows):
        for column,text in enumerate(cells):
            item=QTableWidgetItem(str(text));item.setData(Qt.ItemDataRole.UserRole,payload)
            widget.setItem(index,column,item)


def selected(widget):
    item=widget.item(widget.currentRow(),0)
    return item.data(Qt.ItemDataRole.UserRole) if item else None


def spin(low,high,value,*,decimals=None):
    widget=QDoubleSpinBox() if decimals is not None else QSpinBox()
    if decimals is not None:widget.setDecimals(decimals)
    widget.setRange(low,high);widget.setValue(value)
    return widget


def prose(title,paragraphs):
    return '<h3>'+escape(title)+'</h3>'+''.join('<p>'+escape(str(text))+'</p>' for text in paragraphs if text)


class ForecastView(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.root=QVBoxLayout(self)
        self.summary=muted_label('Run a forecast to compare final stats and see the turn-by-turn policy.')
        self.root.addWidget(self.summary)
        self.bars={}
        grid=QGridLayout()
        for index,(key,label) in enumerate((*STAT_LABELS,('skill_points','Skill points'))):
            grid.addWidget(QLabel(label),index,0)
            bar=QProgressBar();bar.setRange(0,2000);grid.addWidget(bar,index,1)
            self.bars[key]=bar
        self.root.addLayout(grid)
        self.timeline=table(['Turn','Action','Energy','Speed','Stamina','Power','Guts','Wit'])
        self.root.addWidget(self.timeline,1)
        self.notes=muted_label('')
        self.root.addWidget(self.notes)

    def set_forecast(self,report):
        if not report.get('available'):
            self.summary.setText(report.get('reason','Forecast unavailable'));return
        for key,bar in self.bars.items():
            row=report['distribution'][key]
            bar.setMaximum(max(2000,int(row['p90'])))
            bar.setValue(round(row['mean']))
            bar.setFormat(f"{row['mean']:.0f} · middle 80% {row['p10']:.0f}–{row['p90']:.0f}")
        self.summary.setText(f"{report['options']['runs']} model careers · {report['target_rate']:.0%} met stat/skill/aptitude targets · "
            f"{report['actions'].get('rests',0):.1f} rests and {report['actions'].get('races',0):.1f} races on average. "
            +('Full support deck.' if report['complete_deck'] else 'Support lineup is incomplete.'))
        fill(self.timeline,[([r['turn'],r['action'],r['energy'],*[r['stats'][key] for key,_ in STAT_LABELS]],r) for r in report.get('timeline',[])])
        self.notes.setText('Model ranges depend on Career assumptions. Skill access and inheritance are chances. Result sparks are checked after import; spark-fishing success is not predicted.')


class RaceInputs(QWidget):
    def __init__(self,master,parent=None):
        super().__init__(parent);self.master=master
        grid=QGridLayout(self);grid.setContentsMargins(0,0,0,0)
        self.course=QComboBox();self.course.setAccessibleName('Race course')
        self.distance=spin(800,5000,1600);self.distance.setSuffix(' m')
        self.surface=QComboBox();self.surface.addItems(('Turf','Dirt'))
        self.ground=QComboBox();self.ground.addItems(('Firm','Good','Soft','Heavy'))
        self.weather=QComboBox();self.weather.addItems(('Sunny','Cloudy','Rainy','Snowy'))
        self.season=QComboBox();self.season.addItems(('Spring','Summer','Autumn','Winter'))
        for i,(label,widget) in enumerate((('Course',self.course),('Distance',self.distance),('Surface',self.surface),
                ('Ground',self.ground),('Weather',self.weather),('Season',self.season))):
            grid.addWidget(QLabel(label),(i//3)*2,i%3);grid.addWidget(widget,(i//3)*2+1,i%3)
        self.course.currentIndexChanged.connect(self._course_changed)

    def refresh(self):
        old=self.course.currentData();self.course.blockSignals(True);self.course.clear();self.course.addItem('Custom course',None)
        seen=set()
        data=game_data(self.master)
        for row in sorted(data.programs,key=lambda r:(r.get('distance') or 0,r.get('track') or 0)):
            if not row.get('course_id') or row['course_id'] in seen:continue
            seen.add(row['course_id'])
            self.course.addItem(f"{data.name(35,row.get('track'),'Racecourse')} · {row['distance']} m · {'Dirt' if row['ground']==2 else 'Turf'}",row)
        for i in range(self.course.count()):
            if self.course.itemData(i)==old:self.course.setCurrentIndex(i);break
        self.course.blockSignals(False)

    def _course_changed(self):
        row=self.course.currentData()
        if row:
            self.distance.setValue(row['distance']);self.surface.setCurrentIndex(int(row['ground']==2))

    def payload(self):
        row=self.course.currentData() or {}
        return {'distance':self.distance.value(),'surface':self.surface.currentText(),'ground_condition':self.ground.currentIndex()+1,
            'weather':self.weather.currentIndex()+1,'season':self.season.currentIndex()+1,'track_id':row.get('track',0),'rotation':row.get('rotation',1)}


class PlanningTools(QWidget):
    edit_requested=Signal(object)

    def __init__(self,store,master,images,parent=None):
        super().__init__(parent)
        self.setObjectName('root')
        self.store,self.master,self.images=store,master,images
        self._worker=None;self._alive=True;self._actions=[];self._last_forecast=None
        self.avatars=AsyncAvatarProvider(images,40,self)
        self.avatars.changed.connect(self._runner_portraits)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0)
        line=QHBoxLayout();line.addWidget(QLabel('Career plan'))
        self.goal=QComboBox();self.goal.setAccessibleName('Plan used by planning tools');line.addWidget(self.goal,1)
        new=QPushButton('New plan');new.clicked.connect(lambda:self.edit_requested.emit(None));line.addWidget(new)
        edit=QPushButton('Edit plan');edit.clicked.connect(lambda:self.edit_requested.emit(self.goal.currentData()));line.addWidget(edit)
        root.addLayout(line)
        self.tabs=QTabWidget();root.addWidget(self.tabs,1)
        self._career_page();self._race_page();self._project_page();self._reference_page();self._resource_page();self._concert_page()
        self.status=muted_label('Choose a saved plan for career, project and collection-specific recommendations.')
        root.addWidget(self.status)
        line=QHBoxLayout();self.progress=QProgressBar();self.progress.hide();line.addWidget(self.progress,1)
        self.cancel=QPushButton('Cancel');self.cancel.hide();self.cancel.clicked.connect(self.cancel_work);line.addWidget(self.cancel)
        root.addLayout(line)
        self.goal.currentIndexChanged.connect(self._goal_changed)
        self.refresh()

    def _page(self,title):
        page=QWidget();layout=QVBoxLayout(page);self.tabs.addTab(page,title)
        return layout

    def _button(self,layout,title,action):
        button=QPushButton(title);button.clicked.connect(action);layout.addWidget(button);self._actions.append(button);return button

    def requirements(self):
        goal=self.goal.currentData()
        return dict(goal['details']) if goal else {'scenario':'Unity Cup','role':'TT','surface':'Turf','style':'Pace Chaser'}

    def execute(self,function,callback):
        if self._worker:return
        worker=self._worker=FunctionWorker(function)
        self.progress.setRange(0,100);self.progress.setValue(0);self.progress.show();self.cancel.show()
        self.status.setText('Working…')
        for button in self._actions:button.setEnabled(False)
        worker.signals.result.connect(lambda result:callback(result) if self._alive else None)
        worker.signals.error.connect(lambda message,_trace:self.status.setText(message))
        worker.signals.progress.connect(lambda value,message:(self.progress.setValue(value),self.status.setText(message)))
        worker.signals.cancelled.connect(lambda:self.status.setText('Cancelled. Your saved plans are unchanged.'))
        worker.signals.finished.connect(self._finished)
        QThreadPool.globalInstance().start(worker)

    def _finished(self):
        self._worker=None;self.progress.hide();self.cancel.hide()
        for button in self._actions:button.setEnabled(True)

    def cancel_work(self):
        if self._worker:self._worker.request_cancel()

    def shutdown(self):
        self._alive=False;self.cancel_work()

    def _career_page(self):
        layout=self._page('Career forecast')
        layout.addWidget(muted_label('Forecast the selected plan using your owned supports, one rental and its parent lineages. Open choices are filled from your collection.'))
        line=QHBoxLayout()
        self.runs=spin(4,256,32);line.addWidget(QLabel('Career samples'));line.addWidget(self.runs)
        self._button(line,'Forecast career',self.run_forecast)
        self._button(line,'Check recorded careers',self.run_validation)
        self.save_forecast=self._button(line,'Use in team planning',self.keep_forecast)
        layout.addLayout(line)
        toggle=QPushButton('Career assumptions');toggle.setCheckable(True);layout.addWidget(toggle)
        body=QWidget();form=QFormLayout(body);body.hide();toggle.toggled.connect(body.setVisible)
        self.assumptions={}
        for key,label,low,high in (('rest_below','Rest below energy',0,100),('event_stat','Stat gain per assumed event',0,100),
                ('event_skill_points','Skill points per assumed event',0,300),('race_stat','Stats per scheduled race',0,100),
                ('race_skill_points','Skill points per scheduled race',0,300),('unity_team_bonus','Unity team practice bonus (%)',0,100),
                ('trackblazer_shop_bonus','Trackblazer shop practice bonus (%)',0,100)):
            control=spin(low,high,DEFAULT_CAREER[key]);form.addRow(label,control);self.assumptions[key]=control
        self.event_frequency=spin(0,1,.45,decimals=2);form.addRow('Chance of an event each turn',self.event_frequency)
        for key,label in (('race_success','Chance to pass each required race'),('hint_access','Chance to obtain an available practice hint'),('event_skill_access','Chance to finish a support skill event')):
            control=spin(0,1,DEFAULT_CAREER[key],decimals=2);form.addRow(label,control);self.assumptions[key]=control
        self.extra_races=QLineEdit();self.extra_races.setPlaceholderText('Optional race turns, e.g. 24, 36, 48')
        form.addRow('Additional race turns',self.extra_races)
        layout.addWidget(body)
        self.forecast_view=ForecastView();layout.addWidget(self.forecast_view,1)

    def run_forecast(self):
        goal=self.goal.currentData()
        if not goal:self.status.setText('Create or choose a career plan first. The trainee can remain open.');return
        try:extra=[int(x.strip()) for x in self.extra_races.text().split(',') if x.strip()]
        except ValueError:self.status.setText('Enter race turn numbers separated by commas.');return
        overrides={key:control.value() for key,control in self.assumptions.items()}
        overrides.update(runs=self.runs.value(),event_frequency=self.event_frequency.value(),extra_race_turns=extra)
        self.execute(partial(forecast_plan,self.store,self.master,goal,overrides=overrides),self._forecast_ready)

    def _forecast_ready(self,result):
        self._last_forecast=result;self.forecast_view.set_forecast(result['forecast'])
        self.status.setText('Forecast ready. Use in team planning retains this result for comparing planned runners.')

    def keep_forecast(self):
        if not self._last_forecast:self.status.setText('Run a career forecast first.');return
        try:retain_forecast(self.store,self._last_forecast)
        except ValueError as exc:self.status.setText(str(exc));return
        self.status.setText('Planned runner saved. Race comparisons and team building can now include it.')

    def run_validation(self):
        requirements=self.requirements()
        self.execute(lambda **kwargs:validate_careers(self.store,self.master,requirements,checkpoint=kwargs.get('checkpoint')),
            lambda r:self.status.setText(f"Checked {r['count']} earlier-to-later career pairs. "+
                ('Mean absolute errors: '+', '.join(f"{label} {r['mae'][key]:.0f}" for key,label in STAT_LABELS) if r['count'] else 'More snapshots of the same career, at least 12 turns apart, are needed.')))

    def _race_page(self):
        layout=self._page('Race comparisons')
        self.race_inputs=RaceInputs(self.master);layout.addWidget(self.race_inputs)
        line=QHBoxLayout();self.race_runs=spin(4,256,32);line.addWidget(QLabel('Race samples'));line.addWidget(self.race_runs)
        self.include_plans=QCheckBox('Include forecast runners');self.include_plans.setChecked(True);line.addWidget(self.include_plans)
        line.addStretch();layout.addLayout(line);line=QHBoxLayout()
        self._button(line,'Compare selected',self.run_race)
        self._button(line,'Build TT team',lambda:self.run_team(False))
        self._button(line,'Build CM team',lambda:self.run_team(True));layout.addLayout(line)
        split=QSplitter();layout.addWidget(split,1)
        choices=QWidget();left=QVBoxLayout(choices)
        self.runner_search=QLineEdit();self.runner_search.setPlaceholderText('Find a runner by name');left.addWidget(self.runner_search)
        self.runners=QListWidget();left.addWidget(self.runners,1)
        self.runner_search.textChanged.connect(lambda text:[self.runners.item(i).setHidden(text.casefold() not in self.runners.item(i).text().casefold()) for i in range(self.runners.count())])
        self._button(left,'Add opponent build',self.add_opponent)
        self.opponents=QListWidget();self.opponents.setMaximumHeight(120);left.addWidget(self.opponents)
        self._button(left,'Remove selected opponent',lambda:self.opponents.takeItem(self.opponents.currentRow()))
        split.addWidget(choices)
        self.race_results=table(['Runner','Mean time','Middle 80%','Win rate','Stamina exhausted'])
        split.addWidget(self.race_results);split.setSizes([300,650])
        self.race_note=muted_label('Choose runners to compare; add opponent builds for an entered CM field. Team building uses all eligible owned veterans and retained career forecasts.')
        layout.addWidget(self.race_note)

    @staticmethod
    def _checked(widget):
        return [widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget.count()) if widget.item(i).checkState()==Qt.CheckState.Checked]

    def add_opponent(self):
        dialog=QDialog(self);dialog.setWindowTitle('Opponent build');form=QFormLayout(dialog)
        name=QLineEdit('Custom opponent');form.addRow('Name',name)
        stats={}
        for key,label in STAT_LABELS:
            value=spin(1,3000,1000);form.addRow(label,value);stats[key]=value
        style=QComboBox();style.addItems(('Front Runner','Pace Chaser','Late Surger','End Closer'));form.addRow('Style',style)
        aptitude=QComboBox();aptitude.addItems(('A','S','B','C','D','E','F','G'));form.addRow('Surface, distance and style aptitude',aptitude)
        skill_search=QLineEdit();skill_search.setPlaceholderText('Optional learned skill names');form.addRow(skill_search)
        skills=QListWidget();skills.setMaximumHeight(180)
        from uma_workbench.planning import catalog_for
        for identity in sorted(catalog_for(self.master).skills,key=lambda key:self.master.skill_name(key)):
            item=QListWidgetItem(self.master.skill_name(identity));item.setData(Qt.ItemDataRole.UserRole,identity);item.setCheckState(Qt.CheckState.Unchecked);skills.addItem(item)
        skill_search.textChanged.connect(lambda text:[skills.item(i).setHidden(text.casefold() not in skills.item(i).text().casefold()) for i in range(skills.count())]);form.addRow(skills)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);form.addRow(buttons)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        grade={'A':7,'S':8,'B':6,'C':5,'D':4,'E':3,'F':2,'G':1}[aptitude.currentText()]
        record={'name':name.text().strip() or 'Opponent','card_id':0,**{key:value.value() for key,value in stats.items()},
            **{key:grade for key,_,_ in APTITUDES},'running_style':style.currentIndex()+1,
            'skill_array':[{'skill_id':identity} for identity in self._checked(skills)]}
        item=QListWidgetItem(record['name']+' · '+style.currentText());item.setData(Qt.ItemDataRole.UserRole,record);self.opponents.addItem(item)

    def _rivals(self):
        return [self.opponents.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.opponents.count())]

    def run_race(self):
        own=self._checked(self.runners)
        rivals=self._rivals()
        if not own:self.status.setText('Check at least one runner to compare.');return
        field=[{**row,'team':0} for row in own]+[{**row,'team':i//3+1} for i,row in enumerate(rivals)]
        requirements=self.race_inputs.payload()
        self.execute(partial(simulate_field,self.master,field,requirements,runs=self.race_runs.value()),self._race_ready)

    def _runner_name(self,row):
        return row.get('name') or (row.get('plan_name','')+' · ' if row.get('projected') else '')+self.master.card_name(row['card_id'])

    def _race_ready(self,result):
        self.race_results.setColumnCount(5)
        self.race_results.setHorizontalHeaderLabels(['Runner','Mean time','Middle 80%','Win rate','Stamina exhausted'])
        fill(self.race_results,[([self._runner_name(r['runner']),f"{r['mean_time']:.2f} s",f"{r['p10']:.2f}–{r['p90']:.2f} s",
            f"{r['win_rate']:.0%}",f"{r['exhausted_rate']:.0%}"],r) for r in result['runners']])
        self.race_note.setText(' '.join(result['notes'])+f" {len(result['unknown_skills'])} skills contain conditions or effects outside this model.")
        self.status.setText('Race comparison ready. Win rates describe this entered field.')

    def run_team(self,cm):
        requirements={**self.race_inputs.payload(),'role':'CM' if cm else 'TT'}
        self.execute(partial(build_team,self.store,self.master,requirements,include_plans=self.include_plans.isChecked(),opponents=self._rivals()),self._team_ready)

    def _team_ready(self,result):
        self.race_results.setColumnCount(6)
        self.race_results.setHorizontalHeaderLabels(['Runner','Division','Style','Estimated time','Estimated base points','Source'])
        labels={1:'Sprint',2:'Mile',3:'Medium',4:'Long',5:'Dirt'};styles={1:'Front Runner',2:'Pace Chaser',3:'Late Surger',4:'End Closer'}
        fill(self.race_results,[([self._runner_name(r['record']),labels[r['division']],styles[r['style']],f"{r['evaluation']['time']:.2f} s",
            f"{r['points']['mean']:.0f} ± {r['points']['error']:.0f}" if r['points'] else 'Not calibrated',
            'Planned career' if r['projected'] else 'Owned veteran'],r) for r in result['selected']])
        vacancies=sum(result['vacancies'].values());self.race_note.setText(' '.join(result['notes']))
        self.status.setText(f"{len(result['selected'])} runners selected; {vacancies} unfilled slots."+
            (f" Entered-field team win rate: {result['team_win_rate']:.0%}." if 'team_win_rate' in result else ''))

    def _project_page(self):
        layout=self._page('Training projects');line=QHBoxLayout()
        self._button(line,'Generate lineage project',self.create_project)
        self._button(line,'Update from collection',self.refresh_projects)
        self._button(line,'Open next career',self.open_next);layout.addLayout(line)
        self.next_career=muted_label('Projects turn the chosen goal into reusable grandparent seeds, parents and a final runner. Matching exported results update progress automatically.')
        layout.addWidget(self.next_career)
        self.project_table=table(['Career','Purpose','Status','Keep result with','Prerequisites','Attempts']);layout.addWidget(self.project_table,1)
        self.project_table.cellDoubleClicked.connect(lambda *_:self.edit_requested.emit(selected(self.project_table)))

    def create_project(self):
        goal=self.goal.currentData()
        if not goal:self.status.setText('Choose a career plan to turn into a lineage project.');return
        self.execute(partial(generate_project,self.store,self.master,goal['details'],name=goal['title'],root_goal_id=goal['id']),self._project_created)

    def _project_created(self,result):
        self.refresh();self.status.setText(f"Created {result['stages']} careers in {result['name']}.")

    def refresh_projects(self):
        result=project_status(self.store,self.master)
        self._project_status=result
        rows=[*result['ready'],*result['blocked'],*result['finished']]
        from uma_workbench.projects import describe_spark_targets
        fill(self.project_table,[([r['title'],r['details'].get('role','Career'),r['status'],describe_spark_targets(self.master,r['details'].get('required_sparks',{})),
            ', '.join(r.get('waiting',[])) or 'Ready / complete',r['details'].get('attempts_recorded',0)],r) for r in rows])
        nxt=result['next'];self.next_career.setText('Next useful career: '+nxt['title']+' · '+nxt['details'].get('stop_condition','') if nxt else
            'No ready careers. Complete a prerequisite, review an attempt limit, or create a project.')

    def open_next(self):
        self.refresh_projects()
        if self._project_status['next']:self.edit_requested.emit(self._project_status['next'])

    def _reference_page(self):
        layout=self._page('Skills and cards');line=QHBoxLayout()
        self.reference_kind=QComboBox();self.reference_kind.addItems(('Skills','Support cards','Trainees'));line.addWidget(self.reference_kind)
        self.reference_search=QLineEdit();self.reference_search.setPlaceholderText('Find a skill, character or card');line.addWidget(self.reference_search,1)
        self._button(line,'Rank for this course',self.rank_reference);layout.addLayout(line)
        split=QSplitter();self.references=QListWidget();split.addWidget(self.references)
        right=QWidget();detail=QVBoxLayout(right);self.reference_portrait=QWidget();detail.addWidget(self.reference_portrait)
        self.reference_text=QTextBrowser();self.reference_text.setOpenExternalLinks(False);detail.addWidget(self.reference_text,1);split.addWidget(right);layout.addWidget(split,1)
        split.setSizes([300,650])
        self.reference_kind.currentIndexChanged.connect(self.refresh_reference)
        self.reference_search.textChanged.connect(lambda text:[self.references.item(i).setHidden(text.casefold() not in self.references.item(i).text().casefold()) for i in range(self.references.count())])
        self.references.currentRowChanged.connect(self.show_reference)

    def refresh_reference(self):
        from uma_workbench.planning import catalog_for
        self.references.clear();kind=self.reference_kind.currentIndex()
        if kind==0:
            for identity in sorted(catalog_for(self.master).skills,key=self.master.skill_name):
                item=QListWidgetItem(self.master.skill_name(identity));item.setData(Qt.ItemDataRole.UserRole,('skill',identity));self.references.addItem(item)
        else:
            code='supports' if kind==1 else 'trainees'
            for descriptor in describe_records(self.master,code,self.store.entities(code)):
                item=QListWidgetItem(descriptor['name']+'\n'+descriptor['summary']);item.setData(Qt.ItemDataRole.UserRole,(code,descriptor['record']));self.references.addItem(item)
        if self.references.count():self.references.setCurrentRow(0)

    def show_reference(self,*_):
        item=self.references.currentItem()
        if not item:return
        kind,value=item.data(Qt.ItemDataRole.UserRole)
        header=QWidget();row=QHBoxLayout(header)
        if kind=='skill':
            title=self.master.skill_name(value);url=skill_icon_url(catalog_for_skill(self.master,value))
            if url:row.addWidget(ArtworkLabel(self.images,url,title,size=72,support=True))
        else:
            descriptor=describe_records(self.master,kind,[value])[0];title=descriptor['name']
            row.addWidget(ArtworkLabel(self.images,descriptor['url'],title,size=96,support=kind=='supports'))
        label=QLabel(title);label.setObjectName('sectionTitle');label.setWordWrap(True);row.addWidget(label,1)
        container=self.reference_portrait.parentWidget().layout();container.replaceWidget(self.reference_portrait,header)
        self.reference_portrait.hide();self.reference_portrait.deleteLater();self.reference_portrait=header
        if kind=='skill':
            p=skill_profile(self.master,value,{**self.requirements(),**self.race_inputs.payload()},store=self.store)
            self.reference_text.setHtml(prose(p['name'],[p['description'],*p['effects'],
                'Skill-point cost: '+str(p['cost'] if p['cost'] is not None else 'Unknown'),
                'Prerequisites: '+', '.join(self.master.skill_name(i) for i in p['prerequisites']),
                'Your collection sources: '+('; '.join(p['sources']) or 'No imported source'),
                'Race model: '+('Supported' if p['modelled'] else 'Some conditions/effects are not modelled'),p['note']]))
        else:
            p=card_profile(self.store,self.master,kind,value,self.requirements())
            self.reference_text.setHtml(prose(p['name'],[f"{p['kind']} · level {p['level'] if p['level'] is not None else 'unknown'}",
                *[f'{name}: {amount}' for name,amount in p['effects']],
                *[f'{key.capitalize()} growth: +{value}%' for key,value in p['growth'].items()],
                'Skills: '+', '.join(self.master.skill_name(i) for i in p['skills']),
                'Possible event skills: '+', '.join(self.master.skill_name(i) for i in p['events']),*p['notes']]))

    def rank_reference(self):
        req={**self.requirements(),**self.race_inputs.payload()}
        if self.reference_kind.currentIndex()==0:
            runners=owned_veterans(self.store)
            if not runners:self.status.setText('Import a veteran for runner-specific skill values.');return
            selected_runners=self._checked(self.runners);runner=selected_runners[0] if selected_runners else runners[0]
            self.execute(partial(rank_skills,self.store,self.master,req,runner),self._skills_ranked)
        elif self.reference_kind.currentIndex()==1:
            trainees=self.store.entities('trainees')
            if not trainees:self.status.setText('Import trainees and supports first.');return
            trainee=next((r for r in trainees if r['card_id']==req.get('card_id')),trainees[0])
            self.execute(partial(compare_supports,self.store,self.master,trainee,req),self._supports_ranked)
        else:
            from uma_workbench.planning import find_setups
            self.execute(partial(find_setups,self.store,self.master,{**req,'card_id':None}),self._trainees_ranked)

    def _trainees_ranked(self,result):
        self.references.clear()
        seen=set()
        for row in result['setups']:
            if row['card_id'] in seen:continue
            seen.add(row['card_id'])
            descriptor=describe_records(self.master,'trainees',[row['trainee']])[0]
            detail=f"Aptitude gaps {row['aptitude_gap']} · missing skill sources {len(row['missing_skills'])}"
            if row.get('career',{}).get('available'):detail+=f" · targets {row['career']['target_rate']:.0%}"
            item=QListWidgetItem(descriptor['name']+'\n'+detail);item.setData(Qt.ItemDataRole.UserRole,('trainees',row['trainee']));self.references.addItem(item)
        if self.references.count():self.references.setCurrentRow(0)
        self.status.setText('Owned trainees ranked using collection setups and available career forecasts.')

    def _skills_ranked(self,rows):
        self.references.clear()
        for p in rows:
            value=f"{p['value_per_100_points']:+.3f} s per 100 points" if p['value_per_100_points'] is not None else 'Model value unavailable'
            item=QListWidgetItem(p['name']+'\n'+value);item.setData(Qt.ItemDataRole.UserRole,('skill',p['id']));self.references.addItem(item)
        self.status.setText('Skills ranked for the chosen course and runner. Entries with unknown effects remain unranked.')

    def _supports_ranked(self,result):
        if not result['available']:self.status.setText('Support practice data are unavailable for this scenario.');return
        self.references.clear()
        for row in result['rows']:
            item=QListWidgetItem(row['profile']['name']+f"\nPractice contribution {row['value']:+.0f} · target skills {len(row['coverage'])}")
            item.setData(Qt.ItemDataRole.UserRole,('supports',row['record']));self.references.addItem(item)
        self.status.setText(result['note'])

    def _resource_page(self):
        layout=self._page('Resource advice')
        layout.addWidget(muted_label('Prioritize awakening unlocks for your plan, compare verified race drops and estimate the missing materials and time.'))
        line=QHBoxLayout();self.minutes=spin(1,120,10);line.addWidget(QLabel('Minutes per run'));line.addWidget(self.minutes)
        self._button(line,'Find useful upgrades',self.run_resources);self._button(line,'Edit material balances',self.edit_balances);layout.addLayout(line)
        self.resource_results=table(['Trainee','Awakening','Useful unlocks','Expected runs','Minutes']);layout.addWidget(self.resource_results,1)
        self.resource_detail=QTextBrowser();self.resource_detail.setMaximumHeight(230);layout.addWidget(self.resource_detail)
        self.resource_results.cellClicked.connect(self._resource_selected)

    def run_resources(self):
        req=self.requirements();balances=self.store.setting('planning_balances',{});minutes=self.minutes.value()
        self.execute(lambda **_:spending_advice(self.store,self.master,req,balances=balances,minutes_per_run=minutes),self._resources_ready)

    def _resources_ready(self,result):
        self._resource_report=result
        fill(self.resource_results,[([self.master.card_name(r['card_id']),f"{r['from_level']} → {r['to_level']}",
            ', '.join(self.master.skill_name(s) for s in r['skills']),r['estimated_runs'] if r['estimated_runs'] is not None else 'Route unknown',
            r['minutes'] if r['minutes'] is not None else 'Unknown'],r) for r in result['upgrades']])
        self.status.setText('Upgrade recommendations ready. Select a row for material costs and verified earning routes.')

    def _resource_selected(self,*_):
        row=selected(self.resource_results)
        if row:
            self.resource_detail.setHtml(prose(self.master.card_name(row['card_id']),[
                f"{item['name']}: need {item['needed']}, missing {item['missing']:g}. "+
                (f"{item['route']['name']} yields {item['route']['items'][item['item_id']]:g} per qualifying entry on average." if item['route'] else 'No verified drop route in this database.')
                for item in row['items']]))

    def edit_balances(self):
        if not getattr(self,'_resource_report',None):self.status.setText('Find useful upgrades first to choose relevant materials.');return
        items={r['item_id']:r['name'] for u in self._resource_report['upgrades'] for r in u['items']}
        old=self.store.setting('planning_balances',{})
        dialog=QDialog(self);dialog.setWindowTitle('Material balances');root=QVBoxLayout(dialog)
        scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();form=QFormLayout(body);scroll.setWidget(body);root.addWidget(scroll)
        controls={}
        for identity,name in sorted(items.items(),key=lambda x:x[1]):
            value=spin(0,100000000,int(old.get(str(identity),0)));form.addRow(name,value);controls[identity]=value
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);root.addWidget(buttons)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);dialog.resize(620,600)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.store.set_setting('planning_balances',{identity:value.value() for identity,value in controls.items()});self.run_resources()

    def _concert_page(self):
        layout=self._page('Grand Concert')
        layout.addWidget(muted_label('Mark the offers currently in your shop. The planner compares songs, lessons and recovery while keeping wanted songs in view.'))
        row=QHBoxLayout();self.performance=[]
        for label in PERFORMANCE:
            value=spin(0,9999,0);value.setAccessibleName(label+' performance balance');row.addWidget(QLabel(label));row.addWidget(value);self.performance.append(value)
        layout.addLayout(row)
        row=QHBoxLayout();self.concert_turn=spin(1,78,24);self.concert_energy=spin(0,200,70);self.practices_left=spin(0,78,40)
        for name,control in (('Turn',self.concert_turn),('Energy',self.concert_energy),('Practices left',self.practices_left)):
            row.addWidget(QLabel(name));row.addWidget(control)
        self._button(row,'Plan shop purchases',self.run_concert);layout.addLayout(row)
        split=QSplitter();layout.addWidget(split,1)
        left=QWidget();column=QVBoxLayout(left);self.lesson_search=QLineEdit();self.lesson_search.setPlaceholderText('Find a song or lesson');column.addWidget(self.lesson_search)
        self.lessons=QListWidget();column.addWidget(self.lessons,1);split.addWidget(left)
        right=QWidget();column=QVBoxLayout(right);column.addWidget(QLabel('Wanted songs'))
        self.wanted_songs=QListWidget();column.addWidget(self.wanted_songs,1)
        self.concert_result=QTextBrowser();column.addWidget(self.concert_result,2);split.addWidget(right)
        self.lesson_search.textChanged.connect(lambda text:[self.lessons.item(i).setHidden(text.casefold() not in self.lessons.item(i).text().casefold()) for i in range(self.lessons.count())])
        row=QHBoxLayout();self._button(row,'Record recommended purchases',self.buy_concert);self._button(row,'Include in career forecast',self.use_concert);layout.addLayout(row)

    def run_concert(self):
        offered=self._checked(self.lessons);balances=[v.value() for v in self.performance]
        try:
            self._concert_report=plan_concert(self.master,offered,balances,bought=self.store.setting('concert_bought',[]),
                wanted=self._checked(self.wanted_songs),turn=self.concert_turn.value(),energy=self.concert_energy.value(),practices_left=self.practices_left.value())
        except ValueError as exc:self.status.setText(str(exc));return
        report=self._concert_report
        self._concert_inputs=(tuple(balances),tuple(offered),self.concert_turn.value(),tuple(self._checked(self.wanted_songs)))
        self.concert_result.setHtml(prose('Recommended purchases',[
            *[f"{i+1}. {r['name']} · {r['effect']}" for i,r in enumerate(report['purchases'])],
            'Remaining: '+', '.join(f'{label} {amount:g}' for label,amount in zip(PERFORMANCE,report['remaining'])),
            f"Next concert: turn {report['next_concert']} · song target {report['song_target']}",
            *['Reserve for '+r['lesson']['name']+': '+', '.join(f'{label} {amount:g}' for label,amount in zip(PERFORMANCE,r['missing']) if amount) for r in report['reserves']],
            *report['notes']]))
        self.store.set_setting('concert_strategy',{'balances':balances,'offered':offered,'wanted':self._checked(self.wanted_songs),'turn':self.concert_turn.value()})

    def buy_concert(self):
        if not getattr(self,'_concert_report',None):self.status.setText('Plan purchases first.');return
        current=(tuple(v.value() for v in self.performance),tuple(self._checked(self.lessons)),self.concert_turn.value(),tuple(self._checked(self.wanted_songs)))
        if current!=self._concert_inputs:self.status.setText('The balances or shop offers changed. Plan purchases again before recording them.');return
        report=self._concert_report;bought=set(self.store.setting('concert_bought',[]))|{r['id'] for r in report['purchases']}
        self.store.set_setting('concert_bought',sorted(bought))
        for control,value in zip(self.performance,report['remaining']):control.setValue(int(value))
        saved=self.store.setting('concert_strategy',{})
        self.store.set_setting('concert_strategy',{**saved,'balances':report['remaining'],
            'offered':[identity for identity in saved.get('offered',[]) if identity not in bought]})
        self.status.setText('Purchases recorded locally. Update the offers after the in-game shop changes.')
        self._concert_report=None

    def use_concert(self):
        goal=self.goal.currentData();report=getattr(self,'_concert_report',None)
        if not goal or not report:self.status.setText('Choose a career plan and plan shop purchases first.');return
        req={**goal['details'],'scenario':'Our Grand Concert','career':{**goal['details'].get('career',{}),
            'concert_purchases':[{'id':r['id'],'turn':self.concert_turn.value()} for r in report['purchases']]}}
        self.store.update_goal(goal['id'],goal['title'],req);self.refresh()
        self.status.setText('Concert purchases saved in this career plan as an assumed purchase schedule.')

    def _goal_changed(self):
        goal=self.goal.currentData();req=goal['details'] if goal else {}
        options={**DEFAULT_CAREER,**req.get('career',{})}
        for key,control in self.assumptions.items():control.setValue(options[key])
        self.event_frequency.setValue(options['event_frequency'])
        self.extra_races.setText(', '.join(map(str,options['extra_race_turns'])))
        self._last_forecast=None

    def refresh(self):
        old=self.goal.currentData();identity=old['id'] if old else None
        self.goal.blockSignals(True);self.goal.clear();self.goal.addItem('Choose a plan…',None)
        for goal in self.store.goals(include_removed=False):
            self.goal.addItem(goal['title'],goal)
            if goal['id']==identity:self.goal.setCurrentIndex(self.goal.count()-1)
        self.goal.blockSignals(False)
        self._goal_changed()
        self.race_inputs.refresh();self.runners.clear()
        for descriptor in describe_records(self.master,'veterans',owned_veterans(self.store)):
            record=descriptor['record'];style=max(range(1,5),key=lambda i:record.get('proper_running_style_'+('nige','senko','sashi','oikomi')[i-1],0))
            item=QListWidgetItem(descriptor['name']+'\n'+descriptor['summary']);item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole,{**record,'running_style':style});self.runners.addItem(item)
        self.runners.setIconSize(QSize(40,40));self._runner_portraits()
        self.refresh_reference();self.refresh_projects()
        bought=set(self.store.setting('concert_bought',[]));saved=self.store.setting('concert_strategy',{})
        self.lessons.clear();self.wanted_songs.clear()
        for lesson in concert_catalog(self.master):
            if lesson['id'] not in bought:
                item=QListWidgetItem(lesson['name']+' · '+', '.join(f'{label} {amount}' for label,amount in zip(PERFORMANCE,lesson['costs']) if amount))
                item.setData(Qt.ItemDataRole.UserRole,lesson['id']);item.setCheckState(Qt.CheckState.Checked if lesson['id'] in saved.get('offered',[]) else Qt.CheckState.Unchecked);self.lessons.addItem(item)
            if lesson['song']:
                item=QListWidgetItem(lesson['name']);item.setData(Qt.ItemDataRole.UserRole,lesson['id']);item.setCheckState(Qt.CheckState.Checked if lesson['id'] in saved.get('wanted',[]) else Qt.CheckState.Unchecked);self.wanted_songs.addItem(item)
        for control,value in zip(self.performance,saved.get('balances',[0]*5)):control.setValue(int(value))

    def _runner_portraits(self):
        for i in range(self.runners.count()):
            item=self.runners.item(i);record=item.data(Qt.ItemDataRole.UserRole)
            if record:
                portrait=self.avatars.avatar(record.get('card_id'))
                if portrait is not None:item.setIcon(QIcon(portrait))


def catalog_for_skill(master,identity):
    from uma_workbench.planning import catalog_for
    return catalog_for(master).skills.get(identity,{}).get('icon_id')
