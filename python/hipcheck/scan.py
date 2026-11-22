"""hipcheck 的判断逻辑（不依赖任何 UI，可在 hython 里直接跑）。

对外两个函数：

- :func:`check_hip` 扫描整个 hip 的路径问题，返回结果列表。每条包含
  ``kind`` / ``node_path`` / ``parm_name`` / ``reason``。
- :func:`scan_layer` 扫描指定网络层（v1 只支持 SOP），返回清理分组。
  返回 dict：``{"supported": bool, "reason": str, "layer": str|None, "groups": [...]}``，
  每个分组是 ``{"status": "floating" | "unused_branch", "node_paths": [...]}``。
"""

import glob
import os
import posixpath
import re

import hou

#: 漂浮节点的上色颜色（紫）
COLOR_FLOATING = (0.6, 0.25, 0.85)
#: 没用分支的上色颜色（黄）
COLOR_UNUSED_BRANCH = (1.0, 0.85, 0.1)

_ABS_RAW_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|//)")
_OP_TOKEN_RE = re.compile(r"op:\s*[`\"']?([^\s`\"';,\)\]\}]+)")
_REL_TOKEN_RE = re.compile(r"(?<![\w./])((?:\.\.?/)+[A-Za-z0-9_.$/-]+)")
_ABS_TOKEN_RE = re.compile(r"/[A-Za-z0-9_.$/-]+")
_WILDCARD_RE = re.compile(r"%0?\d*d|\$F\d*")


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _as_node(value):
    """把 hou.Node 或路径字符串统一成 hou.Node；找不到返回 None。"""
    if value is None:
        return None
    if isinstance(value, hou.Node):
        return value
    if isinstance(value, str):
        try:
            return hou.node(value)
        except Exception:
            return None
    return None


def _all_nodes():
    """整个 hip 里的所有节点（不含根节点）。"""
    try:
        return list(hou.node("/").allSubChildren())
    except Exception:
        return []


def _safe_parm_template(parm):
    try:
        return parm.parmTemplate()
    except Exception:
        return None


def _is_file_reference_parm(parm):
    template = _safe_parm_template(parm)
    if template is None or template.type() != hou.parmTemplateType.String:
        return False
    try:
        return template.stringType() == hou.stringParmType.FileReference
    except Exception:
        return False


def _is_node_reference_parm(parm):
    template = _safe_parm_template(parm)
    if template is None or template.type() != hou.parmTemplateType.String:
        return False
    try:
        return template.stringType() in (
            hou.stringParmType.NodeReference,
            hou.stringParmType.NodeReferenceList,
        )
    except Exception:
        return False


def _is_manager_node(node):
    """Manager 网络（/obj、/out、/stage、/tasks…）不是用户节点。

    它们自带一些工具用的 FileReference 参数（比如 /stage 的
    rendergallerysource 默认指向临时画廊库），检查时要跳过，避免误报。
    """
    try:
        return node.type().category().name() == "Manager"
    except Exception:
        return False


def _type_base(node):
    try:
        name = node.type().name().lower()
    except Exception:
        return ""
    return name.split("::", 1)[0]


def _safe_flag(node, flag):
    try:
        return bool(node.isGenericFlagSet(flag))
    except Exception:
        return False


def _has_execute_button(node):
    try:
        parms = node.parms()
    except Exception:
        return False
    for parm in parms:
        if parm.name() != "execute":
            continue
        template = _safe_parm_template(parm)
        if template is not None and template.type() == hou.parmTemplateType.Button:
            return True
    return False


def _is_write_node(node):
    """是否是“会写文件”的节点（见 design.md 的终点定义）。"""
    base = _type_base(node)
    return base.startswith("rop_") or "filecache" in base or _has_execute_button(node)


def _node_reads_from_disk(node):
    """写文件类节点是否处在“从磁盘读”的模式。

    非写文件节点恒为读。
    """
    base = _type_base(node)
    if "filecache" in base:
        parm = node.parm("loadfromdisk")
        return bool(parm is not None and parm.evalAsInt())
    if base == "file":
        parm = node.parm("filemode")
        if parm is None:
            return True
        return parm.evalAsString() in ("read", "auto")
    if _is_write_node(node):
        return False
    return True


def _parm_values(parm):
    """当前帧、全局首帧、全局尾帧各求值一次，去重后返回（字符串）。"""
    frames = []
    try:
        frames.append(float(hou.frame()))
    except Exception:
        pass
    try:
        first, last = hou.playbar.frameRange()
        frames.extend([float(first), float(last)])
    except Exception:
        pass
    if not frames:
        frames = [1.0]

    values = []
    seen_frames = set()
    for frame in frames:
        key = round(frame, 6)
        if key in seen_frames:
            continue
        seen_frames.add(key)
        value = None
        try:
            value = parm.evalAtFrame(frame)
        except Exception:
            try:
                value = parm.eval()
            except Exception:
                value = None
        if value is None:
            continue
        value = str(value).strip()
        if value and value not in values:
            values.append(value)
    return values


def _resolve_path(path, bases=()):
    """把路径尽力解析成节点。

    路径可能带着参数名（如 ``/obj/geo1/box1/tx``），逐级去掉末尾再试。
    ``bases`` 里的基路径会依次与相对路径拼接。
    """
    if not path:
        return None
    path = path.strip().strip("`'\"")
    if not path:
        return None

    candidates = []
    if path.startswith("/"):
        candidates.append(posixpath.normpath(path))
    else:
        # 相对路径在不同上下文里语义略有差异（网络层 / 节点自身），全试一遍。
        bases = list(bases) + ["/"]
        for base in bases:
            try:
                candidates.append(posixpath.normpath(base + "/" + path))
            except Exception:
                continue

    for candidate in candidates:
        current = candidate
        while current and current != "/":
            try:
                node = hou.node(current)
            except Exception:
                node = None
            if node is not None:
                return node
            parent = posixpath.dirname(current)
            if parent == current:
                break
            current = parent
    return None


def _value_exists(value, node=None):
    """判断读取路径是否真的存在（支持序列通配、op: 路径）。"""
    value = value.strip()
    if not value:
        return True

    lowered = value.lower()
    if lowered.startswith("op:"):
        target = value[3:].strip()
        bases = []
        if node is not None:
            try:
                bases = [node.path(), node.parent().path()]
            except Exception:
                bases = []
        return _resolve_path(target, bases) is not None

    try:
        value = os.path.expanduser(os.path.expandvars(value))
    except Exception:
        pass
    if "$" in value:
        try:
            value = hou.text.expandString(value)
        except Exception:
            pass

    if any(ch in value for ch in "*?[") or _WILDCARD_RE.search(value):
        pattern = _WILDCARD_RE.sub("*", value)
        try:
            return bool(glob.glob(pattern))
        except Exception:
            return False
    try:
        if os.path.exists(value):
            return True
    except Exception:
        pass
    # 相对路径（如 scatter 的 default.pic）Houdini 会去 HOUDINI_PATH 里找。
    if not os.path.isabs(value):
        try:
            return hou.findFile(value) is not None
        except Exception:
            return False
    return False


def _token_matches_path(text, node_path):
    pattern = re.escape(node_path) + r"(?![A-Za-z0-9_])"
    try:
        return re.search(pattern, text) is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 检查：整个 hip 的路径问题
# ---------------------------------------------------------------------------

def check_hip():
    """扫描整个 hip，返回问题列表。

    每条结果是 dict：``kind``（``broken_path`` / ``absolute_path``）、
    ``node_path``、``parm_name``、``reason``，另带 ``value`` 方便 UI 展示。
    """
    results = []
    for node in _all_nodes():
        if _is_manager_node(node):
            continue
        # 锁住的 HDA 内部节点由 HDA 自己管，用户该看的是 HDA 本身的参数。
        try:
            if node.isInsideLockedHDA():
                continue
        except Exception:
            pass
        try:
            parms = node.parms()
        except Exception:
            continue
        for parm in parms:
            if not _is_file_reference_parm(parm):
                continue
            # 界面上灰掉或隐藏的参数（功能没启用）不报。
            try:
                if parm.isDisabled() or parm.isHidden():
                    continue
                # 还是出厂默认值（如 scatter 的 default.pic）说明用户没设过，不报。
                if parm.isAtDefault():
                    continue
            except Exception:
                pass
            try:
                raw = parm.unexpandedString()
            except Exception:
                raw = ""
            raw = (raw or "").strip()
            if not raw:
                continue

            # 1) 写死的绝对路径：只看参数原文。
            if _ABS_RAW_RE.match(raw):
                results.append({
                    "kind": "absolute_path",
                    "node_path": node.path(),
                    "parm_name": parm.name(),
                    "reason": "写死的绝对路径: %s" % raw,
                    "value": raw,
                })

            # 2) 路径断链：只查“读”的路径。
            if not _node_reads_from_disk(node):
                continue
            values = _parm_values(parm)
            if not values:
                continue
            if any(_value_exists(value, node) for value in values):
                continue
            results.append({
                "kind": "broken_path",
                "node_path": node.path(),
                "parm_name": parm.name(),
                "reason": "读取路径不存在: %s" % values[0],
                "value": values[0],
            })

    results.sort(key=lambda r: (r["node_path"], r["parm_name"], r["kind"]))
    return results


# ---------------------------------------------------------------------------
# 清理：当前层的分组
# ---------------------------------------------------------------------------

def _unsupported(network_node, reason):
    return {
        "supported": False,
        "reason": reason,
        "layer": network_node.path() if network_node is not None else None,
        "groups": [],
    }


def _is_self_or_inside(ref_path, target_path):
    """ref 是 target 自己或在它里面（HDA 内部引用自己参数），不算外部引用。"""
    return ref_path == target_path or ref_path.startswith(target_path + "/")


def _collect_referenced_paths(layer, layer_nodes):
    """在整个 hip 里找对 ``layer_nodes`` 的引用，返回被引用节点的路径集合。"""
    candidates = {node.path(): node for node in layer_nodes}
    referenced = set()

    # 1) Houdini 自带依赖（ch() 等表达式、spare input、按名字引用等）。
    #    dependents() 不含普通输入连线，正好是“输入之外”的依赖。
    for candidate in layer_nodes:
        try:
            dependents = candidate.dependents()
        except Exception:
            dependents = ()
        for dependent in dependents:
            try:
                if not _is_self_or_inside(dependent.path(), candidate.path()):
                    referenced.add(candidate.path())
                    break
            except Exception:
                continue
        if candidate.path() in referenced:
            continue

        # 再补一层 parmsReferencingThis()，有些版本对个别表达式写法更灵敏。
        try:
            parms = candidate.parms()
        except Exception:
            continue
        for parm in parms:
            try:
                ref_parms = parm.parmsReferencingThis()
            except Exception:
                continue
            for ref_parm in ref_parms:
                try:
                    ref_node = ref_parm.node()
                    if not _is_self_or_inside(ref_node.path(), candidate.path()):
                        referenced.add(candidate.path())
                        break
                except Exception:
                    continue
            if candidate.path() in referenced:
                break

    # 2) 字符串参数里写到的路径 / op: / 节点引用类参数。
    for ref_node in _all_nodes():
        try:
            parms = ref_node.parms()
        except Exception:
            continue
        for parm in parms:
            # 节点引用类参数直接求值最可靠。
            if _is_node_reference_parm(parm):
                try:
                    targets = parm.evalAsNodes()
                except Exception:
                    targets = ()
                for target in targets:
                    try:
                        if (target.path() in candidates
                                and not _is_self_or_inside(ref_node.path(), target.path())):
                            referenced.add(target.path())
                    except Exception:
                        continue

            template = _safe_parm_template(parm)
            if template is None or template.type() != hou.parmTemplateType.String:
                continue

            try:
                raw = parm.unexpandedString()
            except Exception:
                raw = ""
            raw = raw or ""
            if not raw:
                continue

            for path in list(candidates):
                if _is_self_or_inside(ref_node.path(), path):
                    continue
                if _token_matches_path(raw, path):
                    referenced.add(path)

            bases = []
            try:
                bases.append(ref_node.path())
                bases.append(ref_node.parent().path())
            except Exception:
                pass

            tokens = []
            for match in _OP_TOKEN_RE.finditer(raw):
                tokens.append(match.group(1))
            for match in _REL_TOKEN_RE.finditer(raw):
                tokens.append(match.group(1))
            for match in _ABS_TOKEN_RE.finditer(raw):
                tokens.append(match.group(0))

            for token in tokens:
                if not token or "$" in token:
                    continue
                target = _resolve_path(token, bases)
                if target is None:
                    continue
                try:
                    if (target.path() in candidates
                            and not _is_self_or_inside(ref_node.path(), target.path())):
                        referenced.add(target.path())
                except Exception:
                    continue

    return referenced


def _is_endpoint(node, referenced_paths):
    if _safe_flag(node, hou.nodeFlag.Display):
        return True
    if _safe_flag(node, hou.nodeFlag.Render):
        return True
    if _safe_flag(node, hou.nodeFlag.Template):
        return True
    if _safe_flag(node, hou.nodeFlag.Footprint):
        return True
    if node.name().lower().startswith("out"):
        return True
    if _is_write_node(node):
        return True
    if (_safe_flag(node, hou.nodeFlag.Lock)
            or _safe_flag(node, hou.nodeFlag.SoftLock)):
        return True
    try:
        if node.comment().strip():
            return True
    except Exception:
        pass
    return node.path() in referenced_paths


class _UnionFind(object):
    def __init__(self, items):
        self._parent = {item: item for item in items}

    def find(self, item):
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra


def scan_layer(network_node):
    """扫描一层网络，返回清理分组；不支持的层返回明确原因。"""
    layer = _as_node(network_node)
    if layer is None:
        return _unsupported(None, "找不到当前网络层（需要在网络编辑器里）")

    try:
        category = layer.type().category().name()
    except Exception:
        category = ""
    try:
        child_category = layer.type().childTypeCategory().name()
    except Exception:
        child_category = ""
    # 网络编辑器停在 /obj/geo1 时，层自身的 category 是 Object，
    # 真正的子网络类型要看 childTypeCategory()。
    if "Sop" not in (category, child_category):
        return _unsupported(
            layer,
            "这一层不是 SOP 网络（%s），v1 只支持 SOP 网络的清理"
            % (child_category or category or "未知"),
        )

    try:
        inside_locked = layer.isInsideLockedHDA()
    except Exception:
        inside_locked = False
    if inside_locked:
        return _unsupported(layer, "这一层在锁住的 HDA 里面，v1 不支持清理")

    try:
        layer_nodes = list(layer.children())
    except Exception:
        layer_nodes = []

    # 网络 dot 不在 children() 里，node.inputs() 已经会透明穿过它。
    node_by_path = {node.path(): node for node in layer_nodes}
    referenced_paths = _collect_referenced_paths(layer, layer_nodes)

    useful = set()
    stack = []
    for node in layer_nodes:
        if _is_endpoint(node, referenced_paths):
            useful.add(node.path())
            stack.append(node)

    # 从终点沿输入连线往上游 BFS（Switch 没选中的输入、bypass 连线都算）。
    while stack:
        node = stack.pop()
        try:
            inputs = node.inputs()
        except Exception:
            inputs = ()
        for input_node in inputs:
            if input_node is None:
                continue
            path = input_node.path()
            if path not in node_by_path:
                continue
            if path in useful:
                continue
            useful.add(path)
            stack.append(input_node)

    remaining = [
        node for node in layer_nodes if node.path() not in useful
    ]
    remaining_paths = {node.path() for node in remaining}

    uf = _UnionFind(remaining_paths)
    for node in remaining:
        try:
            inputs = node.inputs()
        except Exception:
            inputs = ()
        for input_node in inputs:
            if input_node is None:
                continue
            in_path = input_node.path()
            if in_path in remaining_paths:
                uf.union(node.path(), in_path)

    groups = {}
    for node in remaining:
        groups.setdefault(uf.find(node.path()), []).append(node)

    result_groups = []
    for members in groups.values():
        is_branch = False
        for node in members:
            try:
                inputs = node.inputs()
            except Exception:
                inputs = ()
            for input_node in inputs:
                if input_node is None:
                    continue
                if input_node.path() in useful:
                    is_branch = True
                    break
            if is_branch:
                break
        paths = sorted(node.path() for node in members)
        result_groups.append({
            "status": "unused_branch" if is_branch else "floating",
            "node_paths": paths,
        })

    result_groups.sort(key=lambda group: group["node_paths"][0] if group["node_paths"] else "")
    return {
        "supported": True,
        "reason": "",
        "layer": layer.path(),
        "groups": result_groups,
    }
