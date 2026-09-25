# kvnloo/cua#15 — browser window readiness

`wait_for_window` in `libs/cua-driver/examples/jev-use/python/run.py` already waits for an on-screen window. The `asyncio.sleep(0.25)` inside that loop is the poll interval, capped at 40 tries. An unrelated visual change is not readiness. No second wait subsystem is added.
