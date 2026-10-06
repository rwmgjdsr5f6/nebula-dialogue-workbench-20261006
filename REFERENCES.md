# references 命令流程说明

本文说明 `dialogue.py` 的 `references` 命令如何得到指定节点的直接入向引用，
仅作文档用途：不新增命令或参数，不改动 `dialogue.py`、现有测试与
`sample.json`，四个既有命令（validate、preview、inspect、references）的
行为保持不变。文中所有结论均可逐项对照源码复核，行号以当前 `dialogue.py`
为准。

## 命令形式

```
python dialogue.py references <文件路径> [--node <节点编号>]
```

`--node` 至多出现一次，且必须是 `--node <值>` 分写形式。省略 `--node`
时查询 `start` 指定的节点；显式给出的节点编号按原字符串精确匹配，
首尾空白不被裁剪（`dialogue.py:238` 直接使用参数原值，未做 `strip()`）。

## 处理流程与源码对应

`references` 的一次执行按以下先后关系进行，每步对应现有函数：

1. **参数检查**：`main()`（`dialogue.py:308`）在 `dialogue.py:326-330`
   分发到 references 分支，先确认至少有文件路径，再调用
   `parse_references_args()`（`dialogue.py:272-282`）解析 `--node`。
   该函数只接受 `[]` 或 `['--node', '值']` 两种形态；任何多余、重复、
   缺值或 `--node=编号` 连写形式都在**读取文件之前**调用
   `fail(REFERENCES_USAGE)`。`fail()`（`dialogue.py:41-44`）向标准错误
   写一条说明并以退出码 2 结束，不输出调用栈。`REFERENCES_USAGE`
   （`dialogue.py:32-34`）是包含全部四条命令的完整用法文字。
2. **读取文件**：`cmd_references()`（`dialogue.py:229`）首先调用
   `load_dialogue(path)`（`dialogue.py:52-68`）。该函数依次尝试：
   以二进制读取文件（`OSError` 报“无法读取文件”）、按 UTF-8 解码
   （`UnicodeDecodeError` 报“UTF-8 解码失败”）、`json.loads` 解析
   （`JSONDecodeError` 报“JSON 语法错误”，消息含第几行第几列）。
   三类失败都经 `fail()` 以退出码 2 结束。
3. **整份校验**：`cmd_references()` 随后调用
   `validate_dialogue(data)`（`dialogue.py:71-138`），对整份对话数据
   （含无法从起点到达的节点）做结构校验与引用校验；失败时抛出
   `DialogueError`，由 `cmd_references` 捕获后以
   `fail("校验失败：…")` 报告，说明中带 JSON 字段位置（如
   `nodes[3].text`）。校验先于任何节点查找，因此即使查询的编号本身
   不存在，只要文件结构非法，也先报校验失败。
4. **节点查找**：校验通过后，`cmd_references` 在
   `dialogue.py:238` 确定目标编号（省略 `--node` 时取 `start`，否则取
   参数原值），并用 `find_node()`（`dialogue.py:141-145`）按字符串相等
   逐个比对 `node["id"]`。找不到时以
   `fail("文件中不存在编号为 {!r} 的节点")` 报告，消息中包含该编号原值。
5. **收集引用并输出**：`dialogue.py:245-253` 按 `nodes` 数组顺序遍历
   每个节点，再按各自 `options` 数组顺序遍历选项，`target` 与目标编号
   相等即追加一条 `{"source": 节点 id, "choice": 选项序号, "text": 选项
   文字}`；`choice` 从 1 开始（`i + 1`）。最终
   `dialogue.py:254-255` 把 `{"id": 目标编号, "references": [...]}` 以
   `json.dumps(..., ensure_ascii=False)` 单行写出，末尾加一个换行。

## 结果语义

- 只统计各节点 `options` 里的**直接**引用，不沿循环或链式关系展开
  间接引用（`dialogue.py:246-248` 只做一层 `target == target_id` 比较）。
- 覆盖整份文件，**不可达来源**照常计入。
- 同一来源的**多个选项逐项保留**，各自独立成条。
- **自引用**（选项指向所在节点自身）照常计入。
- `start` 字段本身**不算**引用，只有 `options[].target` 参与统计。
- 结果按 `nodes` 顺序及各自 `options` 顺序排列，`choice` 从 1 开始。

## 完整示例

以下示例文件仅在本文档中展示，仓库自带的 `sample.json` 保持原样。
它在 `sample.json` 三个节点之后追加一个文字为“旁路”的 `side` 节点，
其三个选项依次为“甲”指向 `forest`、“乙”指向 `forest`、“原地”指向
`side`（`side` 从 `start` 不可达，且含自引用）：

```json
{
  "start": "start",
  "nodes": [
    {
      "id": "start",
      "text": "你来到岔路口。",
      "options": [
        { "text": "向左走", "target": "forest" },
        { "text": "向右走", "target": "river" }
      ]
    },
    {
      "id": "forest",
      "text": "你到了森林。",
      "options": []
    },
    {
      "id": "river",
      "text": "你到了河边。",
      "options": []
    },
    {
      "id": "side",
      "text": "旁路",
      "options": [
        { "text": "甲", "target": "forest" },
        { "text": "乙", "target": "forest" },
        { "text": "原地", "target": "side" }
      ]
    }
  ]
}
```

设该文件保存为 `example.json`。

查询 `forest` 的入向引用：

```
python dialogue.py references example.json --node forest
```

预期输出（标准输出为单行 JSON 加结尾换行，退出码 0，标准错误为空）：

```json
{"id": "forest", "references": [{"source": "start", "choice": 1, "text": "向左走"}, {"source": "side", "choice": 1, "text": "甲"}, {"source": "side", "choice": 2, "text": "乙"}]}
```

依次为 `start` 的选项 1、`side` 的选项 1 和 2：结果按 `nodes` 顺序
（`start` 在 `side` 之前）及各自 `options` 顺序排列，`side` 的“甲”“乙”
两个选项逐项保留，不可达的 `side` 照常计入。

查询 `side` 的入向引用：

```
python dialogue.py references example.json --node side
```

预期输出：

```json
{"id": "side", "references": [{"source": "side", "choice": 3, "text": "原地"}]}
```

仅含 `side` 的选项 3：自引用照常计入；`start` 字段指向 `start` 不算
引用，也没有任何选项指向 `side` 之外再间接指回，不做展开。

## 确定的失败结果

所有失败均为：退出码 2、标准输出为空、标准错误无调用栈（由
`fail()`，`dialogue.py:41-44` 统一保证）。所有成功均为：退出码 0、
标准错误为空、标准输出为单行 JSON 加一个结尾换行，且输入文件字节
不变（程序只读文件，从不写入）。

- **重复 `--node`**（以及其他参数格式错误：缺文件路径、`--node` 缺值、
  未知参数、额外位置参数、`--node=编号` 连写）：在**读取文件之前**
  由 `parse_references_args()` 拒绝，标准错误输出 `REFERENCES_USAGE`
  完整用法文字加一个换行，即：

  ```
  用法：
    python dialogue.py validate <文件路径>
    python dialogue.py preview <文件路径> --choice <选项编号> [--node <节点编号>]
    python dialogue.py inspect <文件路径> [--node <节点编号>]
    python dialogue.py references <文件路径> [--node <节点编号>]
  ```

  即使文件路径不存在或文件内容非法，参数格式检查也优先，不会变成
  文件类错误。

- **合法参数下的文件类失败**（`load_dialogue`，`dialogue.py:52-68`）：
  - 无法读取文件（如路径不存在）：`无法读取文件 <路径>：<原因>`；
  - UTF-8 解码失败：`文件 <路径> 的 UTF-8 解码失败：<细节>`；
  - JSON 语法错误：`文件 <路径> 存在 JSON 语法错误（第 <行> 行第 <列>
    列）：<说明>`，含行列位置。

- **校验失败先于节点查找**：若把上面示例中的 `side` 节点改为缺少
  `text` 字段（其余不变），即使查询一个不存在的编号：

  ```
  python dialogue.py references example_bad.json --node missing
  ```

  也先由整份校验报告 `校验失败：缺少字段 nodes[3].text`（`side` 是
  `nodes` 的第 4 个节点，下标为 3），不会进入节点查找，标准错误中
  不出现“不存在”。

- **节点不存在**：文件合法但查询的编号不存在时（如对合法文件查询
  `missing`），报告 `文件中不存在编号为 'missing' 的节点`，消息中
  包含该编号原值。
