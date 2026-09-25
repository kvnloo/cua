# CUA RFC atlases

GitHub Pages shelf for visual RFC roadmaps on the [kvnloo/cua](https://github.com/kvnloo/cua) fork.

The site is published from the `gh-pages` branch:

https://kvnloo.github.io/cua/

`main` stays aligned with upstream Cua. Atlas files live only on this branch.

## What is here

| Path | What it is |
| --- | --- |
| `index.html` | Catalog. Reads `artifacts.json`. |
| `artifacts.json` | Registry of atlases on the shelf. |
| `rfcs/3963/` | RFC 3963 architecture atlas (script-speed computer use). |

RFC 3963 is [trycua/cua#3963](https://github.com/trycua/cua/issues/3963). The atlas is pinned to commit `a959b2a23f8099769d0d57e4b8c2c8e70bf7d036`.

Companion files shipped with that atlas:

- `atlas.json` — machine-readable atlas, extracted from the page
- `syntax-pilot.json` — AST pilot of `libs/cua-driver/examples/jev-use/python/run.py`
- `requirements-remapped.csv` — the 120 remapped requirements
- `snapshot/libs/cua-driver/examples/jev-use/python/run.py` — source whose SHA-256 matches the pilot record

The downloaded page also links `architecture-report.md` and `prior-graph.json`. Those two files were not in the download, so those two buttons 404 until they are added beside `index.html`.

## Add the next atlas

1. Create `rfcs/<issue>/index.html`.
2. Put companion files in that same directory.
3. Append an object to the `artifacts` array in `artifacts.json` (copy the 3963 entry and edit it).
4. Commit on `gh-pages` and push. GitHub Pages republishes this branch.

A link back to the catalog belongs at the top of the atlas sidebar:

```html
<a class="home" href="../../">All RFCs</a>
```
