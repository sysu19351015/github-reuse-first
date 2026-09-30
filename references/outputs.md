# 输出与阶段交接约定

以下是输出约定，不是已执行记录。按实际填写，无证据的字段用 `null` 或“未知”，不编造仓库、SHA、许可证和测试结果。

## 输出位置

简单比较可在对话交付。涉及源码获取、跨轮选型或二开时，在工作区建立唯一的 `reuse-reports/任务标识/`，写入适用文件：

```text
comparison.md           检索与选型报告
source-record.json      获取后写入；失败也保留状态和原因
development-plan.md     源码检查后的改造与验证计划
```

小型调研不必建目录；不写入技能目录，不覆盖不相关报告。

## comparison.md

包括需求与假设；检索日期、查询词、范围及限制；候选比较；推荐路径、缺口和下一步选择。

比较表建议列：项目链接、已核实能力、需求差距、技术栈、许可证判断、维护证据、改造量、建议。按决策需要增减字段，不用推测填满表格。

影响推荐的核心断言附源码/文档/许可链接，优先固定 commit 链接。区分事实、文档宣称、推断和待验证事项。star 和日期等时间敏感数据附查询时间。

决策记录保留：选定仓库、复用模式、选择原因、未解决问题、用户选定或自动选型授权的上下文。未选定时写 `awaiting_selection`。

## source-record.json

小型 JSON 记录，采用 `schema_version: 1` 便于后续脚本读取。scripts/reuse.py validate 校验核心字段与状态不变量；数据含义和命令见 [cli.md](cli.md)。

| 字段 | 类型与约定 |
| --- | --- |
| `schema_version` | 整数 1 |
| `repository_url` | 已核实仓库 URL |
| `requested_ref` | 用户指定或说明过的 branch/tag/commit，未知为 null |
| `resolved_commit` | 完整 commit SHA，进入源码获取前必须确定 |
| `retrieved_at` | ISO 8601 时间，含时区 |
| `method` | git_clone / commit_archive / file_subset |
| `local_path` | 源码绝对路径 |
| `status` | complete / partial / failed |
| `missing_items` | 未获取的必要文件、子模块、LFS 内容列表 |
| `failure_reason` | 失败或受限原因，没有为 null |
| `archive_sha256` | 归档本地 SHA-256，其余为 null |
| `license` | 对象：status、identifier、files、obligations、unresolved |
| `selection_basis` | 用户选择或自动选型依据，不复制隐私聊天内容 |
| `verification` | 对象：source_checks 与 runtime_checks，记录检查、结果或未执行原因 |

`license.status` 使用 discovery.md 的三种状态，`identifier` 只填实际识别的许可标识。`files` 记录路径、适用范围、固定版本链接；`obligations` 和 `unresolved` 是字符串列表。

来源已核验、commit 已确定且所选范围完整才可标 `complete`。`file_subset` 永远为 `partial`。源码完整不代表运行通过，也不要求已有全部 Git 历史，历史深度另记在 `verification.source_checks`。

## development-plan.md

按项目实际覆盖：

1. 上游仓库、固定版本、源码目录、选型原因、许可条件。
2. 功能对应：已有能力 → 用户需求 → 直接复用/修改/新增。
3. 入口文件、复用模块、扩展接口、具体改动路径。
4. 最小可用范围、实现顺序、保留跟踪上游的方式。
5. 安装、构建、测试、用户关键流程的验证方法，分清建议运行与已运行结果。
6. 未解决差距、缺失文件、环境条件、需要用户决定的事项。

仅要求准备时交付可接手的源码和计划；已要求实际开发时计划是中间产物，继续实现并更新验证结果。

inspect 额外生成 inspection.json、evidence/ 与 review.json。search 生成 search-results.json 与 search-results.md；report 保存 assessment.json 及 comparison.md。每一步使用不同的新子目录，按同一任务标识组织，不覆盖已存在输出。source_checks 中记录 git_blobs_verified、license_hashes_verified、tree_truncated，以及 Git 方式的 HEAD/remote/浅历史说明；runtime_checks 单独标识未运行或实际运行结果。
