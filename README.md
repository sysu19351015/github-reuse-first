# GitHub Reuse First

开发插件或工具前，先找已有开源实现，再决定直接使用、封装、修改源码，还是自行开发。

这是一个可安装到 Codex 的中文 Skill，包含工作流说明、Python 命令行工具、可追溯的源码获取、报告生成和离线测试。**不是根据 stars 自动挑选代码并执行的安装器**；功能适配和许可用途由 Codex 阅读证据后判断。

## 快速使用

环境：Python 3.10+；无第三方 Python 依赖。Git 只在使用 Git 获取方式时需要。

取得本仓库后，在根目录执行：

```shell
python scripts/install.py
```

默认安装到 $CODEX_HOME/skills/github-reuse-first；未设置 CODEX_HOME 时使用 ~/.codex/skills/github-reuse-first。已有版本时：

```shell
python scripts/install.py --upgrade
```

升级先保留旧目录的时间戳备份，默认放在 ~/.codex/skill-backups，避免旧 Skill 被重复发现。--dest 可指定自定义完整技能目录。安装后打开能发现该技能的 Codex 任务，使用：

> 请用 $github-reuse-first 帮我找实现离线 PDF 批注插件的开源项目，比较适配程度和改造量，先不要下载。

选定项目后：

> 选第二个项目，把源码获取到当前工作区的新目录，给我具体的二次开发计划。

也可以一次授权：

> 请用 $github-reuse-first 为我的 JSON 查询工具选择合适的 Python 开源基底，核实许可证后获取源码，并开始实现我列出的功能。

Skill 优先使用已连接的 GitHub 插件；命令行工具提供可复现的只读查询和下载。插件登录态与本地脚本认证分离，公开仓库脚本可无 token 使用。需要私有访问或更高配额时，用环境变量 GITHUB_TOKEN，不将凭据写进文件。

## 能完成什么

| 阶段 | 行为 | 结果 |
| --- | --- | --- |
| 需求整理 | 提取功能、平台、宿主、技术栈、许可用途 | 搜索词和明确约束 |
| 仓库发现 | 中英文同义词、生态词检索，去重并记录范围 | 带查询记录的候选清单 |
| 证据与比较 | 固定 commit，读取源码、文档、许可，区分事实与推断 | comparison.md |
| 获取源码 | GitHub 归档或浅 Git 获取，不执行第三方代码 | 新目录中的源码 |
| 来源校验 | 普通文件逐个对照 Git blob，许可文件核对 SHA-256 | source-record.json |
| 二开交接 | 定位扩展点，补全需求映射、修改路径与验证方法 | development-plan.md；按授权继续实现 |

搜索、代码读取、报告和源码获取命令的参数与示例见 [命令参考](references/cli.md)。源码记录和完整性语义见 [输出约定](references/outputs.md)。

## 命令速览

从仓库根目录执行，下列相对输出路径只是独立 CLI 的例子；Codex 调用时使用用户工作区的绝对路径。

```shell
python scripts/reuse.py search --query "jmespath language:Python" --out reuse-reports/search-01
python scripts/reuse.py inspect --repo jmespath/jmespath.py --out reuse-reports/inspect-01
```

读取 inspect-01/evidence 中的文本，按实际用途补全 review.json。只有证据充分且无未决问题时设置 reviewed_for_use，再获取：

```shell
python scripts/reuse.py acquire --inspection reuse-reports/inspect-01/inspection.json --review reuse-reports/inspect-01/review.json --dest downloads/jmespath-base --report-dir reuse-reports/acquisition-01
python scripts/reuse.py validate --record reuse-reports/acquisition-01/source-record.json
```

生成比较报告：

```shell
python scripts/reuse.py report --assessment examples/assessment.json --out reuse-reports/format-example
```

最后一条仅展示报告格式；examples/assessment.json 没有真实适配结论。实际任务由 Codex 先完成有来源的候选判断。

## 约束与失败状态

- 只要求调研时不下载；已有选型和获取授权时不重复确认。
- 公开仓库不等于已获复用许可；没有许可证时不默认适合二开。
- 不覆盖已有源码或报告目录，不运行下载项目的安装/启动脚本。
- complete 只表示所核对源码范围完整；partial 列出子模块、LFS、链接或树截断等缺失；failed 保存失败原因。以上均不表示功能已运行通过。
- 归档默认上限为下载 100 MiB、解包 512 MiB、30000 项。单份证据 1 MiB、单次最多 30 份；超限如实说明。
- 本地 Git 模式禁用全局配置和交互凭据，使用浅历史；私有仓库建议 token + archive。
- 所有远程写操作由已连接的 GitHub 插件承担；脚本只读，不提供 git push。
- 普通 GitHub 托管仓库受支持；Enterprise 主机未实现。

## 目录与开发

```text
SKILL.md                  Codex 工作流入口
agents/openai.yaml        技能名称与调用示例
scripts/reuse.py          search / inspect / report / acquire / validate
scripts/reuse_common.py   只读 HTTP、路径与数据工具
scripts/reuse_discovery.py 检索与固定版本证据
scripts/reuse_acquisition.py 获取、哈希校验与来源记录
scripts/reuse_reporting.py 比较报告生成
scripts/install.py        安装与带备份的升级
references/               架构、评估、获取、CLI、输出约定
examples/assessment.json  可编辑的报告输入示例
tests/test_reuse.py       不联网的行为与安全边界测试
docs/VALIDATION.md        实测记录与已知限制
```

```shell
python -m unittest discover -s tests -v
python scripts/reuse.py --help
```

测试只使用临时目录和模拟 HTTP，不访问 GitHub，不执行下载的第三方源码。实测范围见 [验证记录](docs/VALIDATION.md)。

## 参考与许可

- [GitHub 搜索 API](https://docs.github.com/en/rest/search/search#search-repositories)
- [GitHub 源码归档 API](https://docs.github.com/en/rest/repos/contents#download-a-repository-archive-zip)
- [OpenAI Skill 结构](https://developers.openai.com/plugins/build/skills)

本项目采用 [MIT License](LICENSE)。下载的第三方项目仍遵守其各自的许可证。
