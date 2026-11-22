# hipcheck HANDOFF

## 当前状态

v1.0.0（2026-11-22）已实现：

- `python/hipcheck/scan.py`：`check_hip()`、`scan_layer()`，无 UI，可在 hython 跑。
- `python/hipcheck/actions.py`：`highlight()`、`colorize()`、`restore_colors()`、`backup_then_delete()`。
- `python/hipcheck/ui.py`：非模态单例弹窗，Qt 只从 `hutil.Qt` 导入。
- `hipcheck.json`（Houdini package）+ `toolbar/hipcheck.shelf`（`hipcheck` shelf 工具）。
- `tests/run_tests.py`：13 项 hython 测试，当前 `ALL PASS 13/13`（Opus 复跑确认）。
- 已安装到本机：`C:/Users/suzyz/houdini21.0/packages/hipcheck.json`（本机 pref 目录不在 Documents 下；packages 文件夹是新建的）。hython 里 `import hipcheck` 正常。
- **等 Kurt 验收**：在 Houdini 界面里点弹窗看外观、跳转、高亮、上色、删除。网络编辑器的高亮/跳转在 hython 测不了，只核对过 API。
- 已知可能慢的地方：引用检查对整个 hip 的每个字符串参数 × 当前层每个节点做匹配，超大工程可能要几秒以上，v1 没做进度条。

## 怎么装

1. 把 `hipcheck.json` 拷到 `$HOUDINI_USER_PREF_DIR/packages`（Windows 通常是
   `C:/Users/<你>/Documents/houdini21.0/packages`）。
2. 重启 Houdini。shelf 里会出现 `hipcheck`，工具按钮执行：
   `import hipcheck.ui; hipcheck.ui.show()`。
3. 快捷键在 Houdini 的 Hotkey Manager 里自己绑到该 shelf 工具上。

`hipcheck.json` 做三件事：

- 设 `HIPCHECK=D:/Kurt/Houdini/tools/hipcheck`
- `PYTHONPATH` append `$HIPCHECK/python`
- `HOUDINI_PATH` append `$HIPCHECK`（让 `toolbar/hipcheck.shelf` 自动载入）

## 怎么测

```
"D:/Program Files/Side Effects Software/Houdini 21.0.512/bin/hython.exe" tests/run_tests.py
```

看最后一行：`ALL PASS n/n` 或 `FAIL k/n`。

测试会在系统临时目录里程序化建场景，不提交 hip 文件。

## hou API 实测结论

- hython 里**没有 `hou.ui`**（`hasattr(hou, 'ui')` 为 False），所以网络编辑器相关的
  跳转/高亮无法在 hython 里做端到端测试；弹窗本身可以构造（见下）。
- 节点 flag：统一用 `node.isGenericFlagSet(hou.nodeFlag.X)`；
  `Display` / `Render` / `Template` / `Footprint` / `Lock` / `SoftLock` 都能读。
  清掉一个 SOP 网络里唯一显示节点的 Display flag 时，Houdini 会自动把别的节点顶上去；
  测试里用一个 `out_display_sink` 哨兵节点占住显示 flag。
- 网络 dot **不在 `node.children()` 里**，但 `node.inputs()` 已经会透明穿过 dot；
  所以清理逻辑不用特殊处理 dot。sticky note、network box 也不是 children。
- 网络编辑器停在 `/obj/geo1` 时，`layer.type().category()` 是 `Object`；
  判断是否 SOP 网络要用 `layer.type().childTypeCategory()`。`/obj` 是 `Object`，
  `/out` 是 `Driver`，都返回“不支持”。
- Houdini 21 的 `NetworkEditor` **没有** `selectNodes()` / `frameSelection()`。
  选中用 `node.setSelected(True, clear_all_selected=...)`，框选用
  `toolutils.homeToItems(nodes)`（实现里已按这个写）。
- `hou.Color` 没有 `.r()` / `.g()` / `.b()`，取分量用 `.rgb()`。
- `hipcheck_orig_color` 里存的是 `{"default": bool, "rgb": [r,g,b]}`：原本是默认色的
  节点恢复时用 `nodeFlag.ColorDefault`（比写死一个灰色更准确），否则用原 RGB。
- File SOP 的 `filemode` 菜单 token 是 `auto` / `read` / `write` / `none`，
  `evalAsString()` 返回 token；File Cache 用 `loadfromdisk` toggle。
- `hou.parmsReferencingThis()` 只返回有 channel 引用的参数；
  `node.dependents()` 还会覆盖 object_merge 这类按名字/路径的依赖，且不含普通输入连线，
  正好对应“输入之外的依赖”。两者都用了。
- 通道表达式里的相对路径是相对**节点自身**（如 `/obj/geo2/holder` 里
  `ch("../../geo1/x/tx")`），但字符串参数里的相对路径可能相对网络层；解析时两种基路径都试。

### 备份实测（saveAsBackup）

- 未设 `$HOUDINI_BACKUP_DIR` 时，默认备份到 `<hip 所在目录>/backup/`，
  文件名 `<hip名>_bak1.hip`、`_bak2.hip`……，返回绝对路径。
- 同一个 hip 连续调两次：得到两个不同文件；第二次调用后第一个备份的**内容快照和
  mtime 都没变**。
- 调用 `saveAsBackup()` **不会修改主 hip 文件**的 mtime / 内容（实测前后
  `st_mtime_ns` 相同）。
- hython 里 `hou.undos.group` / `hou.undos.performUndo()` 可用；上色、删除都能撤销。
- 删除前按 design 的三道保护：先快照备份目录已有文件，返回路径原本存在就停；
  再确认文件真的存在，然后才进撤销组删除。

## 已知限制 / 实现说明

- 清理只支持 SOP 网络；锁住的 HDA 里返回“不支持”，检查部分照常。
- 检查跳过 Manager 网络节点（`/obj`、`/out`、`/stage`、`/tasks` 等）。它们自带
  工具用的 FileReference 参数（例如 `/stage` 的 `rendergallerysource` 默认指向临时
  画廊库），不跳过会每条都误报。这是对 design “扫整个 hip”的一个小的实用化取舍。
- `highlight()` / 网络编辑器跳转的 API 是从本机 Houdini 21 的 `hou.py` 里核对后写的，
  但没能在真实 GUI 里点过（hython 没有 `hou.ui`）。第一次在 Houdini 里用时重点验证一下。
- 多个网络编辑器时，“当前层”优先取当前窗格（如果它是 NetworkEditor），否则取第一个
  NetworkEditor。
- 序列路径用 `%04d` / `$F4` 通配检查；`evalAtFrame()` 会展开 `$F`、`$HIP` 等变量。
- `backup_then_delete()` 在没给节点时直接返回 None（未存盘仍会先拒绝）。
- 备份路径预存在检查发生在 `saveAsBackup()` 返回之后（design 规定的顺序）。

## 下一步（v1 不做，待办照抄 design.md）

- 忽略名单：节点上打“忽略”标记，以后不再报。
- 帧范围前后不一致检查（Kurt 还没想好，实际工作里经常不一致）。
- 其他网络的清理：LOP、DOP、COP、TOP（VOP 要另考虑 Parameter 节点）。
- 停靠面板、网络编辑器右键菜单入口。
