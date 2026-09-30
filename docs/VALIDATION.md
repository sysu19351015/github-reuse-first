# 1.0.0 验证记录

验证日期：2026-09-30。环境：Windows，Python 3.14.6，Git 2.55.0.windows.2。代码目标为 Python 3.10+ 标准库；本次没有实际执行 Linux/macOS 或 Python 3.10 环境，不将兼容目标当作已实测平台。

## 离线行为测试

```shell
python -m unittest discover -s tests -v
```

37 项测试通过，覆盖：
- 固定版本证据采集、review 默认未审阅；
- 未审阅、缺许可证据、仓库/提交不匹配时拒绝进入源码获取；
- 归档下载成功后的文件哈希与许可哈希；
- 文件内容被改、许可证据不同、树被本地篡改；
- 已有目录保护、报告与源码目录隔离；
- 缺失文件、LFS、子模块、树截断只能报 partial；
- 路径穿越、绝对路径、反斜线、保留名、大小写 .git、大小写冲突、链接、解包限额；
- HTTPS 重定向、跨主机去除认证头、限流不循环重试；
- 搜索分页、去重与失败状态；
- 报告要求证据与中文输出；
- 来源记录关键不变量与归档摘要；
- 安装升级保留旧内容的备份。

## 真实 GitHub 端到端验证

测试对象：[jmespath/jmespath.py](https://github.com/jmespath/jmespath.py)。

固定提交：[2812594e69d43098ef60f81f4efc404c071b0418](https://github.com/jmespath/jmespath.py/commit/2812594e69d43098ef60f81f4efc404c071b0418)，由 develop 分支解析取得。

| 步骤 | 结果 |
| --- | --- |
| 搜索 jmespath language:Python | 取得 3 个去重候选；限定一页，因此如实标记结果截断 |
| inspect | 取得 7 份实际证据，无采集警告 |
| 许可审阅 | 阅读固定版本 MIT 文本，记录保留原始版权及许可声明的条件 |
| archive 获取 | complete，62 个 Git blob 与许可哈希核验通过 |
| git 获取 | complete，62 个 Git blob 与许可哈希核验通过，HEAD 与固定提交一致 |
| 来源记录 | 归档和 Git 方式均生成独立 source-record.json |
| 交接 | 生成入口/依赖配置和初稿，并补充实例的具体改造建议 |

Git 获取首次出现网络失败，程序留下 failed 记录和本次目录；在只读连接检查恢复后，换新目录完整重跑成功。没有覆盖失败现场，也没有无限自动重试。

真实验证仅获取和检查第三方源码，未安装或执行该项目代码。完整性通过不表示第三方功能已实测通过。外部项目的源码未放入本技能仓库，许可证没有改动。

## 复测

从 [CLI 参考](../references/cli.md) 选择全新输出目录执行 search、inspect、report、acquire、validate。要复现相同源码，inspect 时指定上述完整 commit；不要假定分支当前仍指向它。

仅重跑离线测试无需网络、GitHub 凭据或安装第三方包。真实检索/获取受 GitHub 配额、认证与本地网络限制；遇到失败应查看记录，不把失败解释为项目不存在。
