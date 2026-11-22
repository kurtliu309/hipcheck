"""hipcheck's check logic (no UI, runs directly in hython).

Two public functions:

- :func:`check_hip` scans the whole hip for path problems and returns a list of
  results. Each has ``kind`` / ``node_path`` / ``parm_name`` / ``reason`` /
  ``ignored``.
- :func:`scan_layer` scans one network layer (v1 only supports SOP) and returns
  cleaning groups. The result is
  ``{"supported": bool, "reason": str, "layer": str|None, "groups": [...]}``
  where each group is
  ``{"status": "floating" | "unused_branch", "node_paths": [...],
  "ignored_paths": [...]}``.

Nodes marked with :data:`IGNORE_KEY` user data are hidden by default; pass
``include_ignored=True`` to get them back, flagged.
"""

import glob
import os
import posixpath
import re

import hou

#: Node userData key marking a node as ignored; value "1"
IGNORE_KEY = "hipcheck_ignore"

_ABS_RAW_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|//)")
_OP_TOKEN_RE = re.compile(r"op:\s*[`\"']?([^\s`\"';,\)\]\}]+)")
_REL_TOKEN_RE = re.compile(r"(?<![\w./])((?:\.\.?/)+[A-Za-z0-9_.$/-]+)")
_ABS_TOKEN_RE = re.compile(r"/[A-Za-z0-9_.$/-]+")
_WILDCARD_RE = re.compile(r"%0?\d*d|\$F\d*")
#: A raw parm value with one of these is frame dependent (needs all frames).
_FRAME_TOKEN_RE = re.compile(r"\$[{(]?[FT]|%0|`")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _as_node(value):
    """Turn a hou.Node or a path string into a hou.Node; None if not found."""
    if isinstance(value, hou.Node):
        return value
    if isinstance(value, str):
        return hou.node(value)
    return None


def _all_nodes():
    """Every node in the hip (root node excluded)."""
    return list(hou.node("/").allSubChildren())


def _is_ignored(node):
    """Whether the node carries the hipcheck ignore mark."""
    return node.userData(IGNORE_KEY) == "1"


def _string_parm_type(parm):
    """The hou.stringParmType of a string parm, None for other parm types."""
    template = parm.parmTemplate()
    if template.type() != hou.parmTemplateType.String:
        return None
    return template.stringType()


def _is_manager_node(node):
    """Manager networks (/obj, /out, /stage, /tasks, ...) are not user nodes.

    They ship tool FileReference parms (for example /stage's
    rendergallerysource defaults to a temporary gallery), so skipping them
    avoids false positives.
    """
    return node.type().category().name() == "Manager"


def _type_base(node):
    return node.type().name().lower().split("::", 1)[0]


def _has_execute_button(node):
    for parm in node.parms():
        if parm.name() != "execute":
            continue
        if parm.parmTemplate().type() == hou.parmTemplateType.Button:
            return True
    return False


def _is_write_node(node):
    """Whether the node writes files (see the endpoint list in design.md).

    Driver nodes (ROPs, wherever they live: /out, inside SOP/LOP/TOP networks)
    write files; so do rop_* SOPs, File Cache and nodes with an execute button.
    """
    if node.type().category().name() == "Driver":
        return True
    base = _type_base(node)
    return base.startswith("rop_") or "filecache" in base or _has_execute_button(node)


def _node_reads_from_disk(node):
    """Whether a file-writing node is in a "read from disk" mode.

    Nodes that do not write files always read.
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
    return not _is_write_node(node)


def _check_frames():
    """Current frame plus the global start and end frame, unique."""
    frames = [float(hou.frame())]
    first, last = hou.playbar.frameRange()
    frames.extend((float(first), float(last)))
    unique = []
    for frame in frames:
        if frame not in unique:
            unique.append(frame)
    return unique


def _parm_values(parm, raw, frames):
    """Evaluate at every check frame when the raw text is frame dependent."""
    values = []
    for frame in (frames if _FRAME_TOKEN_RE.search(raw) else frames[:1]):
        try:
            value = parm.evalAtFrame(frame)
        except Exception:
            value = None
        if value is None:
            continue
        value = str(value).strip()
        if value and value not in values:
            values.append(value)
    return values


def _resolve_path(path, bases=()):
    """Resolve a path to a node as best as possible.

    The path may include a parm name (e.g. ``/obj/geo1/box1/tx``); trailing
    components are dropped one by one. Each base in ``bases`` is prepended to
    relative paths in turn.
    """
    if not path:
        return None
    path = path.strip().strip("`'\"")
    if not path:
        return None

    if path.startswith("/"):
        candidates = [posixpath.normpath(path)]
    else:
        # Relative paths differ slightly by context (network layer vs. the node
        # itself), so try them all.
        candidates = [posixpath.normpath(base + "/" + path)
                      for base in list(bases) + ["/"]]

    for candidate in candidates:
        current = candidate
        while current and current != "/":
            node = hou.node(current)
            if node is not None:
                return node
            parent = posixpath.dirname(current)
            if parent == current:
                break
            current = parent
    return None


def _value_exists(value, node=None):
    """Whether a read path really exists (supports sequence wildcards, op: paths)."""
    value = value.strip()
    if not value:
        return True

    if value.lower().startswith("op:"):
        target = value[3:].strip()
        bases = [node.path(), node.parent().path()] if node is not None else []
        return _resolve_path(target, bases) is not None

    value = os.path.expanduser(os.path.expandvars(value))
    if "$" in value:
        value = hou.text.expandString(value)

    # Houdini resolves relative paths through its own search paths (built-in
    # files such as the camera's defcam.bgeo), which cannot be reproduced
    # reliably, so a relative path is never reported as missing.
    if not os.path.isabs(value):
        return True

    if any(ch in value for ch in "*?[") or _WILDCARD_RE.search(value):
        return bool(glob.glob(_WILDCARD_RE.sub("*", value)))
    return os.path.exists(value)


# ---------------------------------------------------------------------------
# Check: path problems in the whole hip
# ---------------------------------------------------------------------------

def check_hip(include_ignored=False):
    """Scan the whole hip and return a list of issues.

    Each entry is a dict: ``kind`` (``broken_path`` / ``absolute_path``),
    ``node_path``, ``parm_name``, ``reason``, ``value``, and ``ignored``.
    Issues on ignored nodes are dropped unless ``include_ignored`` is true.
    """
    results = []
    frames = _check_frames()
    for node in _all_nodes():
        if _is_manager_node(node) or node.isInsideLockedHDA():
            continue
        ignored = _is_ignored(node)
        if ignored and not include_ignored:
            continue
        reads_from_disk = None  # computed once per node, only when needed
        for parm in node.parms():
            if _string_parm_type(parm) != hou.stringParmType.FileReference:
                continue
            # Grayed-out or hidden parms (feature not enabled) and factory
            # defaults (e.g. scatter's default.pic) are not reported.
            if parm.isDisabled() or parm.isHidden() or parm.isAtDefault():
                continue
            try:
                raw = parm.unexpandedString()
            except hou.OperationFailed:
                raw = ""
            raw = (raw or "").strip()
            if not raw:
                continue

            # 1) Hardcoded absolute path: the raw parm text only.
            if _ABS_RAW_RE.match(raw):
                results.append({
                    "kind": "absolute_path",
                    "node_path": node.path(),
                    "parm_name": parm.name(),
                    "reason": "Hardcoded absolute path: %s "
                              "(not relative to $HIP/$JOB)" % raw,
                    "value": raw,
                    "ignored": ignored,
                })

            # 2) Broken path: only "read" paths are checked.
            if reads_from_disk is None:
                reads_from_disk = _node_reads_from_disk(node)
            if not reads_from_disk:
                continue
            values = _parm_values(parm, raw, frames)
            if not values or any(_value_exists(value, node) for value in values):
                continue
            results.append({
                "kind": "broken_path",
                "node_path": node.path(),
                "parm_name": parm.name(),
                "reason": "File not found: %s" % values[0],
                "value": values[0],
                "ignored": ignored,
            })

    results.sort(key=lambda r: (r["node_path"], r["parm_name"], r["kind"]))
    return results


# ---------------------------------------------------------------------------
# Clean: groups in the current layer
# ---------------------------------------------------------------------------

def _unsupported(network_node, reason):
    return {
        "supported": False,
        "reason": reason,
        "layer": network_node.path() if network_node is not None else None,
        "groups": [],
    }


def _is_self_or_inside(ref_path, target_path):
    """ref is target itself or inside it (an HDA referencing its own parms)."""
    return ref_path == target_path or ref_path.startswith(target_path + "/")


def _collect_referenced_paths(layer_nodes):
    """Find references to ``layer_nodes`` in the whole hip; return their paths."""
    candidates = {node.path(): node for node in layer_nodes}
    referenced = set()

    # 1) Houdini's own dependencies (ch() expressions, spare inputs, name
    #    references, ...). dependents() excludes plain input wires, which is
    #    exactly "anything besides inputs".
    for candidate in layer_nodes:
        candidate_path = candidate.path()
        for dependent in candidate.dependents():
            if not _is_self_or_inside(dependent.path(), candidate_path):
                referenced.add(candidate_path)
                break
        if candidate_path in referenced:
            continue
        # parmsReferencingThis() catches some more expression forms.
        for parm in candidate.parms():
            for ref_parm in parm.parmsReferencingThis():
                if not _is_self_or_inside(ref_parm.node().path(), candidate_path):
                    referenced.add(candidate_path)
                    break
            if candidate_path in referenced:
                break

    # 2) Paths / op: mentions in string parms, and node-reference parms.
    if not candidates:
        return referenced
    # One alternation instead of one search per candidate; longest paths first
    # so a prefix never shadows a longer path.
    path_re = re.compile("|".join(
        re.escape(path) + r"(?![A-Za-z0-9_])"
        for path in sorted(candidates, key=len, reverse=True)))

    for ref_node in _all_nodes():
        if len(referenced) == len(candidates):
            break
        ref_path = ref_node.path()
        for parm in ref_node.parms():
            string_type = _string_parm_type(parm)
            # Evaluating node-reference parms directly is most reliable.
            if string_type in (hou.stringParmType.NodeReference,
                               hou.stringParmType.NodeReferenceList):
                for target in parm.evalAsNodes():
                    target_path = target.path()
                    if (target_path in candidates
                            and not _is_self_or_inside(ref_path, target_path)):
                        referenced.add(target_path)
            if string_type is None:
                continue

            try:
                raw = parm.unexpandedString()
            except hou.OperationFailed:
                continue
            if not raw:
                continue

            for match in path_re.finditer(raw):
                path = match.group(0)
                if not _is_self_or_inside(ref_path, path):
                    referenced.add(path)
            if len(referenced) == len(candidates):
                break

            bases = [ref_path, ref_node.parent().path()]
            tokens = [m.group(1) for m in _OP_TOKEN_RE.finditer(raw)]
            tokens += [m.group(1) for m in _REL_TOKEN_RE.finditer(raw)]
            tokens += [m.group(0) for m in _ABS_TOKEN_RE.finditer(raw)]
            for token in tokens:
                if not token or "$" in token:
                    continue
                target = _resolve_path(token, bases)
                if target is None:
                    continue
                target_path = target.path()
                if (target_path in candidates
                        and not _is_self_or_inside(ref_path, target_path)):
                    referenced.add(target_path)

    return referenced


def _is_endpoint(node, referenced_paths):
    for flag in (hou.nodeFlag.Display, hou.nodeFlag.Render,
                 hou.nodeFlag.Template, hou.nodeFlag.Footprint,
                 hou.nodeFlag.Lock, hou.nodeFlag.SoftLock):
        if node.isGenericFlagSet(flag):
            return True
    if node.name().lower().startswith("out"):
        return True
    if _is_write_node(node):
        return True
    if node.comment().strip():
        return True
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


def scan_layer(network_node, include_ignored=False):
    """Scan one network layer and return cleaning groups; unsupported layers explain why.

    Ignore marks never change the analysis. After grouping, ignored node paths
    are removed from ``node_paths`` (empty groups are dropped) unless
    ``include_ignored`` is true; ``ignored_paths`` always holds the ignored
    subset of the group's ``node_paths``.
    """
    layer = _as_node(network_node)
    if layer is None:
        return _unsupported(None, "Current network layer not found (open a network editor).")

    category = layer.type().category().name()
    # The root is a Director node, whose childTypeCategory() is not available.
    child_category = "" if category == "Director" else layer.type().childTypeCategory().name()
    # When the network editor sits in /obj/geo1, the layer's own category is
    # Object; the real child network type is childTypeCategory().
    if "Sop" not in (category, child_category):
        return _unsupported(
            layer,
            "This layer is not a SOP network (%s); v1 only cleans SOP networks."
            % (child_category or category or "unknown"),
        )

    if layer.isInsideLockedHDA():
        return _unsupported(
            layer, "This layer is inside a locked HDA; v1 does not clean it.")

    # Network dots are not in children(), and node.inputs() already sees
    # through them.
    layer_nodes = list(layer.children())
    node_by_path = {node.path(): node for node in layer_nodes}
    referenced_paths = _collect_referenced_paths(layer_nodes)

    useful = set()
    stack = []
    for node in layer_nodes:
        if _is_endpoint(node, referenced_paths):
            useful.add(node.path())
            stack.append(node)

    # BFS upstream from the endpoints along input wires (including unselected
    # Switch inputs and wires through bypassed nodes).
    while stack:
        node = stack.pop()
        for input_node in node.inputs():
            if input_node is None:
                continue
            path = input_node.path()
            if path not in node_by_path or path in useful:
                continue
            useful.add(path)
            stack.append(input_node)

    remaining = [node for node in layer_nodes if node.path() not in useful]
    remaining_paths = {node.path() for node in remaining}

    uf = _UnionFind(remaining_paths)
    for node in remaining:
        for input_node in node.inputs():
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
        is_branch = any(
            input_node is not None and input_node.path() in useful
            for node in members for input_node in node.inputs())
        ignored = {node.path() for node in members if _is_ignored(node)}
        paths = sorted(node.path() for node in members)
        if not include_ignored:
            paths = [path for path in paths if path not in ignored]
            if not paths:
                continue
        result_groups.append({
            "status": "unused_branch" if is_branch else "floating",
            "node_paths": paths,
            "ignored_paths": [path for path in paths if path in ignored],
        })

    result_groups.sort(key=lambda group: group["node_paths"][0] if group["node_paths"] else "")
    return {
        "supported": True,
        "reason": "",
        "layer": layer.path(),
        "groups": result_groups,
    }
