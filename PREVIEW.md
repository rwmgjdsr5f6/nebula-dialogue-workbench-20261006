# preview 命令流程说明

本文说明 `dialogue.py` 的 `preview`（单步预览）命令从命令行参数输入到
文字输出的现有流程，仅作文档用途：不新增命令或参数，不改动
`dialogue.py`、现有测试、`sample.json` 与其他文档，七个既有命令
（validate、preview、inspect、references、unreachable、no-ending、
route）的接口、校验与只读行为保持不变。文中所有结论均可逐项对照源码
复核，行号以当前 `dialogue.py` 为准。

## 命令形式与参数规则

```
python dialogue.py preview <文件路径> --choice <选项编号> [--node <节点编号>]
```

- `--choice` **必填**，必须是 `--choice <值>` 分写形式；缺少即按用法
  错误处理（`dialogue.py:465-466`）。
- `--node` **可省略**；省略时从顶层 `start` 指定的节点出发
  （`dialogue.py:243`）。
- `--choice` 与 `--node` 两对参数**顺序可互换**，且各自**至多出现一次**；
  未知参数名、重复出现或缺值都按用法错误处理
  （`parse_preview_args()`，`dialogue.py:447-467`）。
- 选项编号从 **1** 开始，按出发节点 `options` 数组的顺序确定
  （`dialogue.py:264`、`dialogue.py:272` 使用 `options[choice - 1]`）。
- 节点编号按**原字符串精确匹配**：`find_node()`（`dialogue.py:177-181`）
  逐个做 `node["id"] == node_id` 比较，首尾空白**不裁剪**，空字符串也照
  原值参与查找。

## 处理流程与源码对应

一次 `preview` 执行严格按以下先后关系进行，每一步对应现有函数：

1. **参数检查（读取文件之前）**：`main()`（`dialogue.py:470-482`）在
   preview 分支先确认参数总数不少于 5（`dialogue.py:479-480`），再调用
   `parse_preview_args(rest)`（`dialogue.py:447-467`）成对扫描
   `--choice`/`--node`。任何未知参数、重复参数、缺值，或最终没有
   `--choice`，都调用 `fail(USAGE)` 结束——此时尚未打开文件。`fail()`
   （`dialogue.py:62-65`）向标准错误写一条说明并以退出码 2 结束，不输出
   调用栈；`USAGE`（`dialogue.py:31-36`）是 validate 与 preview 两条
   命令共用的完整用法文字。
2. **文件读取与解析**：`cmd_preview()`（`dialogue.py:238-275`）首先调用
   `load_validated_dialogue(path)`（`dialogue.py:162-174`），其第一步是
   `load_dialogue(path)`（`dialogue.py:73-89`）：以二进制读取文件
   （`OSError` 报“无法读取文件”，`dialogue.py:78-80`）、按 UTF-8 解码
   （`UnicodeDecodeError` 报“UTF-8 解码失败”，`dialogue.py:81-84`）、
   再用 `json.loads` 解析（`JSONDecodeError` 报含行号列号的“JSON 语法
   错误”，`dialogue.py:85-89`）。三类失败都经 `fail()` 以退出码 2 结束。
3. **整份校验**：`load_validated_dialogue()` 随后调用
   `validate_dialogue(data)`（`dialogue.py:92-159`），对整份对话数据
   （含无法从起点到达的节点、含本次不会选中的分支）做结构与引用校验：
   顶层必须有非空白字符串 `start` 与非空数组 `nodes`
   （`dialogue.py:98-113`）；每个节点必须有 `id`、`text`、`options`
   （`dialogue.py:121-123`），每个选项必须有 `text`、`target`
   （`dialogue.py:140-142`）；`start` 与每个 `target` 都必须指向实际存在
   的节点（`dialogue.py:150-157`）。失败时抛出 `DialogueError`，由
   `load_validated_dialogue()` 转换为 `fail("校验失败：…")`
   （`dialogue.py:171-174`）。**这一步先于出发节点查找与选择编号检查**，
   因此文件本身非法时，即使 `--node` 不存在、`--choice` 不是整数，也
   先报校验失败。
4. **出发节点查找**：校验通过后，`cmd_preview()` 在 `dialogue.py:243`
   确定出发编号（省略 `--node` 取 `start`，否则取参数原值），再用
   `find_node()`（`dialogue.py:177-181`）按原字符串精确匹配。找不到时
   在 `dialogue.py:245-246` 以
   `fail("文件中不存在编号为 {!r} 的节点")` 报告。**这一步先于选择编号
   解析**，因此节点不存在与 `--choice` 非整数同时出现时，先报节点不存在。
   能否从 `start` 到达该节点不在考虑之列：不可达节点也能作为显式出发
   节点（校验只保证编号存在，不做可达性判断）。
5. **选择编号检查**：找到出发节点后依次做两项检查：
   - 先用 `int(choice_arg)` 解析编号（`dialogue.py:249-250`）；解析失败时
     在 `dialogue.py:251-256` 报“无法解析为整数”（消息区分省略 `--node`
     时的“起点”与显式 `--node` 时的“出发节点”）。
   - 再检查选项：出发节点 `options` 为空（结尾节点）时在
     `dialogue.py:258-263` 报“是结尾节点，没有有效选项”；编号超出
     `1 到 len(options)` 范围时在 `dialogue.py:264-269` 报越界。
     因此**整数解析先于结尾/越界判断**：`--choice abc` 作用在结尾节点上
     时先报“无法解析为整数”，而不是“没有有效选项”。
6. **文字输出**：全部检查通过后，`dialogue.py:272` 取
   `options[choice - 1]["target"]`，`dialogue.py:273` 用 `find_node()`
   找到目标节点，`dialogue.py:274` 只向标准输出写出目标节点的 `text`
   再加一个换行（`sys.stdout.write(target_node["text"] + "\n")`），返回
   退出码 0。预览**只走一步**：不沿目标节点的选项继续前进，不保存当前
   节点或任何进度，也不改写输入文件（`cmd_preview` 全程无写文件操作）。

## 样例：example.json

下面的 `example.json` 以 `sample.json` 为基础，仅在 `nodes` 末尾追加一个
id 为 `side` 的节点：文字为“旁路入口”，唯一选项文字为“原地停留”、
target 指向 `side` 自身。原有三个节点保持原样。该样例只在本文档中展示，
不随仓库新增实际 JSON 文件。

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
      "text": "旁路入口",
      "options": [
        { "text": "原地停留", "target": "side" }
      ]
    }
  ]
}
```

`side` 没有任何选项指向它，因此无法从 `start` 沿选项 target 到达；它的
唯一选项又指向自身（自引用）。这两点都不影响校验通过（结构与引用合法，
见 `dialogue.py:150-157`），也不影响把它作为显式出发节点。

### 例 1：从 start 预览第一步

```sh
python dialogue.py preview example.json --choice 1
```

省略 `--node`，出发节点为 `start`；选项编号 1 按 `options` 顺序对应
“向左走”，其 target 为 `forest`。标准输出只有目标节点文字加一个结尾
换行：

```
你到了森林。
```

### 例 2：从不可达且自引用的 side 显式出发

```sh
python dialogue.py preview example.json --node side --choice 1
```

虽然 `side` 从 `start` 不可达，它仍是合法的显式出发节点
（`find_node()` 只按编号查找，`dialogue.py:177-181`）；编号 1 对应唯一
选项“原地停留”，其 target 仍是 `side`。预览**只取这一步的目标节点文字**，
不会因自引用而继续前进或陷入循环。标准输出为：

```
旁路入口
```

两例均以退出码 0 结束，标准错误为空，标准输出只有上述目标文字加一个
结尾换行，且不保存任何进度、不改写文件。

## 错误优先顺序（样例的独立变体）

下列失败一律以退出码 2 结束，标准输出为空，标准错误只有一条中文说明，
不输出调用栈（统一由 `fail()` 处理，`dialogue.py:62-65`）。

### 先整份校验，再查节点与编号

把上面 `example.json` 复制为一个独立变体，仅删除 `side` 节点的 `text`
字段，即其末尾节点变为：

```json
{ "id": "side", "options": [ { "text": "原地停留", "target": "side" } ] }
```

对该变体同时指定不存在的节点 `missing` 和非整数 `--choice abc`：

```sh
python dialogue.py preview <该变体文件> --node missing --choice abc
```

整份校验先于节点查找与编号解析，`nodes[3]` 缺少必需字段即失败
（`dialogue.py:121-123` 经 `dialogue.py:171-174` 报告）。标准错误全文：

```
校验失败：缺少字段 nodes[3].text
```

### 校验通过后，先查出发节点

对合法的 `example.json` 同时指定不存在的节点和非整数编号：

```sh
python dialogue.py preview example.json --node missing --choice abc
```

文件校验通过后先做出发节点查找（`dialogue.py:243-246`），尚未解析
`--choice`。标准错误全文：

```
文件中不存在编号为 'missing' 的节点
```

### 节点存在后，先解析整数再判断结尾

`forest` 存在但 `options` 为空（结尾节点），同时给出非整数编号：

```sh
python dialogue.py preview example.json --node forest --choice abc
```

整数解析（`dialogue.py:249-256`）先于结尾节点判断
（`dialogue.py:258-263`），因此报的是无法解析为整数，而不是“结尾节点，
没有有效选项”。标准错误全文：

```
--choice 的值 'abc' 无法解析为整数（出发节点编号为 'forest'）
```

### 参数用法错误先于文件读取

`--choice` 重复出现时，`parse_preview_args()` 在读取任何文件之前即以
用法错误结束（`dialogue.py:459-460`）；即使给定的文件路径不存在，也不
会报文件读取错误：

```sh
python dialogue.py preview example.json --choice 1 --choice 2
```

标准错误输出 `USAGE`（`dialogue.py:31-36`）的现有完整文字，共三行：

```
用法：
  python dialogue.py validate <文件路径>
  python dialogue.py preview <文件路径> --choice <选项编号> [--node <节点编号>]
```

本例退出码同样为 2，标准输出为空，无调用栈。
