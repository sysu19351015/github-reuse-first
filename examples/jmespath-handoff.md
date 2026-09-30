# 实例：JSON 查询工具的源码复用交接

这是 2026-09-30 对真实源码获取流程的验证实例，不是对当前所有 JSON 查询项目的全面排名，也不意味着已经完成用户的产品开发。

基底：[jmespath/jmespath.py 固定提交 2812594e69d43098ef60f81f4efc404c071b0418](https://github.com/jmespath/jmespath.py/tree/2812594e69d43098ef60f81f4efc404c071b0418)。

## 为什么适合作为实例

[实际入口](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/jmespath/__init__.py) 提供 search(expression, data, options) 和 compile(expression)，将表达式交给 parser，再对传入的 Python 数据执行查询。[README](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/README.rst) 给出了对象字段、列表索引与编译查询的示例。入口实现已读取，完整行为未在本次运行验证。

[MIT 许可](https://github.com/jmespath/jmespath.py/blob/2812594e69d43098ef60f81f4efc404c071b0418/LICENSE) 已读取；复制或分发相关源码时需保留原版权及许可声明。该判断限定于本次源码获取与 JSON 查询复用示例，不涵盖未知第三方依赖。

## 最小改造计划

| 需求 | 已有能力 | 拟议工作 |
| --- | --- | --- |
| 对 JSON 输入执行表达式查询 | jmespath.search 入口 | 优先在独立工具层调用现有库 |
| 同一表达式反复查询 | jmespath.compile 入口 | 在调用层保留编译结果，验证复用行为 |
| 从文件/标准输入读取 JSON | 核心入口接收已经解析的数据 | 新增工具输入层，明确编码和解析错误 |
| 插件宿主接入 | 本次未确认任何指定宿主接口 | 明确宿主后单独实现适配层，不先改解析器 |
| 自定义表达式语法 | 入口调用 jmespath/parser.py | 只有确需扩展语言时才评估解析器改动 |

实施顺序：先用库依赖封装最小命令入口；再补 JSON 输入与错误呈现；按实际宿主接入；仅在原语法确实不满足时修改上游解析实现。是否复制上游或直接依赖库由具体需求决定。

验收方案：字段查询、列表投影、空值/无匹配、非法 JSON、非法表达式、同一已编译表达式多次使用，以及退出码和错误输出。上述为待实施验证，不是已执行测试。

## 来源与运行状态

archive 和 git 两种获取均核对 62 个普通文件的 Git blob 及许可 SHA-256，完整性状态 complete。Git 获取采用浅历史、固定 HEAD；未自动递归获取外部资源。安装、启动及第三方功能测试未运行。

实际任务需要继续把计划里的适配层名称和路径落实到用户项目，再执行测试；不能将此实例直接当作任意项目的完整二开方案。
