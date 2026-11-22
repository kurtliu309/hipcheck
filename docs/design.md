# hipcheck design

Agreed with Kurt on 2026-11-22. Standalone tool, does not depend on kpipe.

## Running

- Python running inside Houdini. Target Houdini 21.0 (21.0.512 on this machine),
  written to stay compatible with 20.5: Qt is always imported through
  `hutil.Qt`, never PySide2/PySide6 directly.
- Location: the whole hipcheck folder can live anywhere (on this machine
  `D:/Kurt/Houdini/tools/hipcheck`).
- Install: only one file goes into Houdini — copy `hipcheck.json` into
  `$HOUDINI_USER_PREF_DIR/packages` and change the single path in the file (the
  value of `HIPCHECK`) to the real folder location, then restart Houdini. The
  package sets `HIPCHECK`, appends `$HIPCHECK/python` to `PYTHONPATH`, and the
  top-level `"path": "$HIPCHECK"` adds the folder to the search path (appending
  to `HOUDINI_PATH` inside `env` does not work; fixed in v1.0.2). See
  `README.md`.
- Open: on a shelf bar `+` -> Shelves -> tick `hipcheck`, click the `hipcheck`
  button (an optional hotkey can be bound in the tool's Edit Tool -> Hotkeys).
  Or run `import hipcheck.ui; hipcheck.ui.show()` in the Python Shell; `show()`
  moves itself to the main thread.
- The window is non-modal (parent is `hou.qt.mainWindow()`). Only one window exists at a time; clicking the entry again brings the
  open window forward and rescans.
- The layer is the current tab of the network editor: the first NetworkEditor
  pane tab that `isCurrentTab()`, else `paneTabOfType(NetworkEditor)`.
- The check logic (`scan.py`) and actions (`actions.py`) do not depend on the
  UI and can run and be tested headless in hython.

## Check tab (whole hip)

Each result row: problem type, node path, parm name, reason, and a jump cell.
The list is flat.

1. **Broken path**: only "read" file paths are checked.
   - File-reference string parms (`hou.stringParmType.FileReference`); empty
     values are skipped.
   - Write parms are not checked: a file-writing node's output path is skipped
     unless the node is in a "read from disk" mode (e.g. File Cache with load
     from disk on, File SOP in Read/Automatic mode). File-writing nodes are
     every Driver-category node (ROPs anywhere, including ROPs inside SOP, LOP
     or TOP networks), `rop_*` and File Cache SOPs, and nodes with an
     `execute` button. The absolute-path check still applies to their parms.
   - Evaluated at the current frame and at the global start and end frame; if
     the file exists for any of the three, it is fine. The frames are computed
     once per `check_hip()` call, and a parm is evaluated at all three only
     when its raw text contains a frame token (`$F`, `${F`, `$T`, `%0`, a
     backtick expression); otherwise once. Identical values are checked once.
   - Paths starting with `op:`: the target node must exist.
   - Not checked (added after UI testing in v1.0.1): top-level manager nodes
     (`/obj`, `/out`, `/stage`, `/tasks` themselves), nodes inside locked HDAs,
     grayed-out or hidden parms, and parms still at their factory default.
     `isAtDefault()` is skipped for both the missing-file and the
     absolute-path check, so a fresh camera, material or ROP is quiet even
     when Houdini's init script fills a parm (the default camera's internal
     File SOP has `defcam.bgeo`, which is not at default but resolves through
     Houdini's search paths).
   - Relative paths are never reported as missing: Houdini resolves them
     through its own search paths (built-in files such as `defcam.bgeo`,
     material `includes`), which cannot be reproduced reliably.
   - The reason strings are "File not found: <path>" and "Hardcoded absolute
     path: <path> (not relative to $HIP/$JOB)". The `kind` keys
     (`broken_path`, `absolute_path`) are unchanged.
2. **Hardcoded absolute path**: the raw parm text (`unexpandedString()`) starts
   with a drive letter (`D:/`, `D:\`) or a network path (`//`, `\\`) is
   reported. Text starting with a variable (`$HIP`, `$JOB`, ...) or a backtick
   expression can never match.
3. **Ignored nodes** (see Ignore marks below): issues on ignored nodes are
   dropped by default. `check_hip(include_ignored=True)` returns them again and
   every issue dict carries an `ignored` flag.

## Clean tab (current layer, SOP only in v1)

The current layer is the one the network editor is in when the scan runs. If it
is not a SOP network, or the editor is inside a locked HDA, the clean section
shows "unsupported" with the reason; checking still works.

### Endpoints (kept, together with all their upstream)

- Nodes with the display, render, template or footprint flag on.
- Nodes whose name starts with `out` (case-insensitive, any type).
- File-writing nodes: File Cache, ROP-type SOPs (type name contains `rop_` or
  `filecache`, or the node has an `execute` button parm).
- Locked nodes (hard lock or soft lock).
- Nodes with a comment.
- Referenced nodes (see below).

### References (searched across the whole hip)

Any node in the current layer referenced by something "outside this chain" is an
endpoint (references from the node itself or from inside it, e.g. an HDA
referencing its own parms, do not count):
- Houdini's own dependency tracking (`ch()` expressions, spare inputs).
- Strings mentioning the node: full path, relative paths such as `../name`,
  `op:` paths, names in node-reference parms, paths after `op:` in wrangle
  code. Better keep too much than delete something needed.

### Grouping

1. Walk upstream from every endpoint along input wires (all inputs count,
   including unselected Switch inputs and wires through bypassed nodes; network
   dots are seen through). Everything reached is "useful".
2. Group the remaining nodes by connectivity (a whole chain is one group):
   - a group with any node taking input from a "useful" node -> **unused branch**
   - otherwise -> **floating**
3. A subnetwork counts as one node and is not entered. Sticky notes and network
   boxes are not nodes and are never deleted. Network boxes left empty are kept.

### Ignore marks

- A node is ignored when its userData holds `hipcheck_ignore = "1"`
  (`actions.ignore()` / `actions.unignore()`). The mark survives save + reload.
- Ignore marks are applied only after the grouping analysis. They never change
  which nodes are endpoints, useful, floating or an unused branch: an ignored
  endpoint still keeps its upstream.
- `scan_layer()` removes ignored node paths from each group's `node_paths` and
  drops a group left empty. `scan_layer(..., include_ignored=True)` keeps them.
- Every group carries `ignored_paths`, the ignored subset of its `node_paths`;
  it is empty by default.

### Window

Two tabs, **Check (n)** and **Clean (n)** (counts in the tab titles). Rescan sits
in the tab bar's top-right corner. Each tab has a bold title row (count on the
right), its list, and its own button row: Check has Select All; Clean has
Select All and, on the right, Delete Selected. Below the tabs: Color Selected
on the left, Show Ignored + Ignore Selected together on the right. All buttons
except Rescan share one width and the row below the tabs is indented like the
rows inside, so the buttons line up as columns. A grey status line is last.

- Both lists use ExtendedSelection and are mutually exclusive: selecting rows in
  one clears the other's selection (signals blocked while clearing).
- On selection change the node paths of the selected rows are collected (a group
  row counts as all its nodes). Exactly the nodes whose parent is the network
  editor's current pwd are selected in Houdini; if none is in that layer the
  Houdini selection is left untouched. Selection changes run in
  `hou.undos.disabler()`. No pwd switch, no framing: the user presses F.
- Select All selects every top-level row (group rows stand for their nodes).
- Jump: the rightmost cell shows Houdini's `BUTTONS_jump` icon, painted by a
  delegate (hover highlight + hand cursor), not a widget per row. Clicking it, or
  double-clicking any row, switches the editor to the nodes' layer, selects
  them, makes the first current and frames them. Group rows jump to all nodes.
- Columns are user-resizable (fitted to content on the first fill, then kept);
  Reason / Node fill the rest; long paths elide in the middle with the full path
  as tooltip. Clicking a header sorts; Count sorts numerically. Default sort is
  the first column ascending (Clean: Floating before Unused branch).
- Ctrl+C or right-click -> Copy Path copies the selected rows' node paths.
- Clean tree: Status row -> Chain rows -> node rows; a status with a single
  chain lists its nodes directly. Floating starts collapsed, Unused branch
  starts expanded (chains collapsed). Clean groups expand with the arrow only:
  double-click jumps.
- Show Ignored rescans with `include_ignored=True`; ignored rows are greyed. The
  ignore button reads "Unignore Selected" when every selected node is ignored.
- Rescan after delete / ignore / unignore. Color does not change scan results.

### Delete flow

1. Re-validate: re-run `scan_layer()` on the network editor's current layer and
   keep only the selected paths that the fresh scan still reports as unused.
   This covers a stale list and another hip loaded while the window is open;
   the confirm dialog reports how many selected nodes are kept because they are
   no longer unused.
2. Confirmation: "Delete N node(s) in <layer>?" plus "M selected node(s) are no
   longer unused and will be kept." when some were dropped.
3. Delete the selected nodes with `actions.delete()` inside an undo group
   labelled `hipcheck: delete`. There is no backup: Ctrl+Z is the safety net.

### Undo labels

Every scene-changing action runs in an undo group whose label starts with
`hipcheck: ` (`ignore`, `unignore`, `color`, `delete`). One Ctrl+Z reverts one
hipcheck operation; there is no Undo All button.

## Performance

- Real hips can have thousands of nodes. Tree building disables updates,
  blocks signals and adds items in batches (`addTopLevelItems`); there are no
  per-row widgets.
- The selection handler is O(selected rows): one `hou.node()` lookup per path,
  no rescans.
- `_collect_referenced_paths` compiles ONE alternation regex for all paths of
  the layer (longest first, so a prefix never shadows a longer path) and runs
  one `finditer` per string parm, with an early exit once every candidate is
  referenced.
- Whether a node reads from disk is computed once per node, and only for nodes
  that have a file parm.

## To do (not in v1)

- Frame range consistency check (Kurt has not decided the exact rule; ranges
  often disagree in real work).
- Cleaning other networks: LOP, DOP, COP, TOP (VOP needs special handling for
  Parameter nodes).
- Docked panel (Python Panel), network editor right-click menu entry.
- Scanning in the background with progress for very large hips.
