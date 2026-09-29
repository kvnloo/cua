# tools/list payload census (kvnloo/cua#76)

| metric | main-b8d619f57.default | pr4318-f2ff99daf.default |
|---|---|---|
| wire_bytes | 182949 | 183221 |
| tools_array_compact_bytes | 168406 | 168678 |
| tool_count | 62 | 62 |
| sum_input_schema_bytes | 68249 | 68521 |
| sum_output_schema_bytes | 47386 | 47386 |
| sum_description_bytes | 32842 | 32842 |
| sum_annotations_bytes | 5543 | 5543 |
| sum_embedded_description_bytes_input | 40161 | 40161 |
| sum_embedded_description_bytes_output | 168 | 168 |
| tools_with_output_schema | 39 | 39 |
| repeated identical input property defs (bytes) [main-b8d619f57.default] | 28050 |
| repeated identical input property defs (bytes) [pr4318-f2ff99daf.default] | 28288 |

## Delta (head - base)
```json
{
 "wire_bytes": 272,
 "added_tools": [],
 "removed_tools": [],
 "changed_tools": [
  {
   "tool": "click",
   "before_bytes": 8405,
   "after_bytes": 8439,
   "delta_bytes": 34
  },
  {
   "tool": "double_click",
   "before_bytes": 5224,
   "after_bytes": 5258,
   "delta_bytes": 34
  },
  {
   "tool": "hotkey",
   "before_bytes": 5480,
   "after_bytes": 5514,
   "delta_bytes": 34
  },
  {
   "tool": "press_key",
   "before_bytes": 5433,
   "after_bytes": 5467,
   "delta_bytes": 34
  },
  {
   "tool": "right_click",
   "before_bytes": 5658,
   "after_bytes": 5692,
   "delta_bytes": 34
  },
  {
   "tool": "scroll",
   "before_bytes": 5520,
   "after_bytes": 5554,
   "delta_bytes": 34
  },
  {
   "tool": "set_value",
   "before_bytes": 3317,
   "after_bytes": 3351,
   "delta_bytes": 34
  },
  {
   "tool": "type_text",
   "before_bytes": 5628,
   "after_bytes": 5662,
   "delta_bytes": 34
  }
 ],
 "sum_delta_bytes_changed_tools": 272
}
```

## main-b8d619f57.default: 15 largest tools

| tool | bytes | description | inputSchema | outputSchema | properties |
|---|---|---|---|---|---|
| get_window_state | 10021 | 3671 | 3537 | 2333 | 13 |
| click | 8405 | 2018 | 4536 | 1461 | 18 |
| drag | 5785 | 525 | 3485 | 1461 | 17 |
| right_click | 5658 | 800 | 3016 | 1461 | 13 |
| type_text | 5628 | 75 | 3705 | 1461 | 13 |
| scroll | 5520 | 127 | 3582 | 1461 | 16 |
| hotkey | 5480 | 565 | 3129 | 1461 | 12 |
| press_key | 5433 | 55 | 3565 | 1461 | 14 |
| double_click | 5224 | 475 | 2878 | 1461 | 12 |
| start_recording | 5221 | 3393 | 1522 | 0 | 5 |
| parse_visual_regions | 4501 | 80 | 766 | 3315 | 2 |
| page | 4345 | 2017 | 2050 | 0 | 12 |
| verify_state | 4087 | 435 | 2294 | 987 | 7 |
| parallel_mouse_drag | 3880 | 617 | 1491 | 1461 | 1 |
| browser_type | 3623 | 449 | 1409 | 1461 | 7 |

### largest repeated input-property definitions

| property | def bytes | occurrences | repeated bytes |
|---|---|---|---|
| delivery_mode | 846 | 8 | 5922 |
| session | 208 | 15 | 2912 |
| coordinate_frame | 364 | 9 | 2912 |
| target | 705 | 5 | 2820 |
| element_token | 267 | 8 | 1869 |
| session | 282 | 7 | 1692 |
| element_index | 172 | 8 | 1204 |
| snapshot_id | 170 | 8 | 1190 |
| x | 219 | 6 | 1095 |
| y | 140 | 6 | 700 |

### repeated outputSchema objects

- 1461 B x 19 tools -> 26298 B repeated (set_window_frame, invoke_menu, click, double_click, right_click, drag, …)
- 854 B x 2 tools -> 854 B repeated (escalate_session, get_session_state)

### repeated description strings (top)

- 754 B x 8 = 5278 B repeated: `Input delivery mode. 'background' (default) never activates or raises the target window. On X11 it injects via XTEST / t…`
- 174 B x 15 = 2436 B repeated: `For multi-call work, prefer a short public session label and repeat it on every call that accepts it. Omit it to use the…`
- 296 B x 9 = 2368 B repeated: `Frame of x/y (and from_x/from_y/to_x/to_y). Default "window": window-local screenshot pixels as returned by get_window_s…`
- 233 B x 8 = 1631 B repeated: `Opaque per-snapshot element handle from `structuredContent.elements[].element_token`. If element_index, snapshot_id, or …`
- 254 B x 7 = 1524 B repeated: `Exact capture/input target selected independently for each action.

`display_id="primary"` is the portable desktop targe…`
- 248 B x 7 = 1488 B repeated: `For multi-call work, prefer a short public session label and repeat it on every call that accepts it. Omit it to use the…`
- 137 B x 8 = 959 B repeated: `Element index from get_window_state. Requires the matching `snapshot_id` alongside it. Prefer `element_token`, which car…`
- 181 B x 6 = 905 B repeated: `Window-local pixel X of the target window's own get_window_state screenshot (0..screenshot_width). For get_desktop_state…`

### properties whose definition diverges across tools (top)

- `session`: 10 distinct definitions; top variants (bytes x tools): 208x15, 282x7, 209x4, 272x3, 209x2
- `delivery_mode`: 2 distinct definitions; top variants (bytes x tools): 846x8, 198x1
- `target`: 3 distinct definitions; top variants (bytes x tools): 705x5, 783x1, 677x1
- `x`: 8 distinct definitions; top variants (bytes x tools): 219x6, 558x1, 378x1, 255x1, 126x1
- `y`: 8 distinct definitions; top variants (bytes x tools): 140x6, 126x1, 77x1, 66x1, 63x1
- `target_id`: 3 distinct definitions; top variants (bytes x tools): 120x6, 88x1, 79x1

### element_token schema shapes
```json
[
 {
  "schema": {
   "description": "Opaque per-snapshot element handle from `structuredContent.elements[].element_token`. If element_index, snapshot_id, or window_id are also supplied they must agree. Returns an explicit stale error once a newer snapshot supersedes it.",
   "type": "string"
  },
  "bytes": 267,
  "tools": 8,
  "tool_names": [
   "click",
   "double_click",
   "right_click",
   "type_text",
   "press_key",
   "hotkey",
   "set_value",
   "scroll"
  ]
 }
]
```

### tokens (main-b8d619f57.default)
```json
{
 "tokenizer": {
  "package": "gpt-tokenizer",
  "version": "4.0.0",
  "license": "MIT"
 },
 "counts": {
  "o200k_base": {
   "tools_array_compact_json": 37881,
   "descriptions_only": 7021,
   "input_schemas_only": 14830,
   "output_schemas_only": 11345
  },
  "cl100k_base": {
   "tools_array_compact_json": 36431,
   "descriptions_only": 7006,
   "input_schemas_only": 14393,
   "output_schemas_only": 10641
  }
 }
}
```

## pr4318-f2ff99daf.default: 15 largest tools

| tool | bytes | description | inputSchema | outputSchema | properties |
|---|---|---|---|---|---|
| get_window_state | 10021 | 3671 | 3537 | 2333 | 13 |
| click | 8439 | 2018 | 4570 | 1461 | 18 |
| drag | 5785 | 525 | 3485 | 1461 | 17 |
| right_click | 5692 | 800 | 3050 | 1461 | 13 |
| type_text | 5662 | 75 | 3739 | 1461 | 13 |
| scroll | 5554 | 127 | 3616 | 1461 | 16 |
| hotkey | 5514 | 565 | 3163 | 1461 | 12 |
| press_key | 5467 | 55 | 3599 | 1461 | 14 |
| double_click | 5258 | 475 | 2912 | 1461 | 12 |
| start_recording | 5221 | 3393 | 1522 | 0 | 5 |
| parse_visual_regions | 4501 | 80 | 766 | 3315 | 2 |
| page | 4345 | 2017 | 2050 | 0 | 12 |
| verify_state | 4087 | 435 | 2294 | 987 | 7 |
| parallel_mouse_drag | 3880 | 617 | 1491 | 1461 | 1 |
| browser_type | 3623 | 449 | 1409 | 1461 | 7 |

### largest repeated input-property definitions

| property | def bytes | occurrences | repeated bytes |
|---|---|---|---|
| delivery_mode | 846 | 8 | 5922 |
| session | 208 | 15 | 2912 |
| coordinate_frame | 364 | 9 | 2912 |
| target | 705 | 5 | 2820 |
| element_token | 301 | 8 | 2107 |
| session | 282 | 7 | 1692 |
| element_index | 172 | 8 | 1204 |
| snapshot_id | 170 | 8 | 1190 |
| x | 219 | 6 | 1095 |
| y | 140 | 6 | 700 |

### repeated outputSchema objects

- 1461 B x 19 tools -> 26298 B repeated (set_window_frame, invoke_menu, click, double_click, right_click, drag, …)
- 854 B x 2 tools -> 854 B repeated (escalate_session, get_session_state)

### repeated description strings (top)

- 754 B x 8 = 5278 B repeated: `Input delivery mode. 'background' (default) never activates or raises the target window. On X11 it injects via XTEST / t…`
- 174 B x 15 = 2436 B repeated: `For multi-call work, prefer a short public session label and repeat it on every call that accepts it. Omit it to use the…`
- 296 B x 9 = 2368 B repeated: `Frame of x/y (and from_x/from_y/to_x/to_y). Default "window": window-local screenshot pixels as returned by get_window_s…`
- 233 B x 8 = 1631 B repeated: `Opaque per-snapshot element handle from `structuredContent.elements[].element_token`. If element_index, snapshot_id, or …`
- 254 B x 7 = 1524 B repeated: `Exact capture/input target selected independently for each action.

`display_id="primary"` is the portable desktop targe…`
- 248 B x 7 = 1488 B repeated: `For multi-call work, prefer a short public session label and repeat it on every call that accepts it. Omit it to use the…`
- 137 B x 8 = 959 B repeated: `Element index from get_window_state. Requires the matching `snapshot_id` alongside it. Prefer `element_token`, which car…`
- 181 B x 6 = 905 B repeated: `Window-local pixel X of the target window's own get_window_state screenshot (0..screenshot_width). For get_desktop_state…`

### properties whose definition diverges across tools (top)

- `session`: 10 distinct definitions; top variants (bytes x tools): 208x15, 282x7, 209x4, 272x3, 209x2
- `delivery_mode`: 2 distinct definitions; top variants (bytes x tools): 846x8, 198x1
- `target`: 3 distinct definitions; top variants (bytes x tools): 705x5, 783x1, 677x1
- `x`: 8 distinct definitions; top variants (bytes x tools): 219x6, 558x1, 378x1, 255x1, 126x1
- `y`: 8 distinct definitions; top variants (bytes x tools): 140x6, 126x1, 77x1, 66x1, 63x1
- `target_id`: 3 distinct definitions; top variants (bytes x tools): 120x6, 88x1, 79x1

### element_token schema shapes
```json
[
 {
  "schema": {
   "description": "Opaque per-snapshot element handle from `structuredContent.elements[].element_token`. If element_index, snapshot_id, or window_id are also supplied they must agree. Returns an explicit stale error once a newer snapshot supersedes it.",
   "pattern": "^s[0-9a-f]{8}:[0-9]+$",
   "type": "string"
  },
  "bytes": 301,
  "tools": 8,
  "tool_names": [
   "click",
   "double_click",
   "right_click",
   "type_text",
   "press_key",
   "hotkey",
   "set_value",
   "scroll"
  ]
 }
]
```

### tokens (pr4318-f2ff99daf.default)
```json
{
 "tokenizer": {
  "package": "gpt-tokenizer",
  "version": "4.0.0",
  "license": "MIT"
 },
 "counts": {
  "o200k_base": {
   "tools_array_compact_json": 38041,
   "descriptions_only": 7021,
   "input_schemas_only": 14990,
   "output_schemas_only": 11345
  },
  "cl100k_base": {
   "tools_array_compact_json": 36583,
   "descriptions_only": 7006,
   "input_schemas_only": 14545,
   "output_schemas_only": 10641
  }
 }
}
```

