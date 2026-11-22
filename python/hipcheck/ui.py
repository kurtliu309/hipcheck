"""hipcheck 的非模态弹窗。

Qt 一律从 ``hutil.Qt`` 导入（兼容 Houdini 20.5 / 21 的 PySide2 / PySide6）。
判断和动作都在 scan.py / actions.py 里，本文件只负责展示与交互。
"""

import traceback

import hou

from hutil.Qt import QtCore, QtWidgets

from . import actions, scan

_WINDOW = None

_STATUS_LABELS = {
    "floating": "漂浮",
    "unused_branch": "没用分支",
}

_KIND_LABELS = {
    "broken_path": "路径断链",
    "absolute_path": "绝对路径",
}


def _main_window():
    try:
        qt = getattr(hou, "qt", None)
        if qt is not None:
            return qt.mainWindow()
    except Exception:
        pass
    return None


def _network_editor():
    # 优先用当前窗格（就是用户正在看的网络编辑器）。
    try:
        tab = hou.ui.curDesktop().currentPaneTab()
        if tab is not None and tab.type() == hou.paneTabType.NetworkEditor:
            return tab
    except Exception:
        pass
    try:
        return hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    except Exception:
        return None


def _current_layer():
    """扫描时网络编辑器所在的那一层。"""
    editor = _network_editor()
    if editor is not None:
        try:
            return editor.pwd()
        except Exception:
            pass
    try:
        return hou.pwd()
    except Exception:
        return None


def _is_new_file():
    try:
        return bool(hou.hipFile.isNewFile())
    except Exception:
        return False


class HipcheckWindow(QtWidgets.QDialog):
    """单例弹窗本体；用 ``ui.show()`` 打开。"""

    def __init__(self, parent=None):
        super(HipcheckWindow, self).__init__(parent)
        self.setWindowTitle("hipcheck — 工程体检与清理")
        self.resize(940, 660)

        self._layer = None
        self._layer_supported = False

        layout = QtWidgets.QVBoxLayout(self)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        layout.addWidget(splitter, 1)

        # 上半：检查
        check_box = QtWidgets.QGroupBox("检查（整个 hip）", self)
        check_layout = QtWidgets.QVBoxLayout(check_box)
        self._check_tree = QtWidgets.QTreeWidget(check_box)
        self._check_tree.setHeaderLabels(["类型", "节点", "参数", "原因"])
        self._check_tree.setRootIsDecorated(False)
        self._check_tree.setAlternatingRowColors(True)
        self._check_tree.header().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeToContents)
        self._check_tree.header().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeToContents)
        self._check_tree.header().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeToContents)
        self._check_tree.header().setSectionResizeMode(
            3, QtWidgets.QHeaderView.Stretch)
        self._check_tree.itemClicked.connect(self._on_check_item_clicked)
        check_layout.addWidget(self._check_tree)
        self._check_label = QtWidgets.QLabel("", check_box)
        check_layout.addWidget(self._check_label)
        splitter.addWidget(check_box)

        # 下半：清理
        clean_box = QtWidgets.QGroupBox("清理（当前这一层）", self)
        clean_layout = QtWidgets.QVBoxLayout(clean_box)
        self._clean_tree = QtWidgets.QTreeWidget(clean_box)
        self._clean_tree.setHeaderLabels(["状态", "节点数", "节点"])
        self._clean_tree.setRootIsDecorated(True)
        self._clean_tree.header().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeToContents)
        self._clean_tree.header().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeToContents)
        self._clean_tree.header().setSectionResizeMode(
            2, QtWidgets.QHeaderView.Stretch)
        self._clean_tree.itemChanged.connect(self._on_clean_item_changed)
        self._clean_tree.itemClicked.connect(self._on_clean_item_clicked)
        clean_layout.addWidget(self._clean_tree)
        self._clean_label = QtWidgets.QLabel("", clean_box)
        clean_layout.addWidget(self._clean_label)
        splitter.addWidget(clean_box)

        # 状态 + 按钮
        self._status = QtWidgets.QLabel("", self)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        buttons = QtWidgets.QHBoxLayout()
        self._rescan_btn = QtWidgets.QPushButton("重新扫描", self)
        self._highlight_btn = QtWidgets.QPushButton("全部高亮", self)
        self._color_btn = QtWidgets.QPushButton("上色", self)
        self._restore_btn = QtWidgets.QPushButton("恢复颜色", self)
        self._delete_btn = QtWidgets.QPushButton("删除", self)
        for button in (self._rescan_btn, self._highlight_btn,
                       self._color_btn, self._restore_btn,
                       self._delete_btn):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._rescan_btn.clicked.connect(self.refresh)
        self._highlight_btn.clicked.connect(self._highlight_all)
        self._color_btn.clicked.connect(self._colorize_checked)
        self._restore_btn.clicked.connect(self._restore_colors)
        self._delete_btn.clicked.connect(self._delete_checked)

        self.refresh()

    # -- 数据 ---------------------------------------------------------------

    def _set_status(self, text):
        self._status.setText(text)

    def _update_delete_state(self, *_args):
        has_groups = self._clean_tree.topLevelItemCount() > 0 and self._layer_supported
        self._delete_btn.setEnabled((not _is_new_file()) and has_groups)

    def refresh(self):
        """重新扫描整个 hip 和当前层。"""
        self._layer = _current_layer()
        errors = []

        # 检查列表
        self._check_tree.clear()
        try:
            issues = scan.check_hip()
        except Exception as exc:
            issues = []
            errors.append("检查失败: %s" % exc)
        for issue in issues:
            item = QtWidgets.QTreeWidgetItem([
                _KIND_LABELS.get(issue.get("kind"), issue.get("kind", "")),
                issue.get("node_path", ""),
                issue.get("parm_name", ""),
                issue.get("reason", ""),
            ])
            item.setData(0, QtCore.Qt.UserRole, issue.get("node_path"))
            item.setToolTip(3, issue.get("reason", ""))
            self._check_tree.addTopLevelItem(item)
        self._check_label.setText("共 %d 条问题" % len(issues))

        # 清理列表
        self._clean_tree.blockSignals(True)
        self._clean_tree.clear()
        self._layer_supported = False
        try:
            result = scan.scan_layer(self._layer)
        except Exception as exc:
            result = {"supported": False, "reason": "清理扫描失败: %s" % exc,
                      "groups": []}
            errors.append("清理扫描失败: %s" % exc)

        self._layer_supported = bool(result.get("supported"))
        if not result.get("supported"):
            reason = result.get("reason") or "这一层不支持清理"
            item = QtWidgets.QTreeWidgetItem(["不支持", "0", reason])
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)
            self._clean_tree.addTopLevelItem(item)
            self._clean_label.setText(reason)
        else:
            groups = result.get("groups", [])
            total_nodes = 0
            for group in groups:
                paths = list(group.get("node_paths", []))
                total_nodes += len(paths)
                item = QtWidgets.QTreeWidgetItem([
                    _STATUS_LABELS.get(group.get("status"), group.get("status", "")),
                    str(len(paths)),
                    "",
                ])
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(0, QtCore.Qt.Checked)
                item.setData(0, QtCore.Qt.UserRole, group)
                for path in paths:
                    child = QtWidgets.QTreeWidgetItem(["", "", path])
                    child.setData(2, QtCore.Qt.UserRole, path)
                    item.addChild(child)
                item.setExpanded(False)
                self._clean_tree.addTopLevelItem(item)
            self._clean_label.setText(
                "共 %d 组 / %d 个节点（当前层 %s）"
                % (len(groups), total_nodes,
                   result.get("layer") or (self._layer.path()
                                           if self._layer else "?")))
        self._clean_tree.blockSignals(False)

        self._update_delete_state()
        if errors:
            self._set_status("；".join(errors))
        elif _is_new_file():
            self._set_status("hip 还没存过盘：删除已禁用，请先保存。")
        else:
            self._set_status("扫描完成。")

    # -- 选中 / 勾选 --------------------------------------------------------

    def _group_items(self):
        for i in range(self._clean_tree.topLevelItemCount()):
            item = self._clean_tree.topLevelItem(i)
            if item.data(0, QtCore.Qt.UserRole) is not None:
                yield item

    def _checked_groups(self):
        groups = []
        for item in self._group_items():
            if item.checkState(0) == QtCore.Qt.Checked:
                group = item.data(0, QtCore.Qt.UserRole)
                if group:
                    groups.append(group)
        return groups

    def _all_group_paths(self):
        paths = []
        for item in self._group_items():
            group = item.data(0, QtCore.Qt.UserRole) or {}
            paths.extend(group.get("node_paths", []))
        return paths

    @staticmethod
    def _paths_in(groups):
        paths = []
        for group in groups:
            paths.extend(group.get("node_paths", []))
        return paths

    # -- 交互 ---------------------------------------------------------------

    def _on_clean_item_changed(self, *_args):
        self._update_delete_state()

    def _on_clean_item_clicked(self, item, _column=0):
        node_path = item.data(2, QtCore.Qt.UserRole)
        if node_path:
            self._jump_to(node_path)

    def _on_check_item_clicked(self, item, _column=0):
        node_path = item.data(0, QtCore.Qt.UserRole)
        self._jump_to(node_path)

    def _jump_to(self, node_path):
        node = scan._as_node(node_path)
        if node is None:
            self._set_status("节点不存在（可能已被删除）：%s" % node_path)
            return
        try:
            node.setSelected(True, clear_all_selected=True)
        except Exception:
            pass

        editor = _network_editor()
        if editor is None:
            return
        try:
            editor.setPwd(node.parent())
        except Exception:
            pass
        try:
            editor.setCurrentNode(node)
        except Exception:
            pass
        try:
            import toolutils
            toolutils.homeToItems([node])
        except Exception:
            pass

    def _highlight_all(self):
        paths = self._all_group_paths()
        if not paths:
            self._set_status("没有可高亮的清理分组。")
            return
        try:
            ok = actions.highlight(paths)
        except Exception:
            self._set_status(traceback.format_exc())
            return
        if ok:
            self._set_status("已高亮 %d 个节点。" % len(paths))
        else:
            self._set_status("当前环境没有网络编辑器，无法高亮。")

    def _colorize_checked(self):
        groups = self._checked_groups()
        if not groups:
            self._set_status("没有勾选任何分组。")
            return
        try:
            count = actions.colorize(groups)
        except Exception:
            self._set_status(traceback.format_exc())
            return
        self._set_status("已上色 %d 个节点。" % count)

    def _restore_colors(self):
        try:
            count = actions.restore_colors(layer=self._layer)
        except Exception:
            self._set_status(traceback.format_exc())
            return
        self._set_status("已恢复 %d 个节点的颜色。" % count)

    def _delete_checked(self):
        if _is_new_file():
            QtWidgets.QMessageBox.warning(
                self, "hipcheck", "当前 hip 还没有存过盘，请先保存后再删除。")
            return
        groups = self._checked_groups()
        paths = self._paths_in(groups)
        if not paths:
            self._set_status("没有勾选任何分组。")
            return
        answer = QtWidgets.QMessageBox.question(
            self, "hipcheck",
            "将删除 %d 个节点，会先备份，确定？" % len(paths),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            backup = actions.backup_then_delete(paths)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "hipcheck", str(exc))
            self._set_status("删除已停止：%s" % exc)
            return
        self._set_status("已备份到 %s，删除 %d 个节点。" % (backup, len(paths)))
        self.refresh()

    # -- 生命周期 -----------------------------------------------------------

    def closeEvent(self, event):
        global _WINDOW
        if _WINDOW is self:
            _WINDOW = None
        super(HipcheckWindow, self).closeEvent(event)


def show(parent=None):
    """打开（或复用）非模态弹窗；再点入口会前置并重扫。"""
    global _WINDOW
    if _WINDOW is not None:
        try:
            _WINDOW.refresh()
            _WINDOW.show()
            _WINDOW.raise_()
            _WINDOW.activateWindow()
            return _WINDOW
        except RuntimeError:
            _WINDOW = None

    if parent is None:
        parent = _main_window()
    _WINDOW = HipcheckWindow(parent)
    _WINDOW.show()
    return _WINDOW
