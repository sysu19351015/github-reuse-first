# 同类技能调研与改进依据

检索日期：2026-10-22（Asia/Shanghai）。需求：核查与 github-reuse-first 相近的技能，改进现有技能，保持 GitHub 插件优先和只读 CLI 的边界。

## 检索范围和证据

使用已连接 GitHub 插件的公开仓库搜索，查询 `github-reuse-first`，返回首批 10 个结果；并用公开网页检索 `github skill search reuse existing repositories before coding plugin`、`site:github.com "search-first" "SKILL.md"` 补充发现。并非全站穷尽检索，插件搜索未提供总量/完整性标记。深入检查以下三个相关仓库的 main 提交、完整 Git 树和技能入口；另读 py-sit 的元数据脚本与查询参考。仅读取文件，未获取完整源码、安装或执行第三方项目。额外探查 everything-claude-code 的技能及许可文件未返回可读内容，未将其纳入判断。

## 候选比较

| 项目及固定版本 | 已核实能力 | 差距与接入成本 | 许可判断 | 版本维护证据 | 决策 |
| --- | --- | --- | --- | --- | --- |
| [py-sit/github-search-skill](https://github.com/py-sit/github-search-skill/tree/775b834142ab8b819df6315bb90ddc364ce534ad) | 技能定义搜索简报、候选表、接入风险；Python 脚本收集根目录、README 和仓库元数据 | 偏调研与克隆；未发现与本技能同等的固定版本获取/逐文件校验流程。Shell 克隆路径绑定作者 macOS 目录，直接替换成本中 | needs_review：完整树未发现 LICENSE/COPYING/NOTICE；脚本和技能未见许可授权声明 | 所读 main 提交日期 2026-03-19；不据此认定失修 | 仅借鉴搜索投入和接入成本的评估思路 |
| [nguyenquan27122005-cmd/github-first-reuse](https://github.com/nguyenquan27122005-cmd/github-first-reuse/tree/24510f0ded62af621b3a6156d42696293d88a4a2) | 技能定义本地能力优先、组件缺口、搜索投入、基线与最小端到端验证 | 主要是工作流文档；树中测试属于包装测试，未见本技能的来源获取工具。替换会丢失现有 CLI，成本中 | needs_review：完整树未发现许可文件，技能入口未见许可授权声明 | 所读 main 提交日期 2026-10-19；未审查长期 issue/CI 状态 | 仅借鉴组件级选型、总成本和实施验证思路 |
| [L1SC/Codex-github-reuse-first](https://github.com/L1SC/Codex-github-reuse-first/tree/0e294e0a2690a417777585a34d4dfd5e1c727bf0) | 技能定义维护、部署、技术栈、许可及 MVP 比较 | 每次编码前确认、每次获取前确认，范围宽且重复打断已授权工作；未见获取/校验脚本。直接替换成本中高 | needs_review：完整树无许可文件，技能入口未见许可授权声明 | 所读 main 提交日期 2026-09-08；未审查 CI/发布记录 | 不引入其强制确认流程 |

这些是可见的相近 Skill，不代表均为可直接安装的独立插件。上述判断来自文件阅读；未运行候选项目，也未声称完整完成依赖许可审计。未发现明确许可授权不能解释为允许复制、改造和分发。

## 复用决定与实现映射

选择：保留当前技能，仅借鉴设计；本次内容独立编写，不复制第三方文件，不新增依赖。用户已授权更新技能及自己的对应仓库，无须另选外部基底或下载候选项目。

| 本次识别的缺口 | 更新路径 | 预期行为 |
| --- | --- | --- |
| 未明确先核查已有实现与依赖 | SKILL.md、references/discovery.md | 先定位缺口；用户明确要求外部检索时仍检索 |
| 组件选择容易扩大为整项目 | 同上 | 库/SDK/扩展点与整项目基底分别检索 |
| 搜索投入只有笼统轮数 | references/discovery.md | 默认投入随任务规模调整，补查只围绕影响决策的问题 |
| 接入成本未明确覆盖后续维护 | SKILL.md、references/discovery.md、references/outputs.md | 比较依赖、服务、上游升级、替换和迁移成本 |
| 实施验证缺少基线与纵向验收 | SKILL.md、references/outputs.md | 原始基线与最小端到端结果分别记录；交接任务只列建议 |

保留：按授权继续实施、固定 commit、许可用途判断、逐文件来源校验、GitHub 远程写操作仅通过连接插件。CLI 和数据格式未变。

## 行为检查场景

- 普通本地修复且现有依赖可满足：直接修复，不额外搜索。
- 用户明确要求比较同类技能：完成外部检索，即使本地已有实现。
- 只缺 CSV 解析组件：优先库或平台能力，避免整套应用。
- 已授权选型并实施：记录原始基线，验证最小用户流程后继续，不新增确认门。
- 只要求比较/交接：输出结论或验证计划，不运行候选代码。
- 无许可文件：保留 needs_review，不导入第三方内容。

以上为静态行为走查，非独立代理实测；当前仓库离线测试与技能格式校验结果以本次交付的验证记录为准。
