"""hipcheck's non-modal window.

Qt is always imported through ``hutil.Qt`` (works with both PySide2 / PySide6).
The checks and actions live in scan.py / actions.py; this file only displays and
handles interaction.
"""

import threading

import hou

from hutil.Qt import QtCore, QtGui, QtWidgets

from . import actions, scan


_STATUS_LABELS = {
    "floating": "Floating",
    "unused_branch": "Unused branch",
}

_KIND_LABELS = {
    "broken_path": "Missing input file",
    "absolute_path": "Absolute path",
}

#: Column-0 item data: node path (check rows and clean node rows)
_ROLE_PATH = QtCore.Qt.UserRole
#: Column-0 item data: scan group dict (clean group rows)
_ROLE_GROUP = QtCore.Qt.UserRole + 1
#: Jump-column item data: True when the row has a jump button
_ROLE_JUMP = QtCore.Qt.UserRole + 2

#: Width of the jump column (fits one small button)
_JUMP_WIDTH = 44


def _fit_columns_once(tree, columns, max_width=420):
    """Fit columns to their content the first time the tree has rows.

    After that the user's own column widths are kept across rescans.
    """
    if tree.property("hipcheck_fitted") or not tree.topLevelItemCount():
        return
    for column in columns:
        tree.resizeColumnToContents(column)
        tree.setColumnWidth(column, min(tree.columnWidth(column) + 12, max_width))
    tree.setProperty("hipcheck_fitted", True)


class _Tree(QtWidgets.QTreeWidget):
    """QTreeWidget with: Ctrl+C / right-click Copy Path, header sorting, and a
    hand cursor + highlight over jump cells."""

    def __init__(self, parent, headers, stretch, on_copy):
        super().__init__(parent)
        self._on_copy = on_copy
        self._hover = QtCore.QPersistentModelIndex()
        self._jump_column = len(headers) - 1
        self.setHeaderLabels(headers)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setTextElideMode(QtCore.Qt.ElideMiddle)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setMouseTracking(True)
        self.setItemDelegateForColumn(self._jump_column, _JumpDelegate(self))
        self.setSortingEnabled(True)
        self.sortByColumn(0, QtCore.Qt.AscendingOrder)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(stretch, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(self._jump_column, QtWidgets.QHeaderView.Fixed)
        header.resizeSection(self._jump_column, _JUMP_WIDTH)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def hover_index(self):
        return QtCore.QModelIndex(self._hover)

    def is_jump_column(self, column):
        return column == self._jump_column

    def mouseMoveEvent(self, event):
        index = self.indexAt(_event_pos(event))
        on_jump = index.isValid() and index.column() == self._jump_column             and bool(index.data(_ROLE_JUMP))
        new = QtCore.QPersistentModelIndex(index if on_jump else QtCore.QModelIndex())
        if new != self._hover:
            self._hover = new
            self.viewport().setCursor(
                QtCore.Qt.PointingHandCursor if on_jump else QtCore.Qt.ArrowCursor)
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover = QtCore.QPersistentModelIndex()
        self.viewport().unsetCursor()
        self.viewport().update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.matches(QtGui.QKeySequence.Copy):
            self._on_copy(self)
        else:
            super().keyPressEvent(event)

    def _context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        menu.addAction("Copy Path").triggered.connect(
            lambda: self._on_copy(self))
        menu.exec_(self.viewport().mapToGlobal(pos))


def _main_window():
    qt = getattr(hou, "qt", None)
    return qt.mainWindow() if qt is not None else None


def _network_editor():
    """The network editor the user is looking at, or None (hython has none)."""
    if not hasattr(hou, "ui"):
        return None
    for tab in hou.ui.paneTabs():
        if tab.type() == hou.paneTabType.NetworkEditor and tab.isCurrentTab():
            return tab
    return hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)


def _current_layer():
    """The layer the network editor is currently in."""
    editor = _network_editor()
    if editor is not None:
        return editor.pwd()
    return hou.pwd()


def _select_in_layer(paths, layer):
    """Select exactly the given nodes whose parent is ``layer``.

    If no node is in that layer, the Houdini selection is left untouched.
    Selection changes run with undo disabled so they add no undo entries.
    Returns the number of nodes selected.
    """
    layer_node = scan._as_node(layer)
    if layer_node is None:
        return 0
    layer_path = layer_node.path()
    nodes = []
    for path in paths or ():
        node = scan._as_node(path)
        parent = node.parent() if node is not None else None
        if parent is not None and parent.path() == layer_path:
            nodes.append(node)
    if not nodes:
        return 0
    with hou.undos.disabler():
        hou.clearAllSelected()
        for node in nodes:
            node.setSelected(True)
    return len(nodes)


def _unused_paths(paths, layer):
    """Keep only the paths a fresh scan still reports as unused in ``layer``."""
    result = scan.scan_layer(layer)
    unused = set()
    for group in result.get("groups", ()):
        unused.update(group.get("node_paths", ()))
    return result, [path for path in paths if path in unused]


def _event_pos(event):
    """Mouse position as QPoint (Qt6 has position(), Qt5 pos())."""
    return event.position().toPoint() if hasattr(event, "position") else event.pos()


def _jump_icon():
    """Houdini's own "jump to operator" icon; None in hython (no hou.qt)."""
    qt = getattr(hou, "qt", None)
    return qt.Icon("BUTTONS_jump") if qt is not None else None


class _JumpDelegate(QtWidgets.QStyledItemDelegate):
    """Paints Houdini's jump icon (as next to Object Merge's path).

    Only painted, not a widget per row, so thousands of rows stay fast. The
    cell under the mouse gets a soft highlight; clicks go through itemClicked.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._icon = _jump_icon()

    def paint(self, painter, option, index):
        if not index.data(_ROLE_JUMP):
            return
        tree = option.widget
        size = min(option.rect.height() - 4, 16)
        rect = QtCore.QRect(0, 0, size, size)
        rect.moveCenter(option.rect.center())
        painter.save()
        if tree is not None and tree.hover_index() == index:
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(option.palette.highlight().color().lighter(130))
            painter.drawRoundedRect(rect.adjusted(-4, -2, 4, 2), 3, 3)
        if self._icon is not None:
            self._icon.paint(painter, rect)
        else:
            painter.drawText(option.rect, QtCore.Qt.AlignCenter, "->")
        painter.restore()


class _Item(QtWidgets.QTreeWidgetItem):
    """Tree item that sorts numbers as numbers (the Clean "Count" column)."""

    def __lt__(self, other):
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        mine, theirs = self.text(column), other.text(column)
        if mine.isdigit() and theirs.isdigit():
            return int(mine) < int(theirs)
        return mine.lower() < theirs.lower()


def _jump_to(nodes):
    """Switch the network editor to the nodes' layer, select them, frame them.

    The first node becomes the current node. A single node is the 1-element
    case; the node's parent is the layer.
    """
    nodes = [n for n in (scan._as_node(item) for item in nodes) if n is not None]
    if not nodes:
        return False
    editor = _network_editor()
    with hou.undos.disabler():
        if editor is not None:
            editor.setPwd(nodes[0].parent())
            editor.setCurrentNode(nodes[0], pick_node=False)
        nodes[0].setSelected(True, clear_all_selected=True)
        for node in nodes[1:]:
            node.setSelected(True)
        if editor is not None:
            import toolutils
            toolutils.homeToItems(nodes)
    return True


def _grey(item):
    """Show an ignored row greyed out."""
    brush = QtWidgets.QApplication.palette().brush(
        QtGui.QPalette.Disabled, QtGui.QPalette.Text)
    for column in range(item.columnCount()):
        item.setForeground(column, brush)


def _group_item(label, paths, status):
    """A selectable/jumpable row standing for ``paths`` (status or chain)."""
    item = _Item([label, str(len(paths)), "", ""])
    item.setData(3, _ROLE_JUMP, True)
    item.setData(0, _ROLE_GROUP, {"status": status, "node_paths": list(paths)})
    return item


def _add_node_items(parent, paths, ignored):
    for path in paths:
        child = _Item(["", "", path, ""])
        child.setData(3, _ROLE_JUMP, True)
        child.setData(0, _ROLE_PATH, path)
        child.setToolTip(2, path)
        if path in ignored:
            _grey(child)
        parent.addChild(child)


class HipcheckWindow(QtWidgets.QDialog):
    """The singleton window; open it with ``ui.show()``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("hipcheck")
        self.resize(1000, 760)

        self._layer = None
        self._layer_supported = False

        layout = QtWidgets.QVBoxLayout(self)
        self._tabs = QtWidgets.QTabWidget(self)
        layout.addWidget(self._tabs, 1)
        self._rescan_btn = QtWidgets.QPushButton("Rescan", self)
        self._tabs.setCornerWidget(self._rescan_btn, QtCore.Qt.TopRightCorner)

        # Check: whole hip. Columns: Type, Node, Parm, Reason (fills), jump.
        check, self._check_tree, self._check_title, self._check_label, check_bar = (
            self._make_section(["Type", "Node", "Parm", "Reason", ""], stretch=3))
        self._check_tree.setRootIsDecorated(False)
        self._check_all = self._add_button(check_bar, "Select All")
        check_bar.addStretch(1)
        self._tabs.addTab(check, "Check")

        # Clean: current layer. Status > chain > node. Columns: Status, Count,
        # Node (fills), jump.
        clean, self._clean_tree, self._clean_title, self._clean_label, clean_bar = (
            self._make_section(["Status", "Count", "Node", ""], stretch=2))
        self._clean_tree.setExpandsOnDoubleClick(False)  # double-click jumps
        self._clean_all = self._add_button(clean_bar, "Select All")
        clean_bar.addStretch(1)
        self._delete_btn = self._add_button(clean_bar, "Delete Selected")
        self._tabs.addTab(clean, "Clean")

        # Outside the tabs: actions on whatever is selected in either list.
        layout.addSpacing(6)
        bar = self._global_bar = QtWidgets.QHBoxLayout()
        self._color_btn = self._add_button(bar, "Color Selected")
        bar.addStretch(1)
        self._show_ignored = QtWidgets.QCheckBox("Show Ignored", self)
        bar.addWidget(self._show_ignored)
        bar.addSpacing(8)
        self._ignore_btn = self._add_button(bar, "Ignore Selected")
        layout.addLayout(bar)
        self._status = QtWidgets.QLabel("", self)
        self._status.setWordWrap(True)
        self._status.setEnabled(False)  # greyed: secondary information
        layout.addWidget(self._status)

        self._rescan_btn.clicked.connect(self.refresh)
        self._color_btn.clicked.connect(self._color_selected)
        self._ignore_btn.clicked.connect(self._toggle_ignore)
        self._show_ignored.toggled.connect(self.refresh)
        self._delete_btn.clicked.connect(self._delete_selected)
        self._check_all.clicked.connect(lambda: self._select_all(self._check_tree))
        self._clean_all.clicked.connect(lambda: self._select_all(self._clean_tree))
        for tree in (self._check_tree, self._clean_tree):
            # Selection only mirrors into Houdini; the two lists are exclusive.
            tree.itemSelectionChanged.connect(
                lambda tree=tree: self._on_selection_changed(tree))
            tree.itemClicked.connect(
                lambda item, column, tree=tree: self._on_tree_clicked(
                    tree, item, column))
            tree.itemDoubleClicked.connect(
                lambda item, _column: self._jump_row(item))

        # All buttons share one width so the rows inside and outside the tabs
        # line up as columns.
        buttons = [b for b in self.findChildren(QtWidgets.QPushButton)
                   if b is not self._rescan_btn]  # Rescan sits in the tab corner
        self._ignore_btn.setText("Unignore Selected")  # measure the longer label
        width = max(button.sizeHint().width() for button in buttons)
        self._ignore_btn.setText("Ignore Selected")
        for button in buttons:
            button.setFixedWidth(width)

        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        # Indent the bar outside the tabs exactly like the bars inside them.
        QtCore.QTimer.singleShot(0, self._align_global_bar)

    def _align_global_bar(self):
        origin = QtCore.QPoint(0, 0)
        inner = self._check_all if self._check_all.isVisible() else self._clean_all
        margins = self._global_bar.contentsMargins()
        offset = (inner.mapTo(self, origin).x()
                  - self._color_btn.mapTo(self, origin).x() + margins.left())
        self._global_bar.setContentsMargins(offset, 0, offset, 0)

    def _make_section(self, headers, stretch):
        """Title row (bold title, count on the right), tree, button bar."""
        widget = QtWidgets.QWidget(self)
        box = QtWidgets.QVBoxLayout(widget)
        box.setContentsMargins(8, 8, 8, 8)
        title_row = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("", widget)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        count = QtWidgets.QLabel("", widget)
        count.setEnabled(False)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(count)
        box.addLayout(title_row)
        tree = _Tree(widget, headers, stretch, self._copy_paths)
        box.addWidget(tree, 1)
        bar = QtWidgets.QHBoxLayout()
        box.addLayout(bar)
        return widget, tree, title, count, bar

    def _add_button(self, bar, text):
        button = QtWidgets.QPushButton(text, self)
        bar.addWidget(button)
        return button

    # -- data ---------------------------------------------------------------

    def _set_status(self, text):
        self._status.setText(text)

    def refresh(self):
        """Rescan the whole hip and the current layer."""
        self._layer = _current_layer()
        include_ignored = self._show_ignored.isChecked()
        errors = []

        try:
            issues = scan.check_hip(include_ignored=include_ignored)
        except Exception as exc:
            issues = []
            errors.append("Check failed: %s" % exc)
        self._fill_check_tree(issues)

        try:
            result = scan.scan_layer(self._layer, include_ignored=include_ignored)
        except Exception as exc:
            result = {"supported": False,
                      "reason": "Clean scan failed: %s" % exc,
                      "groups": []}
            errors.append("Clean scan failed: %s" % exc)
        self._layer_supported = bool(result.get("supported"))
        self._fill_clean_tree(result)

        self._delete_btn.setEnabled(
            self._layer_supported and self._clean_tree.topLevelItemCount() > 0)
        self._update_ignore_button()
        self._set_status("; ".join(errors) if errors else "Scan complete.")

    def _fill_check_tree(self, issues):
        tree = self._check_tree
        tree.blockSignals(True)
        tree.setUpdatesEnabled(False)
        tree.setSortingEnabled(False)  # sort once after filling, not per row
        tree.clear()
        items = []
        for issue in issues:
            path = issue.get("node_path", "")
            item = _Item([
                _KIND_LABELS.get(issue.get("kind"), issue.get("kind", "")),
                path,
                issue.get("parm_name", ""),
                issue.get("reason", ""),
                "",
            ])
            item.setData(4, _ROLE_JUMP, True)
            item.setData(0, _ROLE_PATH, path)
            item.setToolTip(1, path)
            item.setToolTip(3, issue.get("reason", ""))
            if issue.get("ignored"):
                _grey(item)
            items.append(item)
        tree.addTopLevelItems(items)
        _fit_columns_once(tree, (0, 1, 2))
        tree.setSortingEnabled(True)
        tree.setUpdatesEnabled(True)
        tree.blockSignals(False)
        self._check_title.setText("Check  —  whole hip")
        self._check_label.setText("%d issue(s)" % len(issues))
        self._tabs.setTabText(0, "Check (%d)" % len(issues))

    def _fill_clean_tree(self, result):
        tree = self._clean_tree
        tree.blockSignals(True)
        tree.setUpdatesEnabled(False)
        tree.setSortingEnabled(False)
        tree.clear()
        layer_path = result.get("layer")
        if layer_path is None and self._layer is not None:
            layer_path = self._layer.path()
        self._clean_title.setText("Clean  —  %s" % (layer_path or "?"))

        if not result.get("supported"):
            reason = result.get("reason") or "This layer cannot be cleaned."
            item = _Item(["Unsupported", "", reason, ""])
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)
            tree.addTopLevelItem(item)
            self._clean_label.setText("")
            self._tabs.setTabText(1, "Clean")
            tree.setSortingEnabled(True)
            tree.setUpdatesEnabled(True)
            tree.blockSignals(False)
            return

        # Status rows (Floating / Unused branch) hold their chains; a status with
        # a single chain lists its nodes directly.
        by_status = {}
        for group in result.get("groups", []):
            by_status.setdefault(group.get("status"), []).append(group)
        total_nodes = 0
        items = []
        for status, groups in by_status.items():
            paths = [p for g in groups for p in g.get("node_paths", ())]
            ignored = {p for g in groups for p in g.get("ignored_paths", ())}
            total_nodes += len(paths)
            item = _group_item(
                _STATUS_LABELS.get(status, status or ""), paths, status)
            if len(groups) == 1:
                _add_node_items(item, paths, ignored)
            else:
                for index, group in enumerate(groups, 1):
                    chain_paths = list(group.get("node_paths", ()))
                    chain = _group_item("Chain %d" % index, chain_paths, status)
                    _add_node_items(chain, chain_paths, ignored)
                    item.addChild(chain)
            items.append(item)
        tree.addTopLevelItems(items)
        for item in items:  # Unused branch opens to show its chains
            item.setExpanded(item.data(0, _ROLE_GROUP)["status"] == "unused_branch")
        _fit_columns_once(tree, (0, 1))
        tree.setSortingEnabled(True)
        tree.setUpdatesEnabled(True)
        tree.blockSignals(False)
        self._clean_label.setText(
            "%d chain(s) / %d node(s)"
            % (len(result.get("groups", [])), total_nodes))
        self._tabs.setTabText(1, "Clean (%d)" % total_nodes)

    # -- selection / jump ---------------------------------------------------

    @staticmethod
    def _selected_paths(tree):
        """Node paths of all selected rows; a group row counts as its nodes."""
        paths = []
        for item in tree.selectedItems():
            group = item.data(0, _ROLE_GROUP)
            if group is not None:
                paths.extend(group.get("node_paths", ()))
                continue
            path = item.data(0, _ROLE_PATH)
            if path:
                paths.append(path)
        return list(dict.fromkeys(paths))

    def _active_paths(self):
        """Selected node paths of whichever list has a selection."""
        return (self._selected_paths(self._check_tree)
                or self._selected_paths(self._clean_tree))

    def _select_all(self, tree):
        """Select every top-level row (group rows stand for all their nodes)."""
        tree.blockSignals(True)
        tree.clearSelection()
        for index in range(tree.topLevelItemCount()):
            tree.topLevelItem(index).setSelected(True)
        tree.blockSignals(False)
        self._on_selection_changed(tree)

    def _on_selection_changed(self, tree):
        # The two lists are mutually exclusive: selecting in one clears the other.
        other = self._clean_tree if tree is self._check_tree else self._check_tree
        other.blockSignals(True)
        other.clearSelection()
        other.blockSignals(False)

        layer = _current_layer()
        layer_path = layer.path()
        count = _select_in_layer(self._selected_paths(tree), layer)
        if count:
            self._set_status("Selected %d node(s) in %s." % (count, layer_path))
        else:
            self._set_status(
                "No selected row is in the current layer (%s)." % layer_path)
        self._update_ignore_button()

    def _update_ignore_button(self):
        """Say "Unignore Selected" when every selected node is already ignored."""
        nodes = [n for n in map(scan._as_node, self._active_paths()) if n is not None]
        unignore = bool(nodes) and all(actions.is_ignored(n) for n in nodes)
        self._ignore_btn.setText("Unignore Selected" if unignore else "Ignore Selected")

    def _on_tree_clicked(self, tree, item, column):
        if tree.is_jump_column(column):
            self._jump_row(item)

    def _jump_row(self, item):
        """Jump to a row's node, or to all nodes of a group row."""
        group = item.data(0, _ROLE_GROUP)
        if group is not None:
            paths = list(group.get("node_paths", ()))
        else:
            paths = [p for p in (item.data(0, _ROLE_PATH),) if p]
        if not paths:
            return
        if _jump_to(paths):
            self._set_status("Jumped to %d node(s)." % len(paths))
        else:
            self._set_status("Node(s) no longer exist.")

    def _copy_paths(self, tree):
        paths = self._selected_paths(tree)
        if paths:
            QtWidgets.QApplication.clipboard().setText("\n".join(paths))
            self._set_status("Copied %d path(s)." % len(paths))

    # -- actions (each is one undo step: Ctrl+Z reverts it) -----------------

    def _color_selected(self):
        paths = self._active_paths()
        if not paths:
            self._set_status("Nothing selected.")
            return
        count = actions.colorize(paths)
        self._set_status("Colored %d node(s) red. Ctrl+Z to undo." % count)

    def _toggle_ignore(self):
        paths = self._active_paths()
        if not paths:
            self._set_status("Nothing selected.")
            return
        if self._ignore_btn.text().startswith("Unignore"):
            count, verb = actions.unignore(paths), "Unignored"
        else:
            count, verb = actions.ignore(paths), "Ignored"
        self.refresh()
        self._set_status("%s %d node(s). Ctrl+Z to undo." % (verb, count))

    def _delete_selected(self):
        paths = self._selected_paths(self._clean_tree)
        if not paths:
            self._set_status("Nothing selected in the Clean list.")
            return
        # Re-validate: the list may be stale, and another hip may have been
        # loaded while the window was open.
        result, kept = _unused_paths(paths, _current_layer())
        if not kept:
            self.refresh()
            self._set_status("Selected node(s) are no longer unused; nothing deleted.")
            return
        message = "Delete %d node(s) in %s?" % (len(kept), result.get("layer") or "?")
        dropped = len(paths) - len(kept)
        if dropped:
            message += ("\n%d selected node(s) are no longer unused (or are ignored) "
                        "and will be kept." % dropped)
        answer = QtWidgets.QMessageBox.question(
            self, "hipcheck", message,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        count = actions.delete(kept)
        self.refresh()
        self._set_status("Deleted %d node(s). Ctrl+Z to undo." % count)

    # -- lifecycle ----------------------------------------------------------

    def closeEvent(self, event):
        if _get_window() is self:
            _set_window(None)
        super().closeEvent(event)


# The window reference lives on hou.session, so a module reload (during
# development) does not create a second window.
_SESSION_KEY = "_hipcheck_window"


def _get_window():
    return getattr(hou.session, _SESSION_KEY, None)


def _set_window(window):
    setattr(hou.session, _SESSION_KEY, window)


def show(parent=None):
    """Open (or reuse) the non-modal window; calling again brings it up and rescans."""
    if threading.current_thread() is not threading.main_thread():
        import hdefereval
        hdefereval.executeDeferred(lambda: show(parent))
        return None

    old = _get_window()
    if old is not None:
        try:
            if isinstance(old, HipcheckWindow):
                old.refresh()
                old.show()
                old.raise_()
                old.activateWindow()
                return old
            old.close()  # window left over from older code: close and rebuild
        except RuntimeError:
            pass
        _set_window(None)

    if parent is None:
        parent = _main_window()
    window = HipcheckWindow(parent)
    _set_window(window)
    window.show()
    return window
