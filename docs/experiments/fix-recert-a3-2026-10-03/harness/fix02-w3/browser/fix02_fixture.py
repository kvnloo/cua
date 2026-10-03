"""FIX-02 fixture: the FIX-01 journaled fixture plus two page variants (measurement harness only).

Imports ``harness/fix-01/fix01_fixture.py`` and ``harness/r2-07/fixture.py`` unchanged (copied by
path from 4a301d32a and 2d71548b4). The TARGET owns the journal; callers see only ``GET /state``.

Variants added here (both start from the unchanged jev-use form page):
  spa_submit     the form's submit is handled in-page (fetch POST /submit, no navigation), so the
                 form and its Submit button are still there after an effect landed. A caller that
                 re-dispatches Submit after a landed click produces a second journaled submit
                 (received/applied 2): the blind-replay hazard is observable on the target.
  file_rerender  the form plus ``<input type=file aria-label="attachment">``. The page reports, by
                 beacon, every input/change event on the old and the replacement node with its
                 ``files.length``. On /__signal it replaces the input with a fresh clone, and it
                 then polls the OLD (detached) node: if files are ever assigned to it, even
                 without an event, it reports ``old:files<n>``.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for path in (HERE.parent / "fix-01", HERE.parent / "r2-07"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import fix01_fixture as f01  # noqa: E402  (unchanged FIX-01 fixture)

PAGE = f01.PAGE

SPA_SUBMIT = b"""<script>
document.querySelector('form').addEventListener('submit', (event) => {
  event.preventDefault();
  const value = document.querySelector('input[name=value]').value;
  fetch('/submit', {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'value=' + encodeURIComponent(value)})
    .then(() => { document.querySelector('output').textContent = 'status=submitted'; });
});
</script>"""

FILE_INPUT = b'<p><input type="file" id="att" aria-label="attachment"></p>'

FILE_RERENDER = b"""<script>""" + f01.LISTEN + b"""
function watchFile(el, node) {
  for (const kind of ['input', 'change']) {
    el.addEventListener(kind, () => cuaReport(node, kind + el.files.length), true);
  }
}
watchFile(document.getElementById('att'), 'old');
fetch('/__signal').then(() => {
  const old = document.getElementById('att');
  const fresh = old.cloneNode(true);
  watchFile(fresh, 'fresh');
  old.replaceWith(fresh);
  cuaReport('page', 'rerendered');
  let polls = 0;
  const timer = setInterval(() => {
    polls += 1;
    if (old.files && old.files.length > 0) { cuaReport('old', 'files' + old.files.length); clearInterval(timer); }
    if (polls > 400) clearInterval(timer);
  }, 25);
  return fetch('/__rerendered', {method: 'POST'});
});
</script>"""


def page_for(variant: str) -> bytes:
    if variant == "spa_submit":
        return PAGE.replace(b"</main></html>", b"</main>" + SPA_SUBMIT + b"</html>")
    if variant == "file_rerender":
        page = PAGE.replace(b"</form>", b"</form>" + FILE_INPUT)
        return page.replace(b"</main></html>", b"</main>" + FILE_RERENDER + b"</html>")
    return f01.page_for(variant)


class Handler(f01.Handler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" and self.server.variant in ("spa_submit", "file_rerender"):
            self._send(f01.HTTPStatus.OK, "text/html; charset=utf-8", page_for(self.server.variant))
            return
        super().do_GET()


class JournalFixture(f01.JournalFixture):
    def __init__(self) -> None:
        import threading

        self.journal = f01.r207.TargetJournal()
        self.variant = "normal"
        self.signal = threading.Event()
        self.rerendered = threading.Event()
        f01.r207.ThreadingHTTPServer.__init__(self, ("127.0.0.1", 0), Handler)

    def configure(self, trial: str, token: str, *, variant: str = "normal", mode: str = "immediate") -> None:
        page_for(variant)
        super().configure(trial, token, variant="normal", mode=mode)
        self.variant = variant


def journal_summary(events: list[dict]) -> dict:
    """FIX-01 counts plus the file-input page events."""
    summary = f01.journal_summary(events)
    page = [e for e in events if e.get("kind") == "page_event"]
    summary.update({
        "old_file_events": sum(1 for e in page if e.get("node") == "old"
                               and str(e.get("event", "")).startswith(("input", "change", "files"))),
        "fresh_change_with_file": sum(1 for e in page if e.get("node") == "fresh"
                                      and str(e.get("event", "")).startswith("change")
                                      and str(e.get("event", "")).removeprefix("change") not in ("", "0")),
        "received": sum(1 for e in events if e.get("kind") == "received"),
    })
    return summary
