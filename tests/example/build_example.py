# Build an example scene in a Houdini session with the package installed
# (for a visual acceptance test in the UI).
import os, hou

ROOT = os.environ["HIPCHECK"]  # set by the hipcheck package

geo = hou.node("/obj").createNode("geo", "example_geo")
for c in geo.children():
    c.destroy()

# Trunk: box -> xform -> switch -> OUT (OUT has no display flag; endpoints are
# recognized by name).
box = geo.createNode("box", "main_box")
xf = geo.createNode("xform", "main_xform"); xf.setInput(0, box)
alt = geo.createNode("sphere", "switch_alt_input")
sw = geo.createNode("switch", "main_switch"); sw.setInput(0, xf); sw.setInput(1, alt)
byp = geo.createNode("null", "bypassed_null"); byp.setInput(0, sw); byp.bypass(True)
out = geo.createNode("null", "OUT_main"); out.setInput(0, byp)
disp = geo.createNode("null", "display_here"); disp.setInput(0, out)
disp.setDisplayFlag(True); disp.setRenderFlag(True)

# Floating chain
f1 = geo.createNode("grid", "float_grid")
f2 = geo.createNode("mountain", "float_mountain"); f2.setInput(0, f1)
f3 = geo.createNode("null", "float_end"); f3.setInput(0, f2)

# Unused branch: dangles off the trunk
d1 = geo.createNode("color", "dead_color"); d1.setInput(0, xf)
d2 = geo.createNode("null", "dead_end"); d2.setInput(0, d1)

# Name that looks like out but does not start with it: still unused
lay = geo.createNode("null", "layout1"); lay.setInput(0, box)

# Kept: dangling but writes files / has a comment / is referenced / locked
fc_src = geo.createNode("scatter", "cache_src"); fc_src.setInput(0, box)
fc = geo.createNode("filecache::2.0", "dangling_filecache"); fc.setInput(0, fc_src)
cm = geo.createNode("null", "commented_keep"); cm.setInput(0, box); cm.setComment("keep on purpose")
ref = geo.createNode("null", "referenced_keep"); ref.parm("copyinput").set(1)
xf.parm("tx").setExpression('ch("../referenced_keep/scale")')
# Reference: mentioned by an object_merge path
om_target = geo.createNode("tube", "objmerge_target")
om = geo.createNode("object_merge", "om_reader"); om.parm("objpath1").set("../objmerge_target")
mrg = geo.createNode("merge", "merge_main"); mrg.setInput(0, out); mrg.setInput(1, om)
mrg.setDisplayFlag(True); mrg.setRenderFlag(True)

# Check items: broken read path + hardcoded absolute path
rd = geo.createNode("file", "broken_read"); rd.parm("file").set("$HIP/geo/does_not_exist.$F4.bgeo.sc")
ab = geo.createNode("file", "absolute_read"); ab.parm("file").set("D:/somewhere/hardcoded.bgeo.sc")
mrg.setInput(2, rd); mrg.setInput(3, ab)

geo.layoutChildren()
os.makedirs(ROOT + "/tests/example", exist_ok=True)
hou.hipFile.save(ROOT + "/tests/example/hipcheck_example.hip")

# Move the network editor into this layer (GUI only; hython has no hou.ui)
if hasattr(hou, "ui"):
    for pane in hou.ui.paneTabs():
        if pane.type() == hou.paneTabType.NetworkEditor:
            pane.setPwd(geo)
            break

import importlib, hipcheck.scan as s
importlib.reload(s)
r = s.scan_layer(geo)
for g in r["groups"]:
    print(g["status"], [p.split("/")[-1] for p in g["node_paths"]])
for c in s.check_hip():
    print("CHECK", c.get("kind"), c.get("node_path"), c.get("parm_name"))
