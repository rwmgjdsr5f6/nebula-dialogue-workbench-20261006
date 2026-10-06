# references 命令：直接入向引用查询说明

本文档只说明 `dialogue.py` 现有的 `references` 命令如何就一份对话文件得到指定节点的**直接入向引用**，并把参数检查、读取文件、整份校验、节点查找、结果输出五个阶段对应到现有函数与源码行号，便于逐项复核。

- 本文档不新增命令或参数，不修改业务源码、现有测试与 `sample.json`；`validate`、`preview`、`inspect`、`references` 四个既有命令的行为保持不变。
- 文中第 7 节的四节点示例**仅在本文档中展示**，不写入仓库；仓库自带的 `sample.json`（三个节点）保持原样。

命令形式（`dialogue.py:8`、`dialogue.py:326-330`）：

```
python dialogue.py references <文件路径> [--node <节点编号>]
```

## 1. 执行流程（五个阶段的先后关系）

入口 `main` 在识别出 `references` 后，先检查文件路径是否存在（`dialogue.py:327-328`），再调用参数解析与命令函数。完整顺序如下，前一阶段失败就以退出码 2 结束，**不会**进入后续阶段：

| 顺序 | 阶段 | 现有函数与源码位置 | 失败时的处理 |
| --- | --- | --- | --- |
| 1 | 参数检查 | `main`（`dialogue.py:326-330`）→ `parse_references_args`（`dialogue.py:272-282`） | 任何格式错误调用 `fail(REFERENCES_USAGE)`（`dialogue.py:282`），**发生在读取文件之前** |
| 2 | 读取文件 | `cmd_references` 调用 `load_dialogue`（`dialogue.py:231`；函数体 `dialogue.py:52-68`） | 读取、UTF-8 解码、JSON 解析三类错误分别在 `dialogue.py:59`、`dialogue.py:63`、`dialogue.py:67-68` 报告 |
| 3 | 整份校验 | `cmd_references` 调用 `validate_dialogue`（`dialogue.py:232-235`；函数体 `dialogue.py:71-138`） | 抛出 `DialogueError` 后报告“校验失败：……”（`dialogue.py:234-235`），**先于节点查找** |
| 4 | 节点查找 | 确定目标编号后调用 `find_node`（`dialogue.py:238-240`；函数体 `dialogue.py:141-145`） | 找不到时报告节点不存在（`dialogue.py:240`） |
| 5 | 结果输出 | 遍历收集后写标准输出（`dialogue.py:245-255`） | 成功路径，不写文件 |

`fail` 是所有失败的统一出口：向标准错误写入消息加一个换行并 `sys.exit(2)`，不输出调用栈（`dialogue.py:41-44`）。

### 1.1 阶段 1：参数检查（读取文件之前）

`parse_references_args`（`dialogue.py:272-282`）只接受两种形态：

- 文件路径之后无其他参数：`[]` → 返回 `None`（`dialogue.py:278-279`）；
- 恰好是 `--node <编号>`：长度为 2 且第一个记号是 `--node` → 原样返回编号字符串（`dialogue.py:280-281`）。

其余一切形态都在 `dialogue.py:282` 以用法错误拒绝，包括：`--node` 缺值、重复出现 `--node`（即使两次值相同）、`--node=编号` 连写、未知参数（如 `--choice`）、额外位置参数。此外，连文件路径都缺失时由 `main` 在 `dialogue.py:327-328` 直接拒绝。这些检查都不触碰文件，因此即使路径不存在或文件内容是损坏的 JSON，重复 `--node` 等错误仍只报用法（见第 8.1 节）。

### 1.2 阶段 2：读取文件

`load_dialogue`（`dialogue.py:52-68`）严格按三步处理，错误分类固定：

1. 以二进制只读方式打开（`dialogue.py:55`，`open(path, "rb")`）；`OSError` 报告“无法读取文件 ……”（`dialogue.py:57-59`）；
2. 按 UTF-8 解码（`dialogue.py:61`）；`UnicodeDecodeError` 报告“UTF-8 解码失败……”（`dialogue.py:62-63`）；
3. `json.loads` 解析（`dialogue.py:65`）；`json.JSONDecodeError` 报告“JSON 语法错误（第 X 行第 X 列）：……”，行列来自异常的 `lineno`、`colno`（`dialogue.py:66-68`）。

### 1.3 阶段 3：整份校验

`validate_dialogue`（`dialogue.py:71-138`）校验**整份**数据：第一遍逐个检查全部节点及其选项的结构与重复编号（`dialogue.py:96-126`），第二遍检查 `start` 与每个 `target` 的引用是否存在（`dialogue.py:128-136`）。校验覆盖无法从起点到达的节点——它们的结构错误一样会暴露。校验成功返回 `(start, nodes)`（`dialogue.py:138`）。

### 1.4 阶段 4：节点查找

`cmd_references` 先确定目标编号（`dialogue.py:238`），再用 `find_node` 按节点在 `nodes` 中的出现顺序做相等查找（`dialogue.py:141-145`、`dialogue.py:239`）。由于阶段 3 已保证 `start` 与全部 `target` 都存在，省略 `--node` 时这一步必然成功；只有显式给出的编号可能找不到。

### 1.5 阶段 5：收集并输出结果

收集逻辑在 `dialogue.py:245-253`，输出在 `dialogue.py:254-255`，规则见第 3、4 节。

## 2. 目标节点编号的确定与匹配

- **省略 `--node`**：查询顶层 `start` 字段指定的节点（`dialogue.py:238`，`start` 来自 `validate_dialogue` 的返回值）。
- **显式编号按原字符串匹配**：`--node` 后的值由 `parse_references_args` 原样返回（`dialogue.py:281`），`find_node` 用 `node["id"] == node_id` 精确比较（`dialogue.py:143`），引用匹配同样是 `option["target"] == target_id`（`dialogue.py:248`）。
- **首尾空白不被裁剪**：全程没有对命令行编号做 `strip`。因此 `--node " forest"` 只会匹配编号字面量就是 `" forest"` 的节点，不会匹配 `"forest"`；反过来 `"forest"` 也不匹配 `" forest"`。（`is_id_string` 中的 `strip()` 只用于判断编号是否至少含一个非空白字符，见 `dialogue.py:47-49`，不参与查找比较。）

## 3. 直接入向引用的统计规则

入向引用是指：某节点的某个选项的 `target` 恰好等于目标节点编号。`dialogue.py:245-253` 的双重循环确定了以下行为：

1. **只统计直接引用**：只比较每个选项自身的 `target`（`dialogue.py:248`），不沿指向关系继续追踪，**不沿循环展开间接引用**。
2. **包含不可达来源**：外层遍历整份 `nodes`（`dialogue.py:246`），不以“能否从 `start` 到达”做任何过滤；不可达节点里指向目标的选项同样列出。
3. **同一来源的多个选项逐项保留**：内层逐个遍历 `options`（`dialogue.py:247`），同一节点有几个选项指向目标，结果里就有几条，不会合并或去重。
4. **自引用照常计入**：选项 `target` 等于其所属节点自身编号时没有特殊排除，照样输出（比较仍发生在 `dialogue.py:248`）。
5. **`start` 字段本身不算引用**：扫描范围仅限各节点的 `options`（`dialogue.py:246-247`）；顶层 `start` 只是查询省略 `--node` 时的目标编号来源（`dialogue.py:238`），不作为引用条目。
6. **顺序**：外层按 `nodes` 数组顺序，内层按各节点 `options` 数组顺序（`dialogue.py:246-247`）。
7. **`choice` 从 1 开始**：值为选项在其所属节点 `options` 中的下标加 1（`dialogue.py:251`，`i + 1`），与该选项是否指向目标无关。

每条结果包含三个字段：`source`（来源节点编号，`dialogue.py:250`）、`choice`（选项在来源中的 1 起始编号，`dialogue.py:251`）、`text`（该选项的文字，`dialogue.py:252`）。顶层结果为 `{"id": 目标编号, "references": [...]}`（`dialogue.py:254`）。

## 4. 成功输出格式

- 标准输出为 `json.dumps(result, ensure_ascii=False)` 加一个结尾换行（`dialogue.py:255`）：**单行 JSON**，键顺序固定为 `id`、`references`，条目键顺序固定为 `source`、`choice`、`text`；中文不转义，默认分隔符为 `", "` 与 `": "`。
- 标准错误为空；退出码为 0（`cmd_references` 返回 0，经 `dialogue.py:335` 的 `sys.exit` 透出）。
- 输入文件字节不变：程序只以 `"rb"` 打开读取（`dialogue.py:55`），不存在任何写回操作。

## 5. 完整示例（仅文档展示，不加入仓库）

以下示例文件在 `sample.json` 的三个节点（`start`、`forest`、`river`，文字与选项均不变）之后，于末尾追加第四个节点 `side`（即 `nodes[3]`），文字为“旁路”，三个选项依次为：甲指向 `forest`、乙指向 `forest`、原地指向 `side`。

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

该文件可由读者另存为仓库外的临时文件复现下列结果；它不是仓库文件，`sample.json` 不做此修改。

### 5.1 查询 forest

命令：

```
python dialogue.py references <示例文件路径> --node forest
```

预期标准输出（单行，末尾换行）：

```
{"id": "forest", "references": [{"source": "start", "choice": 1, "text": "向左走"}, {"source": "side", "choice": 1, "text": "甲"}, {"source": "side", "choice": 2, "text": "乙"}]}
```

条目依次为：`start` 的选项 1（“向左走”）、不可达来源 `side` 的选项 1（“甲”）和选项 2（“乙”）。三条按 `nodes` 顺序（先 `start` 后 `side`）与各自 `options` 顺序排列；`side` 的选项 3 指向 `side` 而非 `forest`，不计入。

### 5.2 查询 side

命令：

```
python dialogue.py references <示例文件路径> --node side
```

预期标准输出（单行，末尾换行）：

```
{"id": "side", "references": [{"source": "side", "choice": 3, "text": "原地"}]}
```

只有 `side` 自己的选项 3（“原地”）指向 `side`：自引用照常计入，`choice` 取它在 `side` 三个选项中的编号 3；没有其他节点指向 `side`。

## 6. 确定的失败结果

所有失败均经 `fail`（`dialogue.py:41-44`）结束：**退出码 2、标准输出为空、标准错误为一条说明加换行、无调用栈**。

### 6.1 参数错误：在读取文件前输出现有完整用法

重复 `--node`（以及第 1.1 节列出的其他格式错误）在参数检查阶段即被拒绝，标准错误**逐字**为现有完整用法（`REFERENCES_USAGE`，`dialogue.py:32-34`，由 `fail` 补末尾换行）：

```
用法：
  python dialogue.py validate <文件路径>
  python dialogue.py preview <文件路径> --choice <选项编号> [--node <节点编号>]
  python dialogue.py inspect <文件路径> [--node <节点编号>]
  python dialogue.py references <文件路径> [--node <节点编号>]
```

例如 `references <文件> --node forest --node forest` 即使文件路径不存在，也只输出上述用法，不会出现“无法读取文件”，也不会创建该路径（参数检查先于 `load_dialogue`：`dialogue.py:282` 对 `dialogue.py:231`）。

### 6.2 合法参数下的文件类错误（沿用既有分类）

- **无法读取**（如路径不存在、无权限）：`无法读取文件 <路径>：<系统错误说明>`（`dialogue.py:59`）。
- **UTF-8 解码失败**：`文件 <路径> 的 UTF-8 解码失败：<解码错误说明>`（`dialogue.py:63`）。
- **JSON 语法错误**：`文件 <路径> 存在 JSON 语法错误（第 <行> 行第 <列> 列）：<解析器说明>`，行列位置由 `json.JSONDecodeError` 的 `lineno`/`colno` 给出（`dialogue.py:67-68`）。

### 6.3 整份校验失败先于节点查找

把第 5 节示例中的 `side` 节点去掉 `text` 字段（其余不变，文件仍可解析），则即使查询的是不存在的编号，阶段 3 也先失败。执行：

```
python dialogue.py references <缺 text 的示例文件路径> --node missing
```

标准错误为：

```
校验失败：缺少字段 nodes[3].text
```

定位来自第一遍逐节点校验：`side` 是第 4 个节点（下标 3），缺 `text` 在 `dialogue.py:100-102` 报告为“缺少字段 nodes[3].text”，`cmd_references` 加上“校验失败：”前缀（`dialogue.py:234-235`）。此输出不含“不存在”字样，因为节点查找（`dialogue.py:239-240`）根本没有执行。省略 `--node` 查询同一份文件结果相同。

### 6.4 合法文件查询不存在的节点

文件通过整份校验后，`--node missing` 在阶段 4 失败，标准错误为：

```
文件中不存在编号为 'missing' 的节点
```

消息由 `dialogue.py:240` 用 `{!r}` 格式化，因此包含该编号的字面表示（带引号）；首尾空白同样按原字符串保留在消息中。

## 7. 结论与源码位置对照（复核索引）

| 文档结论 | 源码位置 |
| --- | --- |
| 参数检查先于读取文件，重复/缺值/连写/多余参数报完整用法 | `dialogue.py:272-282`、`dialogue.py:326-330` |
| 失败统一为退出码 2、写标准错误、无调用栈 | `dialogue.py:41-44` |
| 文件读取 / UTF-8 / JSON 语法三类错误分类与行列 | `dialogue.py:52-68`（`:59`、`:63`、`:67-68`） |
| 整份校验覆盖不可达节点，先于查询 | `dialogue.py:71-138`、`dialogue.py:232-235` |
| 缺字段定位形如 `nodes[3].text` | `dialogue.py:96-102` |
| 省略 `--node` 查询 `start` | `dialogue.py:238` |
| 显式编号原字符串精确匹配、空白不裁剪 | `dialogue.py:281`、`dialogue.py:143`、`dialogue.py:248` |
| 节点不存在的消息含编号 | `dialogue.py:239-240` |
| 只统计 `options` 中的直接引用（含不可达来源、多个选项保留、自引用计入、`start` 字段不计、不展开循环） | `dialogue.py:245-253` |
| 结果按 `nodes`/`options` 顺序，`choice` 从 1 开始 | `dialogue.py:246-247`、`dialogue.py:251` |
| 成功输出单行 JSON 加结尾换行 | `dialogue.py:254-255` |
| 只读访问、不改写输入文件 | `dialogue.py:55`（全程仅 `"rb"` 打开，无写入） |
