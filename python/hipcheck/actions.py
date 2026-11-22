"""hipcheck 的动作（不依赖 UI）。

所有会改场景的操作都放进 ``hou.undos.group``，Ctrl+Z 一次撤回。
"""

import json
import os

import hou

from . import scan

#: 原始颜色存在节点 userData 里的键名
ORIG_COLOR_KEY = "hipcheck_orig_color"


def _node_list(items):
    """把节点 / 路径的混合列表去重成 hou.Node 列表（保持顺序）。"""
    nodes = []
    seen = set()
    for item in items or ():
        node = item if isinstance(item, hou.Node) else scan._as_node(item)
        if node is None:
            continue
        path = node.path()
        if path in seen:
            continue
        seen.add(path)
        nodes.append(node)
    return nodes


def _groups_from(groups):
    """兼容传入 scan_layer 的整个结果或只传 groups 列表。"""
    if isinstance(groups, dict):
        return list(groups.get("groups", []))
    return list(groups or ())


def _status_color(status):
    if status == "unused_branch":
        return hou.Color(*scan.COLOR_UNUSED_BRANCH)
    return hou.Color(*scan.COLOR_FLOATING)


# ---------------------------------------------------------------------------
# 高亮 / 上色 / 恢复
# ---------------------------------------------------------------------------

def _first_network_editor():
    try:
        return hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    except Exception:
        return None


def highlight(paths):
    """选中节点并让网络编辑器框住它们；没有 UI（hython）时静默跳过。"""
    nodes = _node_list(paths)
    if not nodes:
        return False

    # Houdini 21 的 NetworkEditor 没有 selectNodes/frameSelection：
    # 选中用 NetworkMovableItem.setSelected，框选用 toolutils.homeToItems。
    try:
        for index, node in enumerate(nodes):
            node.setSelected(True, clear_all_selected=(index == 0))
    except Exception:
        return False

    editor = _first_network_editor()
    if editor is None:
        return False

    try:
        editor.setPwd(nodes[0].parent())
    except Exception:
        pass
    try:
        editor.setCurrentNode(nodes[0])
    except Exception:
        pass
    try:
        import toolutils
        toolutils.homeToItems(nodes)
    except Exception:
        pass
    return True


def _store_original_color(node):
    try:
        if node.userData(ORIG_COLOR_KEY) is not None:
            return
        color = node.color()
        if color is None:
            return
        rgb = color.rgb()
        try:
            is_default = bool(node.isGenericFlagSet(hou.nodeFlag.ColorDefault))
        except Exception:
            is_default = False
        # 记下“原本就是默认色”，恢复时用 ColorDefault 而不是写死一个灰色。
        value = json.dumps({
            "default": is_default,
            "rgb": [rgb[0], rgb[1], rgb[2]],
        })
        node.setUserData(ORIG_COLOR_KEY, value)
    except Exception:
        pass


def colorize(groups):
    """给分组上色：漂浮紫、没用分支黄。返回被上色的节点数。"""
    groups = _groups_from(groups)
    count = 0
    with hou.undos.group("hipcheck 上色"):
        for group in groups:
            color = _status_color(group.get("status"))
            for node in _node_list(group.get("node_paths", ())):
                _store_original_color(node)
                try:
                    node.setColor(color)
                    count += 1
                except Exception:
                    continue
    return count


def restore_colors(paths=None, layer=None):
    """恢复上色前的颜色，并清掉 userData 记录。

    - 给了 ``paths``：只恢复这些节点。
    - 只给 ``layer``（节点或路径）：恢复该层所有节点。
    - 都不给：恢复整个 hip 里所有带记录的节点。
    """
    if paths is not None:
        nodes = _node_list(paths)
    else:
        layer_node = scan._as_node(layer)
        if layer_node is not None:
            try:
                nodes = list(layer_node.children())
            except Exception:
                nodes = []
        else:
            nodes = scan._all_nodes()

    count = 0
    with hou.undos.group("hipcheck 恢复颜色"):
        for node in nodes:
            try:
                value = node.userData(ORIG_COLOR_KEY)
            except Exception:
                value = None
            if value is None:
                continue
            try:
                data = json.loads(value)
            except Exception:
                data = None
            if data is not None:
                try:
                    if isinstance(data, dict):
                        rgb = data.get("rgb")
                        use_default = bool(data.get("default"))
                    else:  # 兼容早期只存 [r, g, b] 的格式
                        rgb = data
                        use_default = False
                    restored = False
                    if use_default:
                        try:
                            node.setGenericFlag(hou.nodeFlag.ColorDefault, True)
                            restored = True
                        except Exception:
                            restored = False
                    if not restored and rgb:
                        node.setColor(hou.Color(
                            float(rgb[0]), float(rgb[1]), float(rgb[2])))
                        restored = True
                    if restored:
                        count += 1
                except Exception:
                    pass
            try:
                node.destroyUserData(ORIG_COLOR_KEY)
            except Exception:
                pass
    return count


# ---------------------------------------------------------------------------
# 备份后删除
# ---------------------------------------------------------------------------

def _backup_dir_candidates(scene_dir, env_dir):
    candidates = []
    if env_dir:
        candidates.append(env_dir)
    if scene_dir:
        candidates.append(os.path.join(scene_dir, "backup"))
        candidates.append(scene_dir)
    return candidates


def _existing_backup_files(directories):
    existing = set()
    for directory in directories:
        try:
            for name in os.listdir(directory):
                existing.add(os.path.normcase(os.path.abspath(
                    os.path.join(directory, name))))
        except Exception:
            continue
    return existing


def backup_then_delete(paths):
    """先做 Houdini 备份，确认备份成功后再在撤销组里删除节点。

    三道保护（design.md）：
    1. 从不保存主 hip。
    2. 备份前记下备份目录已有文件；返回的备份路径原本就存在就停下。
    3. 备份文件确实存在才删除。

    返回备份文件路径。hip 从未存过盘时抛 ``RuntimeError``。
    """
    if hou.hipFile.isNewFile():
        raise RuntimeError("当前 hip 还没有存过盘，请先保存后再删除。")

    hip_path = hou.hipFile.path()
    if not hip_path or not os.path.isfile(hip_path):
        raise RuntimeError("当前 hip 还没有保存到磁盘，请先保存后再删除。")

    nodes = _node_list(paths)
    if not nodes:
        return None
    scene_dir = os.path.dirname(os.path.abspath(hip_path))
    try:
        env_dir = hou.text.expandString("$HOUDINI_BACKUP_DIR").strip()
    except Exception:
        env_dir = ""
    if env_dir:
        env_dir = os.path.abspath(env_dir)

    existing = _existing_backup_files(_backup_dir_candidates(scene_dir, env_dir))

    try:
        backup_path = hou.hipFile.saveAsBackup()
    except Exception as exc:
        raise RuntimeError("Houdini 备份失败，已停止删除：%s" % exc)
    if not backup_path:
        raise RuntimeError("Houdini 没有返回备份文件路径，已停止删除。")

    backup_abs = os.path.abspath(backup_path)
    if os.path.normcase(backup_abs) == os.path.normcase(os.path.abspath(hip_path)):
        raise RuntimeError("备份路径和主 hip 相同，已停止删除。")
    if os.path.normcase(backup_abs) in existing:
        raise RuntimeError(
            "备份文件 %s 原本就存在（可能覆盖旧备份），已停止删除。" % backup_abs)
    if not os.path.isfile(backup_abs):
        raise RuntimeError(
            "备份文件 %s 不存在，已停止删除。" % backup_abs)

    errors = []
    with hou.undos.group("hipcheck 删除节点"):
        # 先删路径更深的（下游），避免反复重连输入。
        for node in sorted(nodes, key=lambda n: len(n.path()), reverse=True):
            node_path = node.path()
            try:
                if node.parent() is None:
                    continue
                node.destroy()
            except Exception as exc:
                errors.append("%s: %s" % (node_path, exc))

    if errors:
        raise RuntimeError("备份成功（%s），但有节点删除失败：\n%s"
                           % (backup_abs, "\n".join(errors)))
    return backup_abs
