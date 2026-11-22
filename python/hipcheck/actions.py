"""hipcheck's actions (no UI).

Every scene-changing action runs inside ``hou.undos.group`` so a single Ctrl+Z
reverts it. All group labels start with :data:`UNDO_PREFIX`.
"""

import hou

from . import scan

#: Node userData key marking a node as ignored; value "1"
IGNORE_KEY = scan.IGNORE_KEY

#: Every hipcheck undo group label starts with this
UNDO_PREFIX = "hipcheck: "

#: The one color used to mark nodes
COLOR_RED = (1.0, 0.0, 0.0)


def _node_list(items):
    """Deduplicate a mixed list of nodes / paths into hou.Node objects (order kept)."""
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


def is_ignored(node):
    """Whether the node carries the ignore mark."""
    return node.userData(IGNORE_KEY) == "1"


# ---------------------------------------------------------------------------
# Ignore marks
# ---------------------------------------------------------------------------

def ignore(paths):
    """Mark the given nodes as ignored. Returns the number of nodes changed."""
    count = 0
    with hou.undos.group(UNDO_PREFIX + "ignore"):
        for node in _node_list(paths):
            if is_ignored(node):
                continue
            node.setUserData(IGNORE_KEY, "1")
            count += 1
    return count


def unignore(paths):
    """Remove the ignore mark from the given nodes. Returns the number changed."""
    count = 0
    with hou.undos.group(UNDO_PREFIX + "unignore"):
        for node in _node_list(paths):
            if not is_ignored(node):
                continue
            node.destroyUserData(IGNORE_KEY)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Color / delete
# ---------------------------------------------------------------------------

def colorize(paths):
    """Color the given nodes red. Returns the number of nodes colored."""
    count = 0
    with hou.undos.group(UNDO_PREFIX + "color"):
        for node in _node_list(paths):
            node.setColor(hou.Color(*COLOR_RED))
            count += 1
    return count


def delete(paths):
    """Destroy the given nodes. Returns the number of nodes deleted."""
    nodes = _node_list(paths)
    count = 0
    with hou.undos.group(UNDO_PREFIX + "delete"):
        # Delete deeper paths first (downstream), to avoid repeated rewiring.
        for node in sorted(nodes, key=lambda n: len(n.path()), reverse=True):
            if node.parent() is None:
                continue
            node.destroy()
            count += 1
    return count
