"""The actual online Uma.guide tool, with a narrow native planning adapter.

No third-party code is copied or redistributed. The page receives only the
roster when the user clicks Load my roster; it has no native file/API bridge.
"""
import json

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ui_qt.components import muted_label
from uma_workbench.roster_viewer import ROSTER_URL, roster_document, selection_for_plan


def import_script(document):
    # Use the site's public file-input handler, rather than its private Vue state.
    encoded = json.dumps(json.dumps(document, ensure_ascii=False), ensure_ascii=True)
    return """(() => {
      if (location.origin !== 'https://uma.guide' || location.pathname !== '/roster-viewer/') return false;
      const input = document.querySelector('.rv-root input[type="file"]');
      if (!input) return false;
      const transfer = new DataTransfer();
      transfer.items.add(new File([PAYLOAD], 'my-roster.json', {type:'application/json'}));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', {bubbles:true}));
      return true;
    })()""".replace("PAYLOAD", encoded)


SELECTION_SCRIPT = """(() => {
  if (location.origin !== 'https://uma.guide' || location.pathname !== '/roster-viewer/') return '{}';
  const id = el => {
    const match = el?.querySelector('img[src*="chr_icon_"]')?.getAttribute('src')?.match(/chr_icon_\\d+_(\\d+)_/);
    return match ? Number(match[1]) : null;
  };
  return JSON.stringify({target: id(document.querySelector('.rv-pl-card--target')),
    parents: [...document.querySelectorAll('.rv-pl-card--parent')].map(el => ({
      card_id:id(el), borrowed:/borrow/i.test(el.className + ' ' + el.textContent),
      placeholder:/placeholder/i.test(el.className + ' ' + el.textContent)
    }))});
})()"""


class RosterViewer(QWidget):
    plan_requested = Signal(object)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store, self.view, self.page, self.profile = store, None, None, None
        self._pending_import = False
        self._attempts = 0
        root = self.root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.load_button = QPushButton("Load my roster in Uma.guide")
        self.load_button.setObjectName("primary")
        self.load_button.clicked.connect(self.load_roster)
        row.addWidget(self.load_button)
        self.plan_button = QPushButton("Plan this target")
        self.plan_button.clicked.connect(self.plan_target)
        self.plan_button.setEnabled(False)
        row.addWidget(self.plan_button)
        new = QPushButton("New plan")
        new.clicked.connect(lambda: self.plan_requested.emit(None))
        row.addWidget(new)
        row.addStretch()
        root.addLayout(row)
        self.status = muted_label("Uma.guide roster viewer · Online. Load your imported veterans, browse sparks and lineage, then choose a target in Lineage Planner and use Plan this target.")
        root.addWidget(self.status)
        self.placeholder = muted_label("Your roster, with names and pictures. Use Load my roster above to open the actual Uma.guide tool here. My collection is available alongside it for offline browsing.")
        root.addWidget(self.placeholder, 1)
        self.load_timeout = QTimer(self)
        self.load_timeout.setSingleShot(True)
        self.load_timeout.setInterval(30000)
        self.load_timeout.timeout.connect(lambda: self._finish_import(False) if self._pending_import else None)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._try_import)

    def _create_view(self, *, smoke_fixture=False):
        # Lazy loading keeps offline startup quick and lets minimal Qt installs
        # continue using the native collection and planner.
        from ui_qt.components import scope_native_wheel_filter
        scope_native_wheel_filter(QApplication.instance())
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView
        class RosterPage(QWebEnginePage):
            def acceptNavigationRequest(page, url, navigation_type, main_frame):
                if smoke_fixture and url.scheme() == "data":
                    return True
                if not main_frame:
                    return url.scheme() == "https" and url.host() == "uma.guide"
                return url.scheme() == "https" and url.host() == "uma.guide" and url.path() == "/roster-viewer/"

        self.view = QWebEngineView(self)
        self.profile = QWebEngineProfile(self)  # Off-the-record, no persistent roster/cookies.
        self.page = RosterPage(self.profile, self.view)
        self.view.setPage(self.page)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.page.featurePermissionRequested.connect(lambda origin, feature: self.page.setFeaturePermission(
            origin, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser))
        self.profile.downloadRequested.connect(lambda download: download.cancel())
        self.page.loadFinished.connect(self._loaded)
        self.root.addWidget(self.view, 1)
        self.placeholder.hide()

    def load_roster(self):
        if not self.store.entities("veterans"):
            self.status.setText("Import your collection first, then load your roster here.")
            return
        try:
            if self.view is None:
                self._create_view()
            self._pending_import, self._attempts = True, 0
            self.load_button.setEnabled(False)
            self.plan_button.setEnabled(False)
            self.status.setText("Loading Uma.guide…")
            self.load_timeout.start()
            self.view.load(QUrl(ROSTER_URL))
        except (ImportError, RuntimeError):
            self.status.setText("The embedded viewer could not start. Use My collection for offline browsing, or reinstall the complete Windows package.")
            self.load_button.setEnabled(True)

    def _loaded(self, ok):
        if not self._pending_import:
            return
        if not ok or self.page.url() != QUrl(ROSTER_URL):
            self._finish_import(False)
            return
        self.timer.start()
        self._try_import()

    def _try_import(self):
        self._attempts += 1
        if self._attempts > 80:
            self._finish_import(False)
            return
        self.page.runJavaScript(import_script(roster_document(self.store.entities("veterans"))), self._imported)

    def _imported(self, ok):
        if not self._pending_import or not ok:
            return
        self.timer.stop()
        self.page.runJavaScript("Number(document.querySelector('button[title*=\"umas\"]')?.title.match(/all (\\d+) umas/)?.[1] || 0)", self._verify_import)

    def _verify_import(self, count):
        if count:
            self._finish_import(True)
        else:
            # FileReader and Vue render after the change event. Check once per
            # timer tick without re-importing or resetting the user's planner.
            self.timer.timeout.disconnect()
            self.timer.timeout.connect(self._check_import)
            self.timer.start()

    def _check_import(self):
        self._attempts += 1
        if self._attempts > 80:
            self._finish_import(False)
        else:
            self.page.runJavaScript("Number(document.querySelector('button[title*=\"umas\"]')?.title.match(/all (\\d+) umas/)?.[1] || 0)", self._verify_import)

    def _finish_import(self, ok):
        self.load_timeout.stop()
        self.timer.stop()
        self.timer.timeout.disconnect()
        self.timer.timeout.connect(self._try_import)
        self._pending_import = False
        self.load_button.setEnabled(True)
        self.plan_button.setEnabled(ok)
        self.status.setText("Roster loaded · Browse Legacy or Lineage Planner. Plan this target carries your owned target into a simple career plan. Online tool by Uma.guide."
            if ok else "Uma.guide could not load the roster. Check your connection and try Load my roster again. My collection and career plans still work offline.")

    def plan_target(self):
        if self.page:
            self.page.runJavaScript(SELECTION_SCRIPT, self._selected)

    def _selected(self, data):
        try:
            runner = selection_for_plan(json.loads(data or "{}"), self.store)
        except (ValueError, TypeError):
            self.status.setText("Choose an owned target in Lineage Planner first, or use New plan to compare all your trainees.")
            return
        self.plan_requested.emit(runner)
