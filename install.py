"""Install hipcheck into the running Houdini.

Run it from Houdini's Python Shell (see README). It asks Houdini where its user
preferences live, writes packages/hipcheck.json pointing at this folder, loads the
package and adds the hipcheck shelf tab. Running it again is safe.
"""

import json
import os

import hou


def _install():
    root = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
    if not os.path.isfile(os.path.join(root, "python", "hipcheck", "ui.py")):
        raise RuntimeError("install.py must stay inside the hipcheck folder:\n" + root)

    # Houdini's own answer, so redirected Documents, OneDrive and HOUDINI_USER_PREF_DIR all just work.
    packages = os.path.join(hou.homeHoudiniDirectory(), "packages").replace("\\", "/")
    os.makedirs(packages, exist_ok=True)
    pkg = packages + "/hipcheck.json"
    data = {
        "env": [
            {"HIPCHECK": root},
            {"PYTHONPATH": {"value": "$HIPCHECK/python", "method": "append"}},
        ],
        "path": "$HIPCHECK",
    }
    with open(pkg, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    loaded = hou.getenv("HIPCHECK")
    restart = bool(loaded) and loaded.replace("\\", "/").rstrip("/") != root
    if not loaded:
        hou.ui.loadPackage(pkg)

    shelf = hou.shelves.shelves().get("hipcheck")
    if shelf is None and not restart:
        hou.shelves.loadFile(root + "/toolbar/hipcheck.shelf")
        shelf = hou.shelves.shelves().get("hipcheck")
    if shelf is not None:
        sets = hou.ui.curDesktop().shelfDock().shelfSets()
        if sets and shelf not in sets[0].shelves():
            sets[0].setShelves(sets[0].shelves() + (shelf,))

    if restart:
        msg = ("hipcheck now points to:\n{}\n\nRestart Houdini to use this copy "
               "(the old one is still loaded).".format(root))
    else:
        msg = ("hipcheck is installed.\n\nClick the hipcheck button on the hipcheck "
               "shelf tab (top left, after your other shelf tabs).")
    hou.ui.displayMessage(msg, title="hipcheck", details="Package file: " + pkg)


try:
    _install()
except Exception as e:  # show the reason instead of a traceback in the shell
    hou.ui.displayMessage("hipcheck was not installed:\n\n" + str(e), title="hipcheck",
                          severity=hou.severityType.Error)
