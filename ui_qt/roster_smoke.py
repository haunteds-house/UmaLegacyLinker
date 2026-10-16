"""Packaged native roster check using synthetic data and no network."""
import json
import tempfile
from pathlib import Path

from ui_qt.image_assets import ImageRepository
from ui_qt.roster_viewer import RosterViewer, VeteranDetails
from ui_qt.training_goal_dialog import TrainingGoalDialog
from uma_workbench.core import MasterData, Store
from uma_workbench.planning import PlanningCatalog
from uma_workbench.roster_viewer import lineage_preview


def run_roster_smoke(application):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        store = Store(root / "profile")
        store.import_bytes("card_data.json", b'[{"card_id":100101,"rarity":3}]')
        veterans = [{"trained_chara_id": identity, "card_id": 100201, "speed": 900,
            "proper_distance_mile": 7 if identity == 11 else 6,
            "factor_info_array": [{"factor_id": 3203}]} for identity in (10, 11)]
        store.import_bytes("trained_chara_data.json", json.dumps(veterans).encode())
        master = MasterData()
        master.names = {(4, 100101): "Special Week", (4, 100201): "Silence Suzuka", (147, 3203): "Mile"}
        master.factors = {3203: {"factor_type": 2, "factor_group_id": 32, "rarity": 3}}
        master._planning_catalog = PlanningCatalog(rarities={100101: {3: {"proper_distance_mile": 6}}})
        images = ImageRepository(root / "images", enabled=False)
        widget = RosterViewer(store, master, images)
        try:
            widget.show()
            application.processEvents()
            widget.filters.aptitudes["proper_distance_mile"].setCurrentIndex(7)
            if [row["record"]["trained_chara_id"] for row in widget.gallery.records] != [11]:
                raise RuntimeError("Roster aptitude filtering failed")
            widget.target.set_choice(widget.target.records[0])
            widget.parents[0].set_choice(next(row for row in widget.parents[0].records if row["record"]["trained_chara_id"] == 11))
            requests = []
            widget.plan_requested.connect(requests.append)
            widget.plan_button.click()
            if requests != [{"card_id": 100101, "lock_trainee": True, "parent_ids": [11]}]:
                raise RuntimeError("The exact selected veteran copy did not reach the plan")
            goal = TrainingGoalDialog(store, master, images, requests[0])
            if goal.payload()["parent_ids"] != [11]:
                raise RuntimeError("The career editor did not preserve the parent selection")
            preview = lineage_preview(master, widget.target.choice["record"], [veterans[1]])
            if next(row for row in preview["aptitudes"] if row["label"] == "Mile")["initial"] != 7:
                raise RuntimeError("Native starting aptitude preview failed")
            details = VeteranDetails(master, images, widget.gallery.records[0])
            details.show()
            application.processEvents()
            details.close()
            goal.reject()
            widget.clear_lineup()
            if widget.selection() != {"target": None, "parent_ids": [None, None]}:
                raise RuntimeError("Clearing the lineage did not clear the selected copies")
        except Exception as exc:
            print(f"Native roster smoke check failed: {exc}", flush=True)
            return 1
        finally:
            widget.close()
            application.processEvents()
        print("Native roster smoke check passed: local filters, veteran details, lineage and exact parent handoff", flush=True)
        return 0
