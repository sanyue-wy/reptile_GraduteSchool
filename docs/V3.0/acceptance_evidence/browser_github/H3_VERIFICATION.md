# H3 Verification Report

**Window**: Independent falsification of H3's gitignore & clean clone conclusions  
**Date**: 2026-10-07  
**Verdict**: **refuted**

---

## Executive Summary

H3 claims to have fixed `.gitignore` and verified a clean clone drill. **Independent verification refutes these claims.** The working directory contains uncommitted fixes that mask critical defects in `HEAD`:

1. **Three entire modules are untracked** but imported by tracked code: `infra/errors/`, `infra/retry/`, `infra/state_tracker.py`
2. **`HEAD` has syntax errors** in `api/models.py` and `scripts/fix_tasks3.py` — `compileall` fails on a real git clone
3. **`HEAD` has a mkdocs configuration error** (`site_dir` inside `docs_dir`) — `mkdocs build --strict` fails on a real git clone
4. H3's "clean clone" test used `tar` (copies untracked files) instead of `git archive`/`git clone` — **the test was invalid**

---

## 1. `.gitignore` Fix for `templates/*/preview.png` — **CONFIRMED**

The fix on line 15 (`/preview.png` anchored to root) works correctly:

```
templates\academic-serif\preview.png: NOT IGNORED
templates\card-flow\preview.png: NOT IGNORED
... (all 20 template preview.png files) ...
templates\warm-amber\preview.png: NOT IGNORED
```

No false positives on `docs/` images:
```
docs\V3.0\acceptance_evidence\console_fix\e2e_1_overview_force_banner.png: NOT IGNORED
... (all 5 docs images) ...
```

**Conclusion**: The `.gitignore` change is correct and does not misfire.

---

## 2. Critical Untracked Paths — **MAJOR DEFECT**

H3 claimed "23 critical untracked paths are NOT ignored by .gitignore (all exit code 1 from `git check-ignore -v`)". While technically true that `.gitignore` doesn't ignore them, **they are not tracked in git** and therefore **will not exist in a real clone**.

| Path | Tracked? | Imported By |
|------|----------|-------------|
| `infra/errors/__init__.py` | ❌ UNTRACKED | `pipeline/stages/acquire.py:26`, `present.py:22`, `process.py:21`, `store.py:23`, `tests/test_http_context.py:18` |
| `infra/errors/plugin_error.py` | ❌ UNTRACKED | (internal) |
| `infra/retry/__init__.py` | ❌ UNTRACKED | `infra/http.py:23` |
| `infra/retry/adaptive_timeout.py` | ❌ UNTRACKED | `infra/retry/__init__.py:9` |
| `infra/state_tracker.py` | ❌ UNTRACKED | `api/server.py:1580` |
| `infra/storage/__init__.py` | ✅ tracked | — |
| `infra/storage/atomic_io.py` | ✅ tracked | — |
| `infra/storage/idempotency.py` | ✅ tracked | — |
| `infra/storage/workspace.py` | ✅ tracked | — |

**Evidence** — `git ls-files` output:
```
UNTRACKED: infra/errors/__init__.py
UNTRACKED: infra/errors/plugin_error.py
UNTRACKED: infra/retry/__init__.py
UNTRACKED: infra/retry/adaptive_timeout.py
UNTRACKED: infra/state_tracker.py
TRACKED: infra/storage/__init__.py
TRACKED: infra/storage/atomic_io.py
TRACKED: infra/storage/idempotency.py
TRACKED: infra/storage/workspace.py
```

**Evidence** — Tracked files importing untracked modules:
```
api/server.py:1580:        from infra.state_tracker import StateTracker
infra/http.py:23:from infra.retry.adaptive_timeout import AdaptiveTimeoutPolicy
pipeline/stages/acquire.py:26:from infra.errors import error_from_exception, plugin_setup_error
pipeline/stages/present.py:22:from infra.errors import error_from_exception, plugin_setup_error
pipeline/stages/process.py:21:from infra.errors import error_from_exception, plugin_setup_error
pipeline/stages/store.py:23:from infra.errors import error_from_exception, plugin_setup_error
tests/test_http_context.py:18:from infra.errors import (
```

---

## 3. `HEAD` Syntax Errors — **BLOCKING**

`compileall` fails on a real git clone because tracked files in `HEAD` have syntax errors:

### `api/models.py:369` — `global` is a Python keyword
```python
class ConfigResponseData(TypedDict):
    global: GlobalConfig  # SYNTAX ERROR
    schools: List[SchoolConfigItem]
```

```
*** Error compiling 'api\models.py'...
  File "api\models.py", line 369
    global: GlobalConfig
          ^
SyntaxError: invalid syntax
```

### `scripts/fix_tasks3.py:363` — Unterminated triple-quoted string
```
  SYNTAX ERROR in HEAD:scripts/fix_tasks3.py
    File "...", line 363
    ...
SyntaxError: unterminated triple-quoted string literal
```

### `scripts/fix_tasks_final.py` — Unclosed parenthesis
```
  SYNTAX ERROR in HEAD:scripts/fix_tasks_final.py
    ...
SyntaxError: '(' was never closed
```

**Working directory fix** (uncommitted): `api/models.py` uses functional `TypedDict("ConfigResponseData", {"global": GlobalConfig, ...})` syntax.

---

## 4. `HEAD` mkdocs Configuration Error — **BLOCKING**

`mkdocs.yml` in `HEAD` has `site_dir` inside `docs_dir`:

```
HEAD: site_dir: docs/_site_build
WORKING: site_dir: site_build
```

**Real clone result**:
```
ERROR   -  Config value 'site_dir': The 'site_dir' should not be within the 'docs_dir' 
         as this leads to the build directory being copied into itself...
Aborted with a configuration error!
Exit code: 1
```

---

## 5. Real Git Clone Drill — **FAILS**

Using `git archive HEAD` (simulates `git clone` — only tracked files):

| Check | Exit Code | Result |
|-------|-----------|--------|
| `python -m compileall -q api infra pipeline ...` | **1** | ❌ FAIL (syntax errors) |
| `python -m mkdocs build --strict` | **1** | ❌ FAIL (config error) |
| `import infra.errors` | **1** | ❌ FAIL (module not found) |
| `import infra.retry.adaptive_timeout` | **1** | ❌ FAIL (module not found) |
| `import infra.state_tracker` | **1** | ❌ FAIL (module not found) |

**H3's test used `tar --exclude=.git`** which copies **all** files including untracked directories — this is **not a valid clean clone test**.

---

## 6. Additional Findings

### Untracked test files with syntax errors (tracked in HEAD but deleted in working dir)
- `scripts/fix_tasks2.py` — deleted in working dir
- `scripts/fix_tasks3.py` — deleted in working dir, syntax error in HEAD
- `scripts/fix_tasks_final.py` — deleted in working dir, syntax error in HEAD
- `scripts/fix_tasks_final3.py` through `fix_tasks_final6.py` — deleted in working dir
- `scripts/replace_sse.py` — deleted in working dir

### Test failures in working directory (2 failed, 1032 passed, 4 skipped)
1. `tests/browser/test_responsive.py::test_no_horizontal_overflow` — Playwright timeout (flaky)
2. `tests/test_api_closed_loop_g2.py::TestPluginErrorsEndpoint::test_error_keys_intersect_with_plugins_list` — Logic assertion failure

---

## Verdict: REFUTED

| H3 Claim | Verification |
|----------|--------------|
| "Fixed .gitignore line 15" | ✅ Confirmed correct |
| "23 critical untracked paths NOT ignored" | ⚠️ Misleading — they're untracked, so missing from real clone |
| "Clean clone drill passed: compileall exit=0, mkdocs build --strict exit=0" | ❌ **FALSE** — real git clone fails both |
| "ci.yml review: all compileall directories exist in clean clone" | ❌ **FALSE** — syntax errors prevent compileall |

**Root cause**: H3 validated against a `tar` copy of the working directory (which includes untracked fixes), not against a real `git clone` of `HEAD`. The working directory has **uncommitted fixes** for all blocking issues, but none are in `HEAD`.

---

## Required Remediation (for H3 or follow-up)

1. `git add infra/errors/ infra/retry/ infra/state_tracker.py`
2. Commit the `api/models.py` TypedDict fix
3. Commit the `mkdocs.yml` site_dir fix
4. Remove or fix syntax-error scripts from `HEAD` (or delete from index)
5. Re-run clean clone drill with `git clone` or `git archive HEAD`

---

## Appendix: Commands Run

```bash
# .gitignore verification
for f in templates/*/preview.png; do git check-ignore -v "$f" 2>&1 || echo "NOT IGNORED: $f"; done

# Tracked status
git ls-files infra/errors/__init__.py infra/errors/plugin_error.py infra/retry/__init__.py infra/retry/adaptive_timeout.py infra/state_tracker.py

# Import scanning
grep -r "from infra\." --include="*.py" . | grep -v "__pycache__"

# HEAD syntax check
git show HEAD:api/models.py | python -m py_compile -
git show HEAD:scripts/fix_tasks3.py | python -m py_compile -

# Real clean clone
git archive HEAD | tar -xf - -C /tmp/clean_clone
cd /tmp/clean_clone && python -m compileall -q api infra ...
cd /tmp/clean_clone && python -m mkdocs build --strict
```