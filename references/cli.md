# 命令行与数据约定

需要确定性检索、证据留档、下载或记录校验时读取本文件。Python 3.10+，仅用标准库。下列命令从技能仓库根目录执行；Codex 从其他目录调用时将 scripts/reuse.py 换成技能安装位置的绝对路径，并使用工作区中的绝对输出路径。

## 搜索

```shell
python scripts/reuse.py search --query "json query language:Python" --query "jmespath language:Python" --limit 5 --pages 1 --out /workspace/reuse-reports/search-01
```

每个 --query 为一组 GitHub REST 仓库搜索词；程序追加 is:public。默认按 GitHub best match 排序，不以 stars 排名。--limit 是每页条数，--pages 是每个查询最大页数。去重不等于穷尽搜索；truncated/incomplete_results 会写入记录。错误保留在 search-results.json，同时生成中文 Markdown 发现列表；该列表不是已经完成的候选评估。

优先用连接的 GitHub 插件发现项目；上述只读 CLI 是没有插件或需要可复现批量记录时的替代。不要重复同一检索只为使用脚本。

## 固定版本与采集证据

```shell
python scripts/reuse.py inspect --repo jmespath/jmespath.py --out /workspace/reuse-reports/inspect-01
```

--ref 可指定 branch/tag/完整 commit；省略时读取实际默认分支。解析成完整 commit 后，所有树和文件请求都使用该 commit。自动读取相关 LICENSE/COPYING/NOTICE/COPYRIGHT、根 README 和常见依赖声明。用重复的 --file 增加实际相关源码，例如 --file jmespath/__init__.py。

输出 inspection.json（含固定 Git 树和证据哈希）、evidence/（原始文本）、review.json（默认 needs_review）。每次最多取 30 份证据，单文件 1 MiB；超限或失败都有 warnings。不是对所有依赖的完整许可审计。

Codex 必须读取相关证据，不把 license_hint 当许可核验结论。将 review.json 补充为：
- intended_use：实际部署/分发和改造用途；
- identifier：读取文本后识别的许可标识，无法判断可保持 null；
- license_files：适用于复用路径的许可证据，保留 path/sha256/url；
- obligations：需遵守的适用条件；
- unresolved：尚未解决的具体事项；
- selection_basis：用户选择或授权自动选择的依据；
- status：仅完成评估、无未决问题时设置 reviewed_for_use。

review 是 Codex/人工语义判断记录，不是法律认证。命令检查版本绑定和哈希，不能自动判定法律兼容性。存在额外目录许可时不能只读根 LICENSE。

## 生成比较报告

读取 examples/assessment.json 了解输入形状；它是格式示例，非已核实项目报告。Codex 按需求比较真实候选后写自己的 assessment.json，再运行：

```shell
python scripts/reuse.py report --assessment /workspace/assessment.json --out /workspace/reuse-reports/comparison-01
```

每个候选需要 fit/gaps/effort、license_status、evidence；每项证据给出 claim、HTTPS url、status（verified/documented/inferred/unknown）。输出 comparison.md 与输入副本。报告只排版已有判断，不自动生成适配结论或热度分数。recommendation 为推荐与理由，decision 默认 awaiting_selection。

## 获取源码

```shell
python scripts/reuse.py acquire --inspection /workspace/reuse-reports/inspect-01/inspection.json --review /workspace/reuse-reports/inspect-01/review.json --dest /workspace/downloads/jmespath-base --report-dir /workspace/reuse-reports/acquisition-01 --method archive
```

--method archive 默认使用 GitHub 固定 commit 归档；可换为 git，执行浅 fetch 和 detached checkout，保留 origin。Git 模式需要 Git，忽略全局 Git 配置、外部过滤器和钩子，禁止交互登录，不递归拉子模块。不自动用个人 Git 凭据；私有仓库优先选择带环境 token 的 archive 模式。

许可 review 必须绑定相同 repo/commit，且已填写用途、选择依据、实际许可文件与未决事项列表。每次都会重新获取固定提交的 Git 树，防止本地 inspection 被编辑后漏检。程序对普通文件比较 Git blob SHA-1，再核对许可 SHA-256。哈希验证确保字节一致，不代表代码安全或可运行。

源码目录和报告目录必须全新、互不包含；已有内容一律不覆盖。归档上限 100 MiB，解包上限 512 MiB/30000 项；拒绝路径穿越、特殊文件、符号链接、Windows 保留名、大小写冲突和 .git 元数据。含符号链接的项目可改用 Git 获取供检查，仍会标为 partial，需后续明确处理。

输出 source-record.json 和初步 development-plan.md。计划只列识别出的配置/入口、许可及待办；Codex 必须读取实际代码，补全需求映射、改动路径和验证步骤后，才能交付为完整二开计划。获取不执行第三方代码。

获取失败会保存 failed 记录和本次已有文件，不清空重试。修复原因后使用新目录；partial 列出缺少的子模块/LFS、未物化链接或不完整树，不能当作“已可运行”。

## 校验来源记录

```shell
python scripts/reuse.py validate --record /workspace/reuse-reports/acquisition-01/source-record.json
```

validate 检查记录字段和状态不变量，不重新联网或重新验证后来修改的源码。获取时的逐文件校验结果保存在 verification.source_checks；二开后保留原始来源记录，另记改动和测试。

## 认证与错误处理

公开仓库可不配置 token。需要提高访问限额或读取获授权的私有仓库时，通过环境变量 GITHUB_TOKEN 提供 token；--token-env NAME 可选择另一个已有环境变量，必须放在子命令之前。GitHub 插件的授权不会自动传给本地脚本。不要把 token 放在命令参数、JSON、报告或 Git URL 中。

HTTP 客户端只有 GET；不包含 push、fork、远程写 API。凭据只发送到 api.github.com，重定向到归档域名时移除。遇到限流输出状态及服务提供的等待提示，不盲目自动重试。

退出码：0 正常完成（仍需检查 warnings/truncated）；2 参数、网络、许可或获取失败；3 源码只获取了一部分。运行状态与功能是否实现是两个维度。

适用范围：github.com；GitHub Enterprise、自定义主机、超限大仓库和外部子模块需要另行选择受控工具，不通过任意 URL 放开凭据边界。
