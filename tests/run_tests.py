"""hipcheck 的 hython 测试。

运行：
    "D:/Program Files/Side Effects Software/Houdini 21.0.512/bin/hython.exe" tests/run_tests.py

最后一行是 ``ALL PASS n/n`` 或 ``FAIL k/n``。
"""

import os
import py_compile
import shutil
import sys
import tempfile
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "python"))

import hou  # noqa: E402

from hipcheck import actions, scan  # noqa: E402

TMP = tempfile.mkdtemp(prefix="hipcheck_tests_")
_APP = None


# ---------------------------------------------------------------------------
# 场景小工具
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
    # SOP 网络至少得有一个显示节点，否则 Houdini 会自动把别的节点顶上去。
    # 放一个没有输入的哨兵节点，让测试里要观察的节点可以真的“无 flag”。
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
# 测试
# ---------------------------------------------------------------------------

def test_trunk():
    """1. box→xform→OUT_null（OUT 不开显示 flag），终点按名字识别。"""
    geo = new_scene()
    box = mk(geo, "box", "box1")
    xform = mk(geo, "xform", "xform1", [box])
    out = mk(geo, "null", "OUT_main", [xform])

    result = scan.scan_layer(geo)
    assert_true(result["supported"], "SOP 层应支持清理")
    assert_equal(result["groups"], [], "主干节点不应出现在清理分组里")
    for node in (box, xform, out):
        assert_true(node.path() not in group_paths(result), "主干节点被误判")


def test_floating_chain():
    """2. 漂浮一串（头没有输入）→ floating，一组。"""
    geo = new_scene()
    head = mk(geo, "null", "float_head")
    mid = mk(geo, "xform", "float_mid", [head])
    tail = mk(geo, "null", "float_tail", [mid])

    result = scan.scan_layer(geo)
    assert_equal(len(result["groups"]), 1, "漂浮链应合成一组")
    group = result["groups"][0]
    assert_equal(group["status"], "floating", "无输入的整串应判为漂浮")
    assert_equal(set(group["node_paths"]),
                 {head.path(), mid.path(), tail.path()}, "漂浮组节点不对")


def test_unused_branch():
    """3. 从主干接出来悬空的一串 → unused_branch。"""
    geo = new_scene()
    box = mk(geo, "box", "box1")
    xform = mk(geo, "xform", "xform1", [box])
    out = mk(geo, "null", "OUT_main", [xform])
    branch1 = mk(geo, "xform", "branch1", [xform])
    branch2 = mk(geo, "null", "branch2", [branch1])

    result = scan.scan_layer(geo)
    assert_equal(len(result["groups"]), 1, "悬空分支应合成一组")
    assert_equal(result["groups"][0]["status"], "unused_branch",
                 "从主干接出来的一串应判为没用分支")
    assert_equal(set(result["groups"][0]["node_paths"]),
                 {branch1.path(), branch2.path()}, "分支组节点不对")
    assert_true(out.path() not in group_paths(result), "OUT 被误判")


def test_switch_and_bypass():
    """4. Switch 未选中的输入保留；经过 bypass 节点连到终点的上游保留。"""
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
    assert_equal(result["groups"], [], "Switch 未选输入和 bypass 上游都应保留")
    for node in (box_a, box_b, switch, out_sw, box_c, bypassed, out_byp):
        assert_true(node.path() not in group_paths(result),
                    "%s 被误判为可清理" % node.path())


def test_write_nodes_kept():
    """5. 悬空但是 filecache / rop_geometry → 保留，连同上游。"""
    geo = new_scene()
    fc_input = mk(geo, "box", "fc_input")
    filecache = mk(geo, "filecache", "filecache1", [fc_input])
    rop_input = mk(geo, "box", "rop_input")
    rop = mk(geo, "rop_geometry", "rop_geometry1", [rop_input])

    result = scan.scan_layer(geo)
    assert_equal(result["groups"], [], "写文件节点及其上游都应保留")
    for node in (fc_input, filecache, rop_input, rop):
        assert_true(node.path() not in group_paths(result),
                    "%s 被误判为可清理" % node.path())


def test_flags_and_comment_kept():
    """6. 悬空但 display/render/template/footprint、lock、有 comment → 保留。"""
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
    comment_node.setComment("这一串留着")

    result = scan.scan_layer(geo)
    assert_equal(result["groups"], [], "带 flag/注释的节点都应保留")
    for node in (display_node, render_node, template_node, footprint_node,
                 lock_node, softlock_node, comment_node):
        assert_true(node.path() not in group_paths(result),
                    "%s 被误判为可清理" % node.path())


def test_referenced_nodes_kept():
    """7. 被 ch()、object_merge、wrangle op: 引用的节点保留。"""
    geo = new_scene()

    ref_channel = mk(geo, "xform", "ref_channel")
    holder = mk(geo, "xform", "holder")
    holder.setComment("引用 holder")
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
                    "%s 被引用，应保留" % node.path())
    # 引用者自己是漂浮的，仍然应该被清理（避免测试把整层都保下来）。
    assert_true(obj_merge.path() in all_grouped, "object_merge 本身应被报成漂浮")
    assert_true(wrangle.path() in all_grouped, "wrangle 本身应被报成漂浮")


def test_layout_name_not_endpoint():
    """8. 名字 layout1 不算终点（只认 out 开头）。"""
    geo = new_scene()
    layout = mk(geo, "null", "layout1")

    result = scan.scan_layer(geo)
    assert_equal(len(result["groups"]), 1, "layout1 应被当成漂浮")
    assert_equal(result["groups"][0]["status"], "floating",
                 "layout1 不该因为名字被当成终点")
    assert_equal(result["groups"][0]["node_paths"], [layout.path()],
                 "layout1 分组不对")


def test_path_checks():
    """9. 路径断链 / 绝对路径的判断。"""
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
            assert_true(key in issue, "检查结果缺少字段 %s" % key)
        kinds.setdefault(issue["node_path"], set()).add(issue["kind"])

    assert_true("broken_path" in kinds.get(broken.path(), set()),
                "不存在的读路径应报断链")
    assert_true("broken_path" not in kinds.get(partial.path(), set()),
                "首尾帧有一帧存在就不该报断链")
    assert_true("broken_path" not in kinds.get(writer.path(), set()),
                "写出路径不该查断链")
    assert_true("absolute_path" in kinds.get(absolute.path(), set()),
                "D:/... 原文应报绝对路径")
    assert_true("absolute_path" not in kinds.get(variable.path(), set()),
                "$HIP/... 不该报绝对路径")
    assert_true("broken_path" not in kinds.get(variable.path(), set()),
                "存在的 $HIP 路径不该报断链")
    assert_true("/stage" not in kinds and "/tasks" not in kinds,
                "Manager 网络的工具路径不该被当成用户文件检查")

    for path in created:
        try:
            os.remove(path)
        except Exception:
            pass


def test_colorize_restore_undo():
    """10. 上色/恢复，以及撤销。"""
    geo = new_scene()
    node_a = mk(geo, "null", "color_a")
    node_b = mk(geo, "null", "color_b")
    orig_a, orig_b = node_a.color(), node_b.color()

    groups = [{"status": "floating",
               "node_paths": [node_a.path(), node_b.path()]}]
    count = actions.colorize(groups)
    assert_equal(count, 2, "上色节点数不对")
    purple = hou.Color(*scan.COLOR_FLOATING)
    assert_true(close_color(node_a.color(), purple), "漂浮节点应为紫色")
    assert_true(node_a.userData(actions.ORIG_COLOR_KEY) is not None,
                "上色前应记录原颜色")

    path_a, path_b = node_a.path(), node_b.path()
    restored = actions.restore_colors(paths=[path_a, path_b])
    assert_equal(restored, 2, "恢复节点数不对")
    assert_true(close_color(node_a.color(), orig_a), "颜色应恢复原值")
    assert_true(close_color(node_b.color(), orig_b), "颜色应恢复原值")
    assert_true(node_a.userData(actions.ORIG_COLOR_KEY) is None,
                "恢复后应清掉 userData")
    assert_true(node_a.isGenericFlagSet(hou.nodeFlag.ColorDefault),
                "原本默认色的节点恢复后应是默认色")

    actions.colorize([{"status": "unused_branch",
                       "node_paths": [path_a, path_b]}])
    yellow = hou.Color(*scan.COLOR_UNUSED_BRANCH)
    assert_true(close_color(node_a.color(), yellow), "没用分支应为黄色")
    hou.undos.performUndo()
    assert_true(close_color(node_a.color(), orig_a),
                "performUndo 应撤回上色")
    assert_true(close_color(node_b.color(), orig_b),
                "performUndo 应撤回上色")

    # 存盘再开，userData 记录还在，仍能恢复。
    actions.colorize([{"status": "floating", "node_paths": [path_a]}])
    scene = os.path.join(TMP, "color_persist.hip")
    hou.hipFile.save(file_name=scene)
    hou.hipFile.load(scene, suppress_save_prompt=True)
    reloaded = hou.node(path_a)
    assert_true(reloaded is not None, "重新载入后节点应还在")
    assert_true(reloaded.userData(actions.ORIG_COLOR_KEY) is not None,
                "存盘再开后原色记录应还在")
    actions.restore_colors(paths=[path_a])
    assert_true(close_color(reloaded.color(), orig_a),
                "存盘再开后应能恢复原色")
    assert_true(reloaded.userData(actions.ORIG_COLOR_KEY) is None,
                "恢复后应清掉 userData")


def test_backup_then_delete():
    """11. 备份不覆盖；新文件拒绝；删除可撤销。"""
    hou.hipFile.clear(suppress_save_prompt=True)
    geo = hou.node("/obj").createNode("geo", "geo1")
    _clear_flags(geo)
    node_a = mk(geo, "null", "delete_a")
    node_b = mk(geo, "null", "delete_b")
    path_a, path_b = node_a.path(), node_b.path()

    scene_dir = os.path.join(TMP, "backup_case")
    os.makedirs(scene_dir, exist_ok=True)
    hip_path = os.path.join(scene_dir, "scene.hip")
    hou.hipFile.save(file_name=hip_path)
    main_mtime = os.stat(hip_path).st_mtime_ns

    backup1 = actions.backup_then_delete([path_a])
    assert_true(os.path.isfile(backup1), "第一次备份文件不存在")
    assert_true(hou.node(path_a) is None, "第一次删除没生效")
    content1 = open(backup1, "rb").read()
    backup1_mtime = os.stat(backup1).st_mtime_ns

    hou.undos.performUndo()
    assert_true(hou.node(path_a) is not None, "删除应能撤销")

    time.sleep(0.03)
    backup2 = actions.backup_then_delete([path_b])
    assert_true(os.path.isfile(backup2), "第二次备份文件不存在")
    assert_true(backup2 != backup1, "两次备份应是不同文件")
    assert_true(open(backup1, "rb").read() == content1, "旧备份内容被改了")
    assert_true(os.stat(backup1).st_mtime_ns == backup1_mtime,
                "旧备份的修改时间被改了")
    assert_true(os.stat(hip_path).st_mtime_ns == main_mtime,
                "主 hip 文件被工具改动了")

    hou.hipFile.clear(suppress_save_prompt=True)
    try:
        actions.backup_then_delete([])
    except RuntimeError:
        pass
    else:
        raise AssertionError("新文件（未存盘）时 backup_then_delete 应拒绝执行")


def test_unsupported_layers():
    """12. 不是 SOP 的层返回“不支持”和明确原因。"""
    new_scene()
    for path in ("/obj", "/out"):
        node = hou.node(path)
        assert_true(node is not None, "%s 应存在" % path)
        result = scan.scan_layer(node)
        assert_true(not result["supported"], "%s 不该支持清理" % path)
        assert_true(bool(result.get("reason")), "%s 应给出原因" % path)
        assert_equal(result["groups"], [], "不支持的层不该有分组")


def test_ui():
    """13. ui.py 可编译；在 hython 里能构造窗口并显示清理分组。"""
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

    geo = new_scene()
    mk(geo, "null", "ui_floating")
    hou.cd(geo.path())  # hython 没有网络编辑器，用 pwd 模拟“当前层”

    window = ui.show()
    assert_true(window is not None, "ui.show() 应返回窗口")
    assert_true(isinstance(window, QtWidgets.QDialog), "窗口应是 QDialog")
    assert_true(window._clean_tree.topLevelItemCount() >= 1,
                "清理列表应显示分组")
    first = window._clean_tree.topLevelItem(0)
    assert_true(first.checkState(0) == QtCore.Qt.Checked,
                "清理分组默认应全部勾上")
    assert_true(not window._delete_btn.isEnabled(),
                "未存盘时删除按钮应灰掉")
    assert_true(ui.show() is window, "再次 show() 应复用同一个窗口")
    window.close()
    assert_true(ui._get_window() is None, "关闭后单例应清掉")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def _save_and_reload(name):
    import tempfile
    path = os.path.join(tempfile.mkdtemp(prefix="hipcheck_"), name).replace("\\", "/")
    hou.hipFile.save(path)
    hou.hipFile.load(path, suppress_save_prompt=True, ignore_load_warnings=True)
    return path


def test_hda_self_reference_not_kept():
    """14. HDA（如 H21 的 Color SOP）内部引用自己参数，不算外部引用；存盘重开后也要判为没用分支。"""
    geo = new_scene()
    box = mk(geo, "box", "box1")
    mk(geo, "null", "OUT_main", [box])
    color = geo.createNode("color", "dead_color")  # 正常初始化，带 HDA 内部节点
    color.setInput(0, box)
    geo_path = geo.path()
    _save_and_reload("hda_self_ref.hip")
    geo = hou.node(geo_path)
    geo.node("dead_color").cook(force=True)  # 让 HDA 内部引用关系生成（界面里打开工程时会自然发生）
    assert_true(any(d.path().startswith(geo_path + "/dead_color/")
                    for d in geo.node("dead_color").dependents()),
                "前提不成立：Color SOP 内部没有引用自己")
    result = scan.scan_layer(geo)
    assert_equal(status_of(result, geo.path() + "/dead_color"), "unused_branch",
                 "HDA 自引用被误当成外部引用")


def test_check_false_positives():
    """15. 锁住 HDA 的内部节点、出厂默认值的文件参数（scatter 的 default.pic）不报。"""
    geo = new_scene()
    box = mk(geo, "box", "box1")
    sc = geo.createNode("scatter", "sc"); sc.setInput(0, box)
    fc = geo.createNode("filecache::2.0", "fc"); fc.setInput(0, sc)
    geo_path = geo.path()
    _save_and_reload("check_fp.hip")
    bad = [r for r in scan.check_hip()
           if r["node_path"].startswith(geo_path + "/fc/")
           or (r["node_path"] == geo_path + "/sc" and r["parm_name"] == "densitytexture")]
    assert_equal(bad, [], "检查出现误报")


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
    ("colorize_restore_undo", test_colorize_restore_undo),
    ("backup_then_delete", test_backup_then_delete),
    ("unsupported_layers", test_unsupported_layers),
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
