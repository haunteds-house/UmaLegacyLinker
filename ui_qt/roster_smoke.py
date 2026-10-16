"""Deterministic packaged WebEngine/roster adapter check; no network or user data."""
import json
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl

from ui_qt.roster_viewer import RosterViewer
from uma_workbench.core import Store
from uma_workbench.roster_viewer import ROSTER_URL


def run_roster_smoke(application):
    temporary = tempfile.TemporaryDirectory()
    store = Store(Path(temporary.name) / "profile")
    store.import_bytes("card_data.json", b'[{"card_id":100101}]')
    veterans = [{"trained_chara_id": 10, "card_id": 100201, "speed": 900,
        "factor_info_array": [{"factor_id": 103, "level": 0}]}]
    store.import_bytes("trained_chara_data.json", json.dumps(veterans).encode())
    widget = RosterViewer(store)
    errors = []
    def finish(error=None):
        if error:
            errors.append(error)
        widget.timer.stop()
        widget.load_timeout.stop()
        QTimer.singleShot(0, lambda: application.exit(int(bool(errors))))
    def selected(runner):
        if runner.get("card_id") != 100101 or runner.get("viewer_parent_ids") != [10]:
            finish("The visible target/parent did not round-trip to owned records")
        else:
            widget.page.runJavaScript("document.getElementById('imported').textContent", imported)
    def imported(data):
        if json.loads(data or "null") != {"trained_chara_array": veterans}:
            finish("The public file-input import did not receive the roster")
        else:
            finish()
    def poll():
        if widget.plan_button.isEnabled():
            poll_timer.stop()
            widget.plan_target()
        elif not widget._pending_import:
            poll_timer.stop()
            finish("The embedded viewer did not acknowledge its imported roster")
    widget.plan_requested.connect(selected)
    try:
        widget._create_view(smoke_fixture=True)
        widget._pending_import = True
        # The fixture exercises the public DOM contracts observed on Uma.guide.
        # It does not depend on its uptime or cache any third-party source code.
        html = """<!doctype html><html><body><div class="rv-root">
        <input type="file"><pre id="imported"></pre>
        <div class="rv-pl-card--target"><img src="data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==#chr_icon_1001_100101_01.webp"></div>
        <div class="rv-pl-card--parent"><span class="rv-pl-card-role">Parent 1</span><img src="data:image/gif;base64,R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==#chr_icon_1002_100201_01.webp"></div>
        </div><script>
        document.querySelector('input').addEventListener('change', async function() {
          const data = JSON.parse(await this.files[0].text());
          document.getElementById('imported').textContent = JSON.stringify(data);
          const button = document.createElement('button');
          button.title = 'Copy roster link for all ' + data.trained_chara_array.length + ' umas';
          document.body.appendChild(button);
        });
        </script></body></html>"""
        widget.page.setHtml(html, QUrl(ROSTER_URL))
        poll_timer = QTimer(widget)
        poll_timer.setInterval(100)
        poll_timer.timeout.connect(poll)
        poll_timer.start()
        QTimer.singleShot(15000, widget, lambda: finish("WebEngine smoke check timed out"))
        result = application.exec()
    except (ImportError, RuntimeError) as exc:
        errors.append(str(exc))
        result = 1
    temporary.cleanup()
    if errors:
        print("Roster viewer smoke check failed: " + "; ".join(errors), flush=True)
    else:
        print("Roster viewer smoke check passed: WebEngine, file import, owned target and parent", flush=True)
    return result
