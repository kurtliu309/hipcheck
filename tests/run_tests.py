"""hython tests for hipcheck.

Run:
    "D:/Program Files/Side Effects Software/Houdini 21.0.512/bin/hython.exe" tests/run_tests.py

The last line is ``ALL PASS n/n`` or ``FAIL k/n``.
"""

import os
import py_compile
import shutil
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

import hou  # noqa: E402

from hipcheck import actions, scan  # noqa: E402

TMP = tempfile.mkdtemp(prefix="hipcheck_tests_")
_APP = None


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def _clear_flags(node):
    for flag in (hou.nodeFlag.Display, hou.nodeFlag.Render,
                 hou.nodeFlag.Template, hou.nodeFlag.Footprint):
        try:
            node.setGenericFlag(flag, False)
        except Exception:
            pass


def new_scene():
    hou.hipFile.clear(suppress_save_prompt=True)
    try:
        hou.playbar.setFrameRange(1, 240)
    except Exception:
        pass
    try:
        hou.setFrame(1)
    except Exception:
        pass
    geo = hou.node("/obj").createNode("geo", "geo1")
    _clear_flags(geo)
    # A SOP network needs at least one displayed node, otherwise Houdini
    # promotes another node. This input-less sentinel lets the nodes under
    # test really have no flags.
    geo.createNode("null", "out_display_sink", run_init_scripts=False)
    return geo


def mk(parent, type_name, name, inputs=()):
    node = parent.createNode(type_name, name, run_init_scripts=False)
    for index, input_node in enumerate(inputs):
        node.setInput(index, input_node)
    _clear_flags(node)
    return node


def group_paths(result):
    paths = set()
    for group in result.get("groups", []):
        paths.update(group.get("node_paths", ()))
    return paths


def status_of(result, path):
    for group in result.get("groups", []):
        if path in group.get("node_paths", ()):
            return group.get("status")
    return None


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def assert_equal(actual, expected, message):
    if actual != expected:
        raise AssertionError("%s: expected %r, got %r"
                             % (message, expected, actual))


def close_color(a, b, tolerance=1e-4):
    rgb_a, rgb_b = a.rgb(), b.rgb()
    return all(abs(rgb_a[i] - rgb_b[i]) <= tolerance for i in range(3))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_trunk():
    """1. box -> xform -> OUT_null (OUT has no display flag), endpoints by name."""
    geo = new_scene()
    box = mk(geo, "box", "box1")
    xform = mk(geo, "xform", "xform1", [box])
    out = mk(geo, "null", "OUT_main", [xform])

    result = scan.scan_layer(geo)
    assert_true(result["supported"], "a SOP layer should be supported")
    assert_equal(result["groups"], [], "trunk nodes must not be in cleaning groups")
    for node in (box, xform, out):
        assert_true(node.path() not in group_paths(result),
                    "trunk node %s was wrongly flagged" % node.path())


def test_floating_chain():
    """2. A floating chain (head has no input) -> floating, one group."""
    geo = new_scene()
    head = mk(geo, "null", "float_head")
    mid = mk(geo, "xform", "float_mid", [head])
    tail = mk(geo, "null", "float_tail", [mid])

    result = scan.scan_layer(geo)
    assert_equal(len(result["groups"]), 1, "the floating chain should be one group")
    group = result["groups"][0]
    assert_equal(group["status"], "floating",
                 "a chain without inputs should be floating")
    assert_equal(set(group["node_paths"]),
                 {head.path(), mid.path(), tail.path()},
                 "wrong nodes in the floating group")


def test_unused_branch():
    """3. A dangling chain branching off the trunk -> unused_branch."""
    geo = new_scene()
    box = mk(geo, "box", "box1")
    xform = mk(geo, "xform", "xform1", [box])
    out = mk(geo, "null", "OUT_main", [xform])
    branch1 = mk(geo, "xform", "branch1", [xform])
    branch2 = mk(geo, "null", "branch2", [branch1])

    result = scan.scan_layer(geo)
    assert_equal(len(result["groups"]), 1, "the dangling branch should be one group")
    assert_equal(result["groups"][0]["status"], "unused_branch",
                 "a chain branching off the trunk should be an unused branch")
    assert_equal(set(result["groups"][0]["node_paths"]),
                 {branch1.path(), branch2.path()},
                 "wrong nodes in the branch group")
    assert_true(out.path() not in group_paths(result), "OUT was wrongly flagged")


def test_switch_and_bypass():
    """4. Unselected Switch inputs and upstream of bypassed nodes are kept."""
    geo = new_scene()
    box_a = mk(geo, "box", "boxA")
    box_b = mk(geo, "box", "boxB")
    switch = mk(geo, "switch", "switch1", [box_a, box_b])
    if switch.parm("input") is not None:
        switch.parm("input").set(0)
    out_sw = mk(geo, "null", "OUT_switch", [switch])

    box_c = mk(geo, "box", "boxC")
    bypassed = mk(geo, "xform", "bypass_xform", [box_c])
    bypassed.setGenericFlag(hou.nodeFlag.Bypass, True)
    out_byp = mk(geo, "null", "OUT_bypass", [bypassed])

    result = scan.scan_layer(geo)
    assert_equal(result["groups"], [],
                 "unselected Switch inputs and bypass upstream must be kept")
    for node in (box_a, box_b, switch, out_sw, box_c, bypassed, out_byp):
        assert_true(node.path() not in group_paths(result),
                    "%s was wrongly flagged as cleanable" % node.path())


def test_write_nodes_kept():
    """5. Dangling filecache / rop_geometry -> kept, with their upstream."""
    geo = new_scene()
    fc_input = mk(geo, "box", "fc_input")
    filecache = mk(geo, "filecache", "filecache1", [fc_input])
    rop_input = mk(geo, "box", "rop_input")
    rop = mk(geo, "rop_geometry", "rop_geometry1", [rop_input])

    result = scan.scan_layer(geo)
    assert_equal(result["groups"], [],
                 "file-writing nodes and their upstream must be kept")
    for node in (fc_input, filecache, rop_input, rop):
        assert_true(node.path() not in group_paths(result),
                    "%s was wrongly flagged as cleanable" % node.path())


def test_flags_and_comment_kept():
    """6. Dangling but display/render/template/footprint, lock, or comment -> kept."""
    geo = new_scene()
    display_node = mk(geo, "null", "display_keep")
    display_node.setGenericFlag(hou.nodeFlag.Display, True)
    render_node = mk(geo, "null", "render_keep")
    render_node.setGenericFlag(hou.nodeFlag.Render, True)
    template_node = mk(geo, "null", "template_keep")
    template_node.setGenericFlag(hou.nodeFlag.Template, True)
    footprint_node = mk(geo, "null", "footprint_keep")
    footprint_node.setGenericFlag(hou.nodeFlag.Footprint, True)
    lock_node = mk(geo, "null", "lock_keep")
    lock_node.setGenericFlag(hou.nodeFlag.Lock, True)
    softlock_node = mk(geo, "null", "softlock_keep")
    softlock_node.setGenericFlag(hou.nodeFlag.SoftLock, True)
    comment_node = mk(geo, "null", "comment_keep")
    comment_node.setComment("keep this chain")

    result = scan.scan_layer(geo)
    assert_equal(result["groups"], [],
                 "nodes with flags or comments must be kept")
    for node in (display_node, render_node, template_node, footprint_node,
                 lock_node, softlock_node, comment_node):
        assert_true(node.path() not in group_paths(result),
                    "%s was wrongly flagged as cleanable" % node.path())


def test_referenced_nodes_kept():
    """7. Nodes referenced by ch(), object_merge, or wrangle op: are kept."""
    geo = new_scene()

    ref_channel = mk(geo, "xform", "ref_channel")
    holder = mk(geo, "xform", "holder")
    holder.setComment("references holder")
    holder.parm("tx").setExpression('ch("../ref_channel/tx")')

    ref_objmerge = mk(geo, "null", "ref_objmerge")
    obj_merge = mk(geo, "object_merge", "object_merge1")
    obj_merge.parm("objpath1").set(ref_objmerge.path())

    ref_wrangle = mk(geo, "null", "ref_wrangle")
    wrangle = mk(geo, "attribwrangle", "wrangle1")
    wrangle.parm("snippet").set(
        'int a = op:`%s`;' % ref_wrangle.path())

    ref_cross = mk(geo, "xform", "ref_cross")
    other_geo = hou.node("/obj").createNode("geo", "geo2")
    _clear_flags(other_geo)
    cross_holder = mk(other_geo, "xform", "cross_holder")
    cross_holder.parm("tx").setExpression(
        'ch("../../geo1/ref_cross/tx")')

    result = scan.scan_layer(geo)
    all_grouped = group_paths(result)
    for node in (ref_channel, ref_objmerge, ref_wrangle, ref_cross):
        assert_true(node.path() not in all_grouped,
                    "%s is referenced and must be kept" % node.path())
    # The referencing nodes themselves are floating and should still be
    # reported, so the test does not keep the whole layer alive.
    assert_true(obj_merge.path() in all_grouped,
                "object_merge itself should be reported as floating")
    assert_true(wrangle.path() in all_grouped,
                "wrangle itself should be reported as floating")


def test_layout_name_not_endpoint():
    """8. A node named layout1 is not an endpoint (only names starting with out)."""
    geo = new_scene()
    layout = mk(geo, "null", "layout1")

    result = scan.scan_layer(geo)
    assert_equal(len(result["groups"]), 1, "layout1 should be floating")
    assert_equal(result["groups"][0]["status"], "floating",
                 "layout1 must not be an endpoint just because of its name")
    assert_equal(result["groups"][0]["node_paths"], [layout.path()],
                 "wrong group for layout1")


def test_path_checks():
    """9. Broken read paths and hardcoded absolute paths."""
    new_scene()
    hip_dir = hou.text.expandString("$HIP")
    try:
        os.makedirs(hip_dir, exist_ok=True)
    except Exception:
        pass
    created = []

    def touch(name):
        path = os.path.join(hip_dir, name)
        with open(path, "w") as handle:
            handle.write("x")
        created.append(path)
        return path

    missing = os.path.join(hip_dir, "hipcheck_missing_12345.bgeo")
    if os.path.exists(missing):
        os.remove(missing)

    broken = mk(hou.node("/obj/geo1"), "file", "read_broken")
    broken.parm("filemode").set("read")
    broken.parm("file").set("$HIP/hipcheck_missing_12345.bgeo")

    partial = mk(hou.node("/obj/geo1"), "file", "read_frames")
    partial.parm("filemode").set("read")
    partial.parm("file").set("$HIP/hipcheck_frames_$F4.bgeo")
    touch("hipcheck_frames_0001.bgeo")
    hou.playbar.setFrameRange(1, 10)
    hou.setFrame(5)

    writer = mk(hou.node("/obj/geo1"), "file", "write_path")
    writer.parm("filemode").set("write")
    writer.parm("file").set("$HIP/hipcheck_write_missing.bgeo")

    absolute = mk(hou.node("/obj/geo1"), "file", "read_abs")
    absolute.parm("filemode").set("read")
    absolute.parm("file").set("D:/hipcheck_missing_abc.bgeo")

    variable = mk(hou.node("/obj/geo1"), "file", "read_var")
    variable.parm("filemode").set("read")
    variable.parm("file").set("$HIP/hipcheck_existing.bgeo")
    touch("hipcheck_existing.bgeo")

    issues = scan.check_hip()
    kinds = {}
    for issue in issues:
        for key in ("kind", "node_path", "parm_name", "reason"):
            assert_true(key in issue, "issue is missing field %s" % key)
        kinds.setdefault(issue["node_path"], set()).add(issue["kind"])

    assert_true("broken_path" in kinds.get(broken.path(), set()),
                "a missing read path should be reported as broken")
    assert_true("broken_path" not in kinds.get(partial.path(), set()),
                "a sequence with one existing frame must not be broken")
    assert_true("broken_path" not in kinds.get(writer.path(), set()),
                "write paths must not be checked for broken links")
    assert_true("absolute_path" in kinds.get(absolute.path(), set()),
                "D:/... should be reported as an absolute path")
    assert_true("absolute_path" not in kinds.get(variable.path(), set()),
                "$HIP/... must not be reported as an absolute path")
    assert_true("broken_path" not in kinds.get(variable.path(), set()),
                "an existing $HIP path must not be reported as broken")
    assert_true("/stage" not in kinds and "/tasks" not in kinds,
                "manager-network tool paths must not be checked as user files")

    for path in created:
        try:
            os.remove(path)
        except Exception:
            pass


def test_check_default_nodes():
    """20. Default camera/material/ROP, write paths and relative paths stay quiet."""
    new_scene()
    cam = hou.node("/obj").createNode("cam", "check_cam")  # init script: file1 = defcam.bgeo
    assert_true(cam.node("file1") is not None,
                "precondition failed: a default camera should have a geo File SOP")
    principled = hou.node("/mat").createNode("principledshader", "check_principled")
    principled.cook(force=True)
    texture = hou.node("/mat").createNode("texture", "check_texture")
    texture.cook(force=True)
    mantra = hou.node("/out").createNode("ifd", "check_mantra")
    karma = hou.node("/out").createNode("karma", "check_karma")
    # A user-set output path on a driver is a write path; it need not exist yet.
    mantra.parm("vm_picture").set("$HIP/render/hipcheck_missing_$F4.exr")
    karma.parm("picture").set("$HIP/render/hipcheck_missing_$F4.exr")
    geo = hou.node("/obj/geo1")
    rop_sop = geo.createNode("rop_geometry", "check_rop_geo")
    rop_sop.parm("sopoutput").set("$HIP/geo/hipcheck_missing_output.bgeo")

    assert_equal(scan.check_hip(), [],
                 "default nodes and write paths must not be reported")

    # Houdini resolves relative paths through its own search paths.
    relative = mk(geo, "file", "check_relative")
    relative.parm("filemode").set("read")
    relative.parm("file").set("hipcheck_missing_relative.bgeo")
    assert_equal(scan.check_hip(), [],
                 "a relative read path must not be reported")

    # A user-set missing read path is still reported.
    broken = mk(geo, "file", "check_broken")
    broken.parm("filemode").set("read")
    broken.parm("file").set("$HIP/hipcheck_missing_12345.bgeo")
    issues = scan.check_hip()
    assert_equal([(issue["node_path"], issue["parm_name"], issue["kind"])
                  for issue in issues],
                 [(broken.path(), "file", "broken_path")],
                 "a user-set missing read path must still be reported")
    assert_equal(
        issues[0]["reason"],
        "File not found: %s"
        % hou.text.expandString("$HIP/hipcheck_missing_12345.bgeo"),
        "wrong broken-path wording")


def test_colorize_undo():
    """10. Colorize everything red (undo label) and Ctrl+Z restores the color."""
    geo = new_scene()
    node_a = mk(geo, "null", "color_a")
    node_b = mk(geo, "null", "color_b")
    orig_a, orig_b = node_a.color(), node_b.color()
    path_a, path_b = node_a.path(), node_b.path()

    count = actions.colorize([path_a, path_b])
    assert_equal(count, 2, "wrong number of nodes colored")
    red = hou.Color(*actions.COLOR_RED)
    assert_true(close_color(node_a.color(), red), "node should be red")
    assert_true(close_color(node_b.color(), red), "node should be red")
    assert_true(node_a.userData(actions.IGNORE_KEY) is None,
                "colorize must not mark nodes as ignored")
    labels = hou.undos.undoLabels()
    assert_true(labels and labels[0] == actions.UNDO_PREFIX + "color",
                "colorize undo label must be %r, got %r"
                % (actions.UNDO_PREFIX + "color", labels[:1]))

    hou.undos.performUndo()
    assert_true(close_color(node_a.color(), orig_a),
                "performUndo should revert the colorize")
    assert_true(close_color(node_b.color(), orig_b),
                "performUndo should revert the colorize")


def test_ignore_roundtrip():
    """11. Ignore marks round trip and are undone with Ctrl+Z."""
    geo = new_scene()
    node_a = mk(geo, "null", "ignore_a")
    node_b = mk(geo, "null", "ignore_b")
    path_a, path_b = node_a.path(), node_b.path()

    assert_true(not actions.is_ignored(node_a), "a new node must not be ignored")
    assert_equal(actions.ignore([path_a, path_b, "/obj/does_not_exist"]), 2,
                 "wrong number of nodes marked ignored")
    assert_true(actions.is_ignored(node_a), "node_a should be ignored")
    assert_true(actions.is_ignored(node_b), "node_b should be ignored")
    assert_equal(node_a.userData(actions.IGNORE_KEY), "1",
                 "the ignore mark should be the userData value '1'")
    assert_equal(actions.ignore([path_a]), 0,
                 "an already ignored node must not count again")
    labels = hou.undos.undoLabels()
    assert_true(labels and labels[0] == actions.UNDO_PREFIX + "ignore",
                "ignore undo label must be %r, got %r"
                % (actions.UNDO_PREFIX + "ignore", labels[:1]))

    assert_equal(actions.unignore([path_a]), 1, "wrong number of nodes unmarked")
    assert_true(not actions.is_ignored(node_a), "node_a should no longer be ignored")
    assert_true(actions.is_ignored(node_b), "node_b must keep its mark")
    assert_equal(actions.unignore([path_a]), 0,
                 "an unignored node must not count again")
    labels = hou.undos.undoLabels()
    assert_true(labels and labels[0] == actions.UNDO_PREFIX + "unignore",
                "unignore undo label must be %r, got %r"
                % (actions.UNDO_PREFIX + "unignore", labels[:1]))

    hou.undos.performUndo()
    assert_true(actions.is_ignored(node_a), "Ctrl+Z should undo the unignore")
    hou.undos.performUndo()
    assert_true(not actions.is_ignored(node_a) and not actions.is_ignored(node_b),
                "Ctrl+Z should undo the ignore")


def test_check_hip_ignored():
    """12. check_hip hides ignored nodes by default and flags them on request."""
    geo = new_scene()

    def broken_node(name):
        node = mk(geo, "file", name)
        node.parm("filemode").set("read")
        node.parm("file").set("$HIP/hipcheck_missing_%s.bgeo" % name)
        return node

    ignored_node = broken_node("check_ignored")
    kept_node = broken_node("check_kept")

    issues = scan.check_hip()
    assert_equal({issue["node_path"] for issue in issues},
                 {ignored_node.path(), kept_node.path()},
                 "both broken nodes should be reported")
    assert_true(all(issue["ignored"] is False for issue in issues),
                "nothing is ignored yet, so every issue's ignored flag is False")

    actions.ignore([ignored_node.path()])
    issues = scan.check_hip()
    assert_equal({issue["node_path"] for issue in issues}, {kept_node.path()},
                 "an ignored node must be hidden by default")
    assert_true(all(issue["ignored"] is False for issue in issues),
                "default results carry ignored=False")

    full = scan.check_hip(include_ignored=True)
    assert_equal({issue["node_path"] for issue in full},
                 {ignored_node.path(), kept_node.path()},
                 "include_ignored should bring the ignored node back")
    for issue in full:
        assert_equal(issue["ignored"], issue["node_path"] == ignored_node.path(),
                     "wrong ignored flag on %s" % issue["node_path"])


def test_delete_undo():
    """13. Delete returns the count and Ctrl+Z restores the nodes."""
    geo = new_scene()
    node_a = mk(geo, "null", "delete_a")
    node_b = mk(geo, "null", "delete_b")
    path_a, path_b = node_a.path(), node_b.path()

    assert_equal(actions.delete([path_a, path_b, "/obj/does_not_exist"]), 2,
                 "wrong number of nodes deleted")
    assert_true(hou.node(path_a) is None, "node_a should be deleted")
    assert_true(hou.node(path_b) is None, "node_b should be deleted")
    labels = hou.undos.undoLabels()
    assert_true(labels and labels[0] == actions.UNDO_PREFIX + "delete",
                "delete undo label must be %r, got %r"
                % (actions.UNDO_PREFIX + "delete", labels[:1]))

    hou.undos.performUndo()
    assert_true(hou.node(path_a) is not None, "Ctrl+Z should restore node_a")
    assert_true(hou.node(path_b) is not None, "Ctrl+Z should restore node_b")

    # A node and its upstream are both deleted in one undoable step.
    upstream = mk(geo, "null", "delete_upstream")
    downstream = mk(geo, "null", "delete_downstream", [upstream])
    up_path, down_path = upstream.path(), downstream.path()
    assert_equal(actions.delete([up_path, down_path]), 2,
                 "an upstream and downstream node should both be counted")
    assert_true(hou.node(up_path) is None, "the upstream node should be gone")
    assert_true(hou.node(down_path) is None, "the downstream node should be gone")
    hou.undos.performUndo()
    assert_true(hou.node(up_path) is not None, "the upstream node should be back")
    assert_true(hou.node(down_path) is not None, "the downstream node should be back")


def test_scan_layer_ignored():
    """14. scan_layer hides ignored nodes by default and flags them on request."""
    geo = new_scene()
    head = mk(geo, "null", "ig_head")
    mid = mk(geo, "xform", "ig_mid", [head])
    tail = mk(geo, "null", "ig_tail", [mid])
    solo = mk(geo, "null", "ig_solo")
    actions.ignore([head.path(), solo.path()])

    result = scan.scan_layer(geo)
    assert_equal(len(result["groups"]), 1,
                 "the fully ignored group must be dropped")
    group = result["groups"][0]
    assert_equal(set(group["node_paths"]), {mid.path(), tail.path()},
                 "ignored nodes must be hidden by default")
    assert_equal(group["ignored_paths"], [],
                 "ignored_paths is empty by default")

    full = scan.scan_layer(geo, include_ignored=True)
    assert_equal(len(full["groups"]), 2,
                 "include_ignored should keep both groups")
    chain_group = next(
        group for group in full["groups"] if mid.path() in group["node_paths"])
    assert_equal(set(chain_group["node_paths"]),
                 {head.path(), mid.path(), tail.path()},
                 "ignore marks must not change the grouping")
    assert_equal(chain_group["ignored_paths"], [head.path()],
                 "the ignored subset must be reported")
    solo_group = next(
        group for group in full["groups"] if solo.path() in group["node_paths"])
    assert_equal(solo_group["ignored_paths"], [solo.path()],
                 "a fully ignored group reports all its paths")

    # Ignore marks are applied after the analysis: an ignored endpoint still
    # keeps its upstream useful.
    geo = new_scene()
    box = mk(geo, "box", "ig_box")
    out = mk(geo, "null", "OUT_ignored", [box])
    actions.ignore([out.path()])
    assert_equal(scan.scan_layer(geo)["groups"], [],
                 "an ignored endpoint must still keep its upstream")


def test_unsupported_layers():
    """12. Non-SOP layers report 'unsupported' with a reason."""
    new_scene()
    for path in ("/obj", "/out"):
        node = hou.node(path)
        assert_true(node is not None, "%s should exist" % path)
        result = scan.scan_layer(node)
        assert_true(not result["supported"], "%s must not be cleanable" % path)
        assert_true(bool(result.get("reason")), "%s needs a reason" % path)
        assert_equal(result["groups"], [], "unsupported layers have no groups")


def test_select_in_layer():
    """13. The selection helper selects only nodes whose parent is the given layer."""
    geo = new_scene()
    node_a = mk(geo, "null", "select_a")
    node_b = mk(geo, "null", "select_b")
    other_geo = hou.node("/obj").createNode("geo", "geo2")
    _clear_flags(other_geo)
    node_c = mk(other_geo, "null", "select_c")

    import hipcheck.ui as ui  # noqa: E402

    # A pre-existing selection is cleared, and other layers are untouched.
    node_c.setSelected(True)
    count = ui._select_in_layer(
        [node_a.path(), node_b.path(), node_c.path()], geo)
    assert_equal(count, 2, "only nodes in the given layer should be selected")
    selected = {node.path() for node in hou.selectedNodes()}
    assert_equal(selected, {node_a.path(), node_b.path()},
                 "wrong nodes selected for the layer")

    # A layer given as a path string behaves the same.
    count = ui._select_in_layer([node_a.path(), node_c.path()], other_geo.path())
    assert_equal(count, 1, "layer path string should work")
    selected = {node.path() for node in hou.selectedNodes()}
    assert_equal(selected, {node_c.path()}, "wrong nodes selected for the layer")

    # No matching node: the Houdini selection is left untouched.
    node_a.setSelected(True, clear_all_selected=True)
    count = ui._select_in_layer([node_c.path()], geo)
    assert_equal(count, 0, "a path from another layer should select nothing")
    selected = {node.path() for node in hou.selectedNodes()}
    assert_equal(selected, {node_a.path()},
                 "a non-matching selection must not clear the Houdini selection")


def test_delete_revalidation():
    """18. A node that became used after the scan is dropped before deleting."""
    geo = new_scene()
    box = mk(geo, "box", "box1")
    xform = mk(geo, "xform", "xform1", [box])
    merge = mk(geo, "merge", "merge1", [xform])
    mk(geo, "null", "OUT_main", [merge])
    stray = mk(geo, "null", "stray")
    stale = mk(geo, "null", "stale")

    import hipcheck.ui as ui  # noqa: E402

    paths = [stray.path(), stale.path()]
    _, kept = ui._unused_paths(paths, geo)
    assert_equal(set(kept), set(paths),
                 "both unused nodes should survive re-validation")

    # The stale node becomes useful after the list was built.
    merge.setInput(1, stale)
    _, kept = ui._unused_paths(paths, geo)
    assert_equal(kept, [stray.path()],
                 "a node that became used must be dropped before deleting")


def test_ui():
    """15. ui.py compiles; the window builds; select all buttons; jump cells."""
    package_dir = os.path.join(ROOT, "python", "hipcheck")
    for name in sorted(os.listdir(package_dir)):
        if name.endswith(".py"):
            py_compile.compile(os.path.join(package_dir, name), doraise=True)

    import hipcheck.ui as ui  # noqa: E402

    global _APP
    from hutil.Qt import QtWidgets, QtCore  # noqa: E402
    _APP = QtWidgets.QApplication.instance()
    if _APP is None:
        _APP = QtWidgets.QApplication([])

    def has_jump(item, column):
        """Rows with a jump button carry ui._ROLE_JUMP on the jump column."""
        return bool(item.data(column, ui._ROLE_JUMP))

    geo = new_scene()
    floating = mk(geo, "null", "ui_floating")
    floating2 = mk(geo, "null", "ui_floating_2")
    hou.cd(geo.path())  # hython has no network editor; pwd stands in for the layer

    window = ui.show()
    assert_true(window is not None, "ui.show() should return a window")
    assert_true(isinstance(window, QtWidgets.QDialog), "the window should be a QDialog")

    check_tree = window._check_tree
    clean_tree = window._clean_tree
    for tree in (check_tree, clean_tree):
        assert_equal(tree.selectionMode(),
                     QtWidgets.QAbstractItemView.ExtendedSelection,
                     "both trees must allow multi-selection")

    assert_equal(check_tree.columnCount(), 5, "check tree needs 5 columns")
    assert_true(isinstance(check_tree.itemDelegateForColumn(4), ui._JumpDelegate),
                "check tree needs a jump-button column")
    assert_equal(clean_tree.columnCount(), 4, "clean tree needs 4 columns")
    assert_true(isinstance(clean_tree.itemDelegateForColumn(3), ui._JumpDelegate),
                "clean tree needs a jump-button column")

    assert_true(clean_tree.topLevelItemCount() >= 1,
                "clean list should show groups")
    group = None
    for index in range(clean_tree.topLevelItemCount()):
        candidate = clean_tree.topLevelItem(index)
        if candidate.text(0) == "Floating":
            group = candidate
            break
    assert_true(group is not None, "a floating group should be listed")
    assert_true(group.data(0, QtCore.Qt.CheckStateRole) is None,
                "clean group rows must not have checkboxes")
    assert_true(not group.isExpanded(), "Floating should start collapsed")
    assert_equal(group.childCount(), 2, "two floating chains -> two chain rows")
    assert_equal(group.text(1), "2", "the status row counts all its nodes")
    chain = group.child(0)
    assert_equal(chain.childCount(), 1, "each chain row holds its node")
    child = chain.child(0)
    assert_true(has_jump(group, 3), "group rows need a jump cell")
    assert_true(has_jump(child, 3), "node rows need a jump cell")
    assert_true(child.data(0, QtCore.Qt.UserRole) in (floating.path(), floating2.path()),
                "node rows should carry their node path")
    assert_true(child.data(0, QtCore.Qt.CheckStateRole) is None,
                "clean node rows must not have checkboxes")

    # Select All is a plain button above each tree; one click selects every row.
    for button in (window._check_all, window._clean_all):
        assert_true(isinstance(button, QtWidgets.QPushButton),
                    "Select All must be a QPushButton, not a checkbox")
        assert_equal(button.text(), "Select All", "wrong Select All button text")
    window._clean_all.click()
    assert_equal(set(window._selected_paths(clean_tree)),
                 {floating.path(), floating2.path()},
                 "Select All should stand for every clean node")
    window._check_all.click()
    assert_equal(len(clean_tree.selectedItems()), 0,
                 "Select All in the other tree should clear this tree")

    # Only the jump column triggers a jump; a group row jumps to all its nodes.
    hou.clearAllSelected()
    window._on_tree_clicked(clean_tree, child, 0)
    assert_equal(len(hou.selectedNodes()), 0,
                 "clicking a non-jump column must not jump")
    window._on_tree_clicked(clean_tree, child, 3)
    assert_true(hou.node(child.data(0, QtCore.Qt.UserRole)).isSelected(),
                "the jump cell should select its node")

    # A group row jumps to all its nodes.
    hou.clearAllSelected()
    window._on_tree_clicked(clean_tree, group, 3)
    assert_equal({node.path() for node in hou.selectedNodes()},
                 set(group.data(0, QtCore.Qt.UserRole + 1)["node_paths"]),
                 "the group jump cell should select every node of the group")

    # The jump helper takes a list; the single-node jump is the 1-element case.
    assert_true(ui._jump_to([floating.path(), floating2.path()]),
                "a jump to existing nodes should succeed")
    assert_equal({node.path() for node in hou.selectedNodes()},
                 {floating.path(), floating2.path()},
                 "the jump helper should select every node it is given")
    assert_true(not ui._jump_to(["/obj/does_not_exist"]),
                "a jump to a missing node should fail")

    assert_true(window._delete_btn.isEnabled(),
                "delete is enabled whenever the Clean list has rows")

    # Ignore: the button flips to Unignore when everything selected is ignored;
    # ignored nodes vanish unless Show Ignored is on.
    clean_tree.clearSelection()
    group.setSelected(True)
    assert_equal(window._ignore_btn.text(), "Ignore Selected", "ignore label")
    window._toggle_ignore()
    assert_equal(window._clean_tree.topLevelItemCount(), 0,
                 "ignored nodes are hidden by default")
    window._show_ignored.setChecked(True)
    assert_true(window._clean_tree.topLevelItemCount() == 1,
                "Show Ignored lists them again")
    window._clean_all.click()
    assert_equal(window._ignore_btn.text(), "Unignore Selected",
                 "all-ignored selection offers Unignore")
    window._toggle_ignore()
    assert_true(not actions.is_ignored(hou.node(floating.path())),
                "Unignore clears the mark")
    window._show_ignored.setChecked(False)
    assert_true(ui.show() is window, "a second show() should reuse the window")
    window.close()
    assert_true(ui._get_window() is None, "closing should clear the singleton")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _save_and_reload(name):
    path = os.path.join(tempfile.mkdtemp(prefix="hipcheck_"), name).replace("\\", "/")
    hou.hipFile.save(path)
    hou.hipFile.load(path, suppress_save_prompt=True, ignore_load_warnings=True)
    return path


def test_hda_self_reference_not_kept():
    """16. An HDA (e.g. H21's Color SOP) referencing its own parms is not externally referenced."""
    geo = new_scene()
    box = mk(geo, "box", "box1")
    mk(geo, "null", "OUT_main", [box])
    color = geo.createNode("color", "dead_color")  # normal init, with HDA internals
    color.setInput(0, box)
    geo_path = geo.path()
    _save_and_reload("hda_self_ref.hip")
    geo = hou.node(geo_path)
    geo.node("dead_color").cook(force=True)  # make internal references appear
    assert_true(any(d.path().startswith(geo_path + "/dead_color/")
                    for d in geo.node("dead_color").dependents()),
                "precondition failed: Color SOP has no internal self reference")
    result = scan.scan_layer(geo)
    assert_equal(status_of(result, geo_path + "/dead_color"), "unused_branch",
                 "an HDA self reference was wrongly treated as external")


def test_check_false_positives():
    """17. Locked HDA internals and factory-default file parms (scatter default.pic) are not reported."""
    geo = new_scene()
    box = mk(geo, "box", "box1")
    sc = geo.createNode("scatter", "sc"); sc.setInput(0, box)
    fc = geo.createNode("filecache::2.0", "fc"); fc.setInput(0, sc)
    geo_path = geo.path()
    _save_and_reload("check_fp.hip")
    bad = [r for r in scan.check_hip()
           if r["node_path"].startswith(geo_path + "/fc/")
           or (r["node_path"] == geo_path + "/sc"
               and r["parm_name"] == "densitytexture")]
    assert_equal(bad, [], "check reported false positives")


TESTS = [
    ("hda_self_reference_not_kept", test_hda_self_reference_not_kept),
    ("check_false_positives", test_check_false_positives),
    ("trunk", test_trunk),
    ("floating_chain", test_floating_chain),
    ("unused_branch", test_unused_branch),
    ("switch_and_bypass", test_switch_and_bypass),
    ("write_nodes_kept", test_write_nodes_kept),
    ("flags_and_comment_kept", test_flags_and_comment_kept),
    ("referenced_nodes_kept", test_referenced_nodes_kept),
    ("layout_name_not_endpoint", test_layout_name_not_endpoint),
    ("path_checks", test_path_checks),
    ("check_default_nodes", test_check_default_nodes),
    ("colorize_undo", test_colorize_undo),
    ("ignore_roundtrip", test_ignore_roundtrip),
    ("check_hip_ignored", test_check_hip_ignored),
    ("delete_undo", test_delete_undo),
    ("scan_layer_ignored", test_scan_layer_ignored),
    ("unsupported_layers", test_unsupported_layers),
    ("select_in_layer", test_select_in_layer),
    ("delete_revalidation", test_delete_revalidation),
    ("ui", test_ui),
]


def main():
    passed = 0
    try:
        for name, test in TESTS:
            try:
                test()
                print("PASS %s" % name)
                passed += 1
            except Exception:
                print("FAIL %s" % name)
                traceback.print_exc()
    finally:
        try:
            shutil.rmtree(TMP, ignore_errors=True)
        except Exception:
            pass

    total = len(TESTS)
    if passed == total:
        print("ALL PASS %d/%d" % (passed, total))
        return 0
    print("FAIL %d/%d" % (total - passed, total))
    return 1


if __name__ == "__main__":
    sys.exit(main())
