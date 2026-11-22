# Changelog

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
