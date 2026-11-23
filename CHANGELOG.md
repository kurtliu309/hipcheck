# Changelog

## 1.3.2

- `install.py`: one-step install from Houdini's Python Shell. It asks Houdini for its
  user preference folder, writes `packages/hipcheck.json` pointing at the unzipped
  folder, loads the package and adds the hipcheck shelf tab. No restart, no config
  editing. Manual install is still documented.
- README and project page: install steps rewritten around the installer, with
  screenshots (`docs/install/`).
- Project page: clearer section titles; film end card lists what the tool does.

## Project page (no code change)

- `docs/`: GitHub Pages site with the product film and a live, scrubbable demo;
  English and Chinese on one page.
- README: banner, preview and links to the site and film.
- MIT license. `hipcheck.json` ships with a placeholder path; the example scene
  script reads `$HIPCHECK` instead of a fixed path.

## 1.3.1

- UI: Unused branch starts expanded (its chains collapsed); Floating stays
  collapsed.
- README rewritten for first-time users (install on Windows / Linux / macOS,
  what each tab reports and keeps, colour / ignore / delete).
- docs/design.md window section matches the tab layout.

## 1.3.0

Ignore marks, fewer buttons, and backup / colour restoring removed: Ctrl+Z is the undo.

- UI: two tabs, Check (n) and Clean (n); Rescan sits in the tab bar corner.
  Clean lists Status > Chain > node (a status with one chain lists its nodes
  directly); selecting a status row selects all its nodes, so the Select
  Floating / Select Unused buttons are gone. Each tab keeps its own Select All
  (Clean also Delete Selected); below the tabs: Color Selected, Show Ignored and
  Ignore Selected (reads Unignore Selected when every selected node is ignored).
  Ignored rows show greyed when Show Ignored is on. Undo All and Restore Colors
  removed. All buttons share one width so the rows line up as columns.

- Actions: new `ignore(paths)` / `unignore(paths)` / `is_ignored(node)`. The mark
  is node userData `hipcheck_ignore = "1"` (`actions.IGNORE_KEY`), set and
  removed inside the undo groups `hipcheck: ignore` / `hipcheck: unignore`;
  both return the number of nodes changed. Verified in hython that userData
  changes are undoable (one Ctrl+Z per action).
- Actions: `colorize(paths)` colors red inside `hipcheck: color` and no longer
  records the original colour. `delete(paths)` destroys the nodes inside
  `hipcheck: delete` and returns the count; there is no backup step and no
  "hip must be saved" rule. Removed `restore_colors()`, `ORIG_COLOR_KEY`,
  `backup_then_delete()` and the backup helpers.
- Check: `check_hip(include_ignored=False)` drops issues on ignored nodes by
  default; every issue carries an `ignored` flag. With `include_ignored=True`
  they are returned again, flagged.
- Clean: `scan_layer(layer, include_ignored=False)` runs the analysis unchanged
  (ignore marks never affect endpoints, useful nodes or grouping), then removes
  ignored node paths from each group's `node_paths` and drops empty groups.
  Every group gains `ignored_paths` (the ignored subset of its `node_paths`;
  empty by default). With `include_ignored=True` the nodes stay, flagged.
- Docs: design.md drops backup / Restore Colors / Undo All and documents the
  ignore marks; the "ignore list" item moved out of To do.
- Tests: 22 (new: ignore round trip + undo, `check_hip` / `scan_layer` ignore
  filtering, colour undo, delete + undo; the backup and restore tests are
  gone), `ALL PASS 22/22`.

## 1.2.0

UI layout pass (from real-project feedback) and fewer false positives in Check.

- UI: the jump cell is a painted push button with Houdini's `BUTTONS_jump` icon
  (like Object Merge's "jump to operator"); painted by a delegate, not a widget
  per row. Group rows have it too. Double-clicking any row jumps as well; Clean
  groups expand with the arrow only.
- UI: columns are user-resizable (fitted to content on the first fill, then
  kept); Reason / Node fill the rest; long paths are elided in the middle, full
  path in the tooltip.
- UI: Ctrl+C and right-click > Copy Path copy the selected rows' node paths.
- UI: Select All is a small button at the bottom-left of each list, next to the
  count. Check type label "Missing input file".
- UI tests: all 20 pass again.

- Check: only user-set parms are checked (`parm.isAtDefault()` skips a parm for
  both the missing-file and the absolute-path check). A fresh camera, material
  and ROP now produce no issues. The default camera's noise came from its init
  script's internal File SOP with `file = defcam.bgeo`, not from the camera
  itself.
- Check: write paths are never existence-checked. File-writing nodes are now
  every Driver-category node (ROPs anywhere, including ROPs inside SOP, LOP and
  TOP networks), plus the existing `rop_*` / File Cache / execute-button
  detection. The absolute-path check still applies to write parms.
- Check: relative paths (not absolute after expansion, e.g. `defcam.bgeo`,
  material `includes`) are never reported as missing; Houdini resolves them
  through its own search paths.
- Check wording: reasons are now "File not found: <path>" and "Hardcoded
  absolute path: <path> (not relative to $HIP/$JOB)"; the `kind` keys are
  unchanged.
- Tests: 20 (new: default camera/material/ROP, user-set ROP output path,
  relative read path, user-set missing read path still reported). All scan
  tests pass; the UI tests were red at the time of this change because of the
  parallel `ui.py` edit.

## v1.1.2 — 2026-11-23

Small UI changes after the v1.1.1 GUI test.

- UI: "Select All" is now a plain button above each list instead of a checkbox.
  One click selects every row of that list (nodes inside collapsed groups
  included); the other list is cleared by the existing mutual-exclusion rule.
  The checkbox state, `_sync_select_all`, the `blockSignals` sync and the
  select/clear-on-toggle logic are gone.
- UI: Clean groups start collapsed.
- UI: the jump column uses Houdini's own "jump to operator" icon
  (`hou.qt.Icon("BUTTONS_jump")`, created once per fill, set with
  `item.setIcon`) instead of the "→" text; hython has no `hou.qt`, so tests
  still get "→". No per-row widgets.
- UI: Clean group rows have the jump icon too. Clicking it switches the network
  editor to the layer of the group's nodes, selects all of them (undo disabled),
  makes the first current and frames them all. `_jump_to` now takes a list of
  nodes; the single-node jump is the 1-element case.
- Tests: 19, `ALL PASS 19/19` (updated: no checkboxes, groups collapsed, group
  row jump cell, jump helper with a list and with a missing node).

## v1.1.1 — 2026-11-23

Fix list from the review and the real GUI test.

- Performance: `scan._collect_referenced_paths` compiles ONE alternation regex
  per scan (longest path first) and runs one `finditer` per string parm,
  instead of one regex search per candidate per parm; it exits early once every
  candidate is referenced, and `ref_node.path()` is read once per node.
- Performance: `check_hip` computes the current frame and playbar range once
  per call, evaluates a parm at all three frames only when its raw text has a
  frame token, and computes `_node_reads_from_disk` once per node.
- Fix: Delete Selected re-runs `scan_layer()` on the network editor's current
  layer and deletes only the selected paths that are still unused. The dialog
  names the layer and reports how many selected nodes were kept. This covers a
  stale list and a different hip loaded while the window is open.
- Fix: a selection with no node in the current layer leaves the Houdini
  selection untouched; hipcheck selection changes and jumps run inside
  `hou.undos.disabler()` and add no undo entries.
- Fix: the two lists are mutually exclusive, the Select All checkboxes follow
  manual selection, both trees block signals while refilling, and the status
  line always reports the real selection count and layer.
- Fix: Restore Colors restores every node hipcheck recorded in the whole hip.
- Fix: Undo All skips the pure selection entries ("Change Selection") that the
  user's network-editor clicks push on top of hipcheck operations; it still
  stops at the first other label and counts only hipcheck operations.
- Fix: `_network_editor()` uses the current NetworkEditor tab; the previous
  `currentPaneTab()` call does not exist in Houdini 21.
- UI: window opens at 1000x760 and the splitter gives Clean at least half the
  height.
- Clean-up: removed over-defensive try/except around Houdini queries (none of
  them raise in Houdini 21); `_all_nodes()` no longer swallows errors; merged
  the file/node parm-type helpers into `_string_parm_type`; deleted the dead
  `eval()` fallback and the old `[r, g, b]` colour format branch.
- Tests: 19 (new: delete re-validation drops a newly used node, a selection in
  another layer leaves the Houdini selection alone, Undo All skips selection
  entries, `restore_colors()` restores other layers), `ALL PASS 19/19`.
  `tests/perf_check.py` measures `scan_layer` / `check_hip` on a generated
  scene on demand (not part of the test run).

## v1.1.0 — 2026-11-23

UI rework; everything tracked in git is now English.

- UI: both lists support multi-selection (Ctrl / Shift). Selecting rows selects
  the matching nodes in the current layer only; there is no pwd switch and no
  framing (the user presses F).
- UI: a "Select All" checkbox above each list selects / clears every row.
- UI: the rightmost cell of every node row is a jump cell ("→"). Clicking it
  switches the network editor to the node's parent, selects the node, makes it
  current and frames it. It is a plain column handled in `itemClicked`, not a
  per-row widget.
- UI: the Clean list no longer has checkboxes; groups are expanded by default.
- UI: buttons are Rescan / Color Selected / Restore Colors / Delete Selected /
  Undo All. "Highlight All" was removed.
- UI: Color Selected colors the selected rows' nodes (both lists, deduplicated)
  red. Restore Colors works as before.
- UI: Undo All undoes hipcheck operations from the top of the undo stack and
  stops at the first non-hipcheck operation, so the user's own edits are never
  undone. Every hipcheck undo group is labelled `hipcheck: <action>`.
- UI: rescan only after operations that can change the result (delete, undo).
- Actions: `colorize()` accepts nodes or paths and always colors red;
  `highlight()` was removed.
- Performance: trees are filled in batches with updates disabled and there are
  no per-row widgets, so thousands of rows stay fast.
- Language: all tracked files are English (UI, messages, comments, docstrings,
  docs, tests). `HANDOFF.md` stays Chinese and is now git-ignored, as is the
  generated `tests/example/backup/` directory. The example scene was rebuilt
  with English text.
- Tests: 17 (new: layer-scoped selection, Undo All, clean tree without
  checkboxes, all-red colorize, undo labels), `ALL PASS 17/17`.

## v1.0.2 — 2026-11-23

Install / open flow reduced to the most common Houdini package setup, plus two
bugs found in real use.

- Fix: `hipcheck.json` used `env` to append to `HOUDINI_PATH`, which does not
  add the folder to the search path, so `toolbar/hipcheck.shelf` was never
  loaded automatically. It now sets `HIPCHECK`, appends to `PYTHONPATH`, and
  uses the top-level `"path": "$HIPCHECK"`. The path appears only once in the
  file, which makes it easy to edit.
- Fix: running `hipcheck.ui.show()` in Houdini's Python Shell deadlocked (the
  Shell runs on a non-main thread; Qt windows can only be shown on the main
  thread). `show()` now hands off to `hdefereval.executeDeferred` when called
  off the main thread.
- Change: `tests/example/build_example.py` no longer does its own `sys.path` /
  `putenv` / shelf `loadFile` and assumes the package is installed (the old
  approach hid the install bug).
- New: `README.md` with the three steps (where to put it / install / open), the
  optional hotkey, and the Python Shell entry point.
- 15 tests, unchanged, `ALL PASS 15/15`.

## v1.0.1 — 2026-11-22

Fixes after testing the example scene inside Kurt's Houdini UI.

- Fix: HDA internal nodes referencing their own parms (e.g. H21's Color SOP)
  were treated as external references and the node was wrongly kept. References
  from the node itself or from inside it no longer count.
- Fix: check false positives. Skip nodes inside locked HDAs (e.g. File Cache's
  read_back, topnet); skip grayed-out, hidden or factory-default file parms
  (e.g. scatter's `default.pic`); relative paths are also looked up on the
  Houdini search path.
- Fix: the window singleton lives on `hou.session`, so a module reload no longer
  creates a second window; `closeEvent` now calls `super()`.
- Change: after deleting, the status line keeps "backed up to ...; Ctrl+Z to
  undo" instead of being overwritten by "scan complete".
- Install: the package now goes into the pref dir the GUI Houdini really uses,
  `OneDrive/Documents/houdini21.0/packages`.
- 15 tests (two new ones: HDA self reference, check false positives; both fail
  if the fixes are reverted).
- Verified in the UI: window, check jump, highlight all, color, delete
  confirmation, backup (creates bak2; bak1 and the main hip untouched), single
  undo.

## v1.0.0 — 2026-11-22

First version.

- Check (whole hip): broken FileReference read paths (current frame / global
  start and end frame, sequence paths through wildcards), hardcoded absolute
  paths (drive letter / `//` / `\\`).
- Clean (current SOP layer): endpoints (display/render/template/footprint flag,
  names starting with `out`, file-writing nodes, locked, comment, referenced)
  walk upstream along inputs; the rest is grouped by connectivity into
  "floating" (purple) and "unused branch" (yellow).
- Reference detection: Houdini's own dependencies `dependents()` /
  `parmsReferencingThis()`, plus full paths, relative paths, `op:` and
  NodeReference parms in strings; searched across the whole hip.
- Actions: highlight all (select and frame), color, restore colors (original
  color stored in user data, survives save + reload), backup then delete.
  Color, restore and delete each get their own undo group.
- Delete backs up with `hou.hipFile.saveAsBackup()` behind three safeguards;
  a hip that was never saved refuses to delete.
- Non-modal singleton window, Qt imported through `hutil.Qt`; checks on top,
  expandable cleaning groups below (all checked by default).
- Houdini package `hipcheck.json` and a `hipcheck` shelf tool.
- 13 hython tests.
