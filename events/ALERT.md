# ALERT: pipeline/analyse.py fails under the default python3 (2026-11-01 evening run)

`python3 pipeline/analyse.py O` stops with a SyntaxError at line 292:

    (f' ({int(rank * 100)}%, n={s['n']})' if s else '')
    SyntaxError: f-string: f-string: unmatched '['

The cloud image's `python3` is 3.11, and reusing the same quote type inside an f-string needs Python 3.12 or later. `python3.13 pipeline/analyse.py TKR` works. Tonight's six earnings previews didn't need it. But list, breakdown and quality-check stories rely on it, and runs that call plain `python3` will fail.

Fix: use `s["n"]` inside that f-string, or pin the routine to python3.12 or later. The writer doesn't touch pipeline/, so this needs the owner.
