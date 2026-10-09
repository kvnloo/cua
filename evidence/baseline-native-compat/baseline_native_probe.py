# Baseline adaptation: identical true/false/omitted request and native call.
# Successor-only enum cases are unavailable on baseline; do not transplant bindings.
# Expected outcomes changed to baseline boolean acceptance.
"""Run with PYTHONPATH pointing to the pinned candidate's committed bindings."""
from cua_driver import _native as n
from cua_driver import _native_contract as c
import json
r = n.CursorMoveRequest(from_point=n.CursorMotionPoint(x=0, y=0), to_point=n.CursorMotionPoint(x=20, y=20), from_heading=0, end_heading=None, target=None, seed='compat', reduced_motion=False)
results = []
for name, value in [('true', True), ('false', False), ('omitted', None)]:
    p = n.default_cursor_motion_params()
    p.effects.trail = value
    try:
        trajectory = n.plan_cursor_move(p, r)
        results.append({'input': name, 'outcome': 'native_call_returned', 'type': type(trajectory).__name__})
    except Exception as e:
        results.append({'input': name, 'outcome': 'rejected', 'exception': type(e).__name__, 'message': str(e)})
print(json.dumps(results, indent=2))
assert [r['outcome'] for r in results] == ['native_call_returned'] * 3
assert all(r['type'] == 'CursorTrajectory' for r in results)
assert not hasattr(c, 'CursorEffectSetting'), 'Baseline unexpectedly exports successor enum'
