<p align="center"><a href="https://kurtliu309.github.io/hipcheck/"><img src="docs/assets/banner.jpg" alt="hipcheck" width="100%"></a></p>

<p align="center">
  <b>Broken paths and dead nodes. Found in one click.</b><br>
  <a href="https://kurtliu309.github.io/hipcheck/">Project page &amp; live demo</a> ·
  <a href="https://github.com/kurtliu309/hipcheck/releases/latest">Download</a> ·
  <a href="docs/assets/hipcheck-en.mp4">Watch the film (50 s)</a>
</p>

<p align="center"><img src="docs/assets/preview.gif" alt="Clicking rows in hipcheck frames each node in the network" width="640"></p>

# hipcheck

A small Houdini tool that checks a scene for path problems and cleans up nodes
that do nothing.

- **Check** (whole hip): input files that do not exist, and hardcoded absolute
  paths that will break when the project moves.
- **Clean** (current SOP network): floating nodes and unused branches — nodes
  whose result never reaches anything that matters. Select them, colour them,
  ignore them, or delete them.

Everything hipcheck changes is one undo step: **Ctrl+Z** reverts it.

Requires Houdini 21 (written to also run on 20.5).

## Install

hipcheck sets itself up from inside Houdini: you never edit a config file or
hunt for your preferences folder.

**1. Download and unzip.** Get `hipcheck-vX.Y.Z.zip` from
[Releases](https://github.com/kurtliu309/hipcheck/releases/latest) and unzip it
somewhere it can stay, for example `D:/tools/hipcheck`. Houdini loads the tool
from this folder every time it starts, so do not leave it in a folder you clear out.

**2. Open the Python Shell.** In Houdini's top menu choose
**Windows → Python Shell** (or press **Alt+Shift+P**). A small window with a
`>>>` prompt opens.

<img src="docs/install/1-python-shell.png" alt="Windows menu with Python Shell highlighted" width="345">

**3. Paste this line and press Enter.**

```python
p = hou.text.expandString(hou.ui.selectFile(title="Select install.py in the hipcheck folder", pattern="install.py")); p and exec(open(p, encoding="utf-8").read(), {"__file__": p})
```

<img src="docs/install/2-paste.png" alt="The install line pasted into the Python Shell" width="560">

**4. Pick `install.py`.** A file browser opens. Go to the folder you unzipped
(type its path into **Look in** and press Enter, or click through the folders),
select `install.py` and click **Accept**.

<img src="docs/install/3-pick-install.png" alt="Houdini file browser with install.py selected" width="560">

**5. Done.** A message says hipcheck is installed. Click **OK**.

<img src="docs/install/4-installed.png" alt="Message: hipcheck is installed" width="560">

A **hipcheck** tab is now at the end of your shelf tabs. Click the **hipcheck**
button on it to open the tool. No restart needed.

<img src="docs/install/5-shelf.png" alt="The hipcheck shelf tab and button at the end of the shelf tabs" width="100%">

What the installer does: it asks Houdini where your user preferences are (so a
OneDrive or moved Documents folder, or `HOUDINI_USER_PREF_DIR`, just works),
writes `packages/hipcheck.json` there pointing at your folder, loads it, and adds
the hipcheck shelf tab.

- **Moved the folder or got a new version?** Run steps 2–4 again from the new
  folder, then restart Houdini.
- **Uninstall:** delete `hipcheck.json` from the `packages` folder (the
  installer's message shows the full path) and restart Houdini.

<details><summary>Install by hand instead</summary>

1. Copy `hipcheck.json` into the `packages` folder of your Houdini user
   preferences (create it if needed), e.g. `Documents/houdini21.0/packages`.
2. Change the one path in it to your folder, with forward slashes:
   `{"HIPCHECK": "D:/tools/hipcheck"}`
3. Restart Houdini, then on a shelf bar click `+` → **Shelves** → tick **hipcheck**.

</details>

## Open

Click the **hipcheck** button on the hipcheck shelf tab.

Optional hotkey: right-click the button -> **Edit Tool...** -> **Hotkeys**.

You can also open it from the Python Shell:

```python
import hipcheck.ui; hipcheck.ui.show()
```

## The window

```
[Check (3)] [Clean (7)]                                  [Rescan]
+--------------------------------------------------------------+
|  list                                                        |
|  [Select All]                              [Delete Selected] |
+--------------------------------------------------------------+
[Color Selected]                 [ ] Show Ignored [Ignore Selected]
```

- **Rescan** scans again (the window does not update by itself).
- Click a row to select its node in Houdini, if the node is in the network you
  are looking at. Nothing happens for nodes in other networks. Press `F` in the
  network editor to frame the selection.
- Ctrl / Shift click to select several rows. **Select All** selects every row.
- The **jump** icon at the right end of a row (or a double-click on the row)
  goes to the node: it switches the network editor to the node's network, then
  selects and frames it.
- **Ctrl+C** or right-click -> **Copy Path** copies the node paths of the
  selected rows.
- Click a column header to sort by it.

### Check tab

| Type | Meaning |
|---|---|
| Missing input file | A file path the node reads from does not exist on disk. |
| Absolute path | The path is typed as `D:/...` or `//server/...` instead of starting with `$HIP` / `$JOB`. |

Not reported, on purpose:
- parameters still at their default value (fresh cameras, materials, ROPs);
- output paths of nodes that write files (ROPs, File Cache in write mode, ...),
  which do not exist until you render or cache;
- relative paths such as `defcam.bgeo`, which Houdini finds in its own folders;
- nodes inside locked HDAs, and hidden or greyed-out parameters.

A path that uses `$F` counts as found if the file exists at the current frame,
the first frame or the last frame.

### Clean tab

Works on the SOP network the network editor is showing when you scan.

A node is **kept** if it is, or feeds into, any of:
- a node with the display, render, template or footprint flag;
- a node whose name starts with `OUT` (any case);
- a node that writes files (File Cache, ROPs);
- a locked node, or a node with a comment;
- a node referenced from anywhere in the hip (`ch()` expressions, Object Merge
  paths, `op:` paths, node names in parameters or wrangle code).

Everything else is listed:
- **Floating**: a chain not connected to anything that is kept.
- **Unused branch**: a chain that takes input from the kept part but whose
  output goes nowhere.

Rows are grouped Status -> Chain -> node. Selecting a Status row selects all of
its nodes; selecting a Chain row selects that chain.

**Delete Selected** first scans again and only deletes nodes that are still
unused, then asks for confirmation. Ctrl+Z brings them back.

### Colour and ignore

- **Color Selected** turns the selected nodes red, so you can look at them in
  the network before deciding.
- **Ignore Selected** marks the selected nodes so they no longer show up in
  either tab. The mark is saved with the hip file.
- Tick **Show Ignored** to list ignored nodes again (greyed out). Select them
  and the button reads **Unignore Selected**.

## Limitations

- Cleaning works in SOP networks only (checking covers the whole hip).
- Scanning runs in the foreground; very large scenes may pause for a moment.

## Tests

Run headless with hython from the hipcheck folder:

```
hython tests/run_tests.py
```

The last line reads `ALL PASS n/n` or `FAIL k/n`.

## License

MIT. See [LICENSE](LICENSE).
