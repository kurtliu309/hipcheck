# Changelog

## v1.0.1 — 2026-11-22

在 Kurt 的 Houdini 界面里用示例场景实测后修的问题。

- 修：HDA 内部节点引用自己参数（如 H21 的 Color SOP），被当成外部引用，节点被误保留。现在引用来自节点自身或其内部时不算。
- 修：检查误报。跳过锁住的 HDA 内部节点（如 File Cache 里的 read_back、topnet）；跳过灰掉、隐藏、还是出厂默认值的文件参数（如 scatter 的 `default.pic`）；相对路径也到 Houdini 搜索路径里找。
- 修：窗口单例存在 `hou.session` 上，模块重新加载后也不会出现第二个窗口；`closeEvent` 改用 `super()`。
- 改：删除后状态栏保留“已备份到 …，Ctrl+Z 可撤回”，不再被“扫描完成”盖掉。
- 装：package 改装到界面版 Houdini 真正用的 pref 目录 `OneDrive/文档/houdini21.0/packages`。
- 测试 15 项（新增 HDA 自引用、检查误报两项，撤掉修复时都会失败）。
- 界面实测通过：弹窗、检查跳转、全部高亮、上色、删除确认框、备份（新建 bak2，bak1 和主 hip 不动）、一步撤销。

## v1.0.0 — 2026-11-22

首个版本。

- 检查（整个 hip）：FileReference 读路径断链（当前帧 / 全局首尾帧，序列路径支持通配）、写死的绝对路径（盘符 / `//` / `\\`）。
- 清理（当前 SOP 层）：按终点（显示/渲染/template/footprint flag、`out*` 名字、写文件节点、锁定、注释、被引用）沿输入往上游 BFS；剩下节点按连通性分成“漂浮”（紫）和“没用分支”（黄）。
- 引用检测：Houdini 原生依赖 `dependents()` / `parmsReferencingThis()`，加上字符串里的完整路径、相对路径、`op:`、NodeReference 参数；整个 hip 范围查。
- 动作：全部高亮（选中 + 网络编辑器框住）、上色、恢复颜色（原色存 userData，存盘再开可恢复）、备份后删除。上色、恢复、删除各自一个撤销组。
- 删除前用 `hou.hipFile.saveAsBackup()` 备份，带三道保护；从未存盘的 hip 拒绝删除。
- 非模态单例弹窗，`hutil.Qt` 导入 Qt；上半检查列表、下半可展开的清理分组（默认全勾）。
- Houdini package `hipcheck.json` 和一个 `hipcheck` shelf 工具。
- hython 测试 13 项。
