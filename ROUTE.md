# route 命令流程说明

本文从 [README.md](README.md)「其他只读查询」中的 `route` 条目展开，
说明 `dialogue.py` 的 `route` 命令如何确定从 `start` 到指定节点的路线，
帮助逐项核对分支路线的确定性结果。本文仅作文档用途：不新增命令或参数，
不改动 `dialogue.py`、现有测试、`sample.json` 与其他公开文档，七个公开
命令（validate、preview、inspect、references、unreachable、no-ending、
route）的命令行与行为保持不变。文中所有结论均可对照源码逐项复核，行号
以当前 `dialogue.py` 为准；文中样例输出均为**预期结果**。

## 命令形式

```
python dialogue.py route <文件路径> --node <目标编号>
```

`route` 只接受一个文件路径加一次分写的 `--node <目标编号>`：`--node`
必须出现恰好一次，且不得写成 `--node=编号` 连写形式；文件路径在前、
`--node` 在后。目标编号按命令行原值接收，首尾空白不被裁剪。

## 处理流程与源码对应

一次 `route` 执行严格按以下先后关系进行，每步对应现有函数：

1. **参数检查（先于读文件）**：`main()`（`dialogue.py:470`）在
   `dialogue.py:506-513` 分发到 route 分支，先在 `dialogue.py:510-512`
   检查参数：`argv` 必须恰好为 5 项（程序名、`route`、文件路径、
   `--node`、目标编号），路径位置不得以减号开头（`argv[2]`），
   `argv[3]` 必须恰好等于 `--node`。缺少文件路径或目标值、`--node`
   重复、未知或额外参数、`--node=编号` 连写、`--node` 出现在路径之前、
   路径位置是形似选项的记号（如 `-x`），都在**读取任何文件之前**调用
   `fail(ROUTE_USAGE)`（`dialogue.py:512`）。`ROUTE_USAGE`
   （`dialogue.py:55`）是单行用法文字
   `python dialogue.py route <文件路径> --node <目标编号>`；`fail()`
   （`dialogue.py:62-65`）向标准错误写入该文字加一个换行并以退出码 2
   结束，不输出调用栈。注意目标编号本身形似选项（如 `-x`）不受此限：
   它位于 `argv[4]`，会被原值照收，留给后面的节点查找处理。
2. **读取文件**：参数合法后，`cmd_route()`（`dialogue.py:404`）在
   `dialogue.py:406` 调用 `load_validated_dialogue(path)`
   （`dialogue.py:162-174`），其内部先调用 `load_dialogue(path)`
   （`dialogue.py:73-89`）。该函数依次尝试：以二进制只读方式打开文件
   （`open(path, "rb")`，`dialogue.py:76`；`OSError` 在
   `dialogue.py:78-80` 报「无法读取文件」并附系统原因）、按 UTF-8 解码
   （`dialogue.py:81-84`；`UnicodeDecodeError` 报「UTF-8 解码失败」）、
   `json.loads` 解析（`dialogue.py:85-89`；`JSONDecodeError` 报
   「JSON 语法错误」，消息中保留出错的行号 `lineno` 与列号 `colno`）。
   三类失败都经 `fail()` 以退出码 2 结束。
3. **整份校验**：`load_validated_dialogue()` 接着在
   `dialogue.py:171-174` 调用 `validate_dialogue(data)`
   （`dialogue.py:92-159`），对**整份**对话数据（含无法从起点到达的
   节点）做结构校验与引用校验；失败时抛出 `DialogueError`，由
   `load_validated_dialogue()` 捕获后在 `dialogue.py:174` 以
   `fail("校验失败：…")` 报告，说明中带 JSON 字段位置（如
   `nodes[4].text`）。缺少 `id`/`text`/`options` 字段的检查在
   `dialogue.py:121-123`，选项缺少 `text`/`target` 在
   `dialogue.py:140-142`；引用检查（`start` 与每个 `target` 必须指向
   已存在的节点）在 `dialogue.py:149-157`。校验先于目标查找，因此即使
   查询的编号本身不存在，只要文件结构或引用非法，也先报校验失败。
4. **目标查找**：整份校验通过、`cmd_route()` 拿到 `(start, nodes)` 后，
   才在 `dialogue.py:409-410` 用 `find_node(nodes, node_arg)`
   （`dialogue.py:177-181`）按 `node["id"] == node_arg` 逐个做字符串
   精确比较。找不到时调用
   `fail("文件中不存在编号为 {!r} 的节点")`（`dialogue.py:410`），消息
   中按原值引用目标编号。
5. **路线选择**：目标存在时，`cmd_route()` 在 `dialogue.py:413-414`
   调用 `best_route(start, node_arg, nodes)`（`dialogue.py:365-401`）
   计算路线，规则见下节。
6. **输出**：`dialogue.py:415-417` 把
   `{"start": 起点编号, "target": 目标编号, "path": 路线}` 以
   `json.dumps(..., ensure_ascii=False, separators=(",", ":"))`
   紧凑序列化后单行写出，末尾加一个换行，退出码为 0
   （`dialogue.py:418`）。

## 编号匹配：精确相等，不裁剪首尾空白

- 节点编号的合法性要求是「至少含一个非空白字符的字符串」
  （`is_id_string()`，`dialogue.py:68-70`），但 `strip()` 只用于判空，
  **不会改写实际编号**；`" a "` 与 `"a"` 是两个不同的合法编号。
- 目标查找用的是命令行原值与 `node["id"]` 的直接相等比较
  （`find_node()`，`dialogue.py:179`）：`main()` 把 `argv[4]` 原样传入
  （`dialogue.py:513`），`cmd_route()` 原样使用（`dialogue.py:409`），
  全程没有 `strip()`。因此 `--node ' t '` 不会匹配到编号为 `t` 的节点，
  错误说明也按原值输出（`文件中不存在编号为 ' t ' 的节点`）。
- 选项编号不是字符串匹配：它从 1 开始，按各节点 `options` 数组的顺序
  确定（`best_route()` 在 `dialogue.py:391` 枚举、`dialogue.py:396`
  以 `i + 1` 作为 `choice`）。

## 路线选择规则（best_route）

路线是按行走顺序排列的若干步骤，每步为
`{"source": 来源编号, "choice": 选项编号, "target": 目标编号}`
（`dialogue.py:396`）。优先级（`dialogue.py:366-375` 的函数说明）：

1. **经过选项数量最少者优先**；
2. 步数并列时，取**完整选项编号序列按数值字典序最小者**，例如序列
   `(1, 2)` 小于 `(2, 1)`，因为先比较第一个元素 `1 < 2`；
3. 该次序与节点在 `nodes` 数组中的排列位置无关：节点先经
   `by_id = {node["id"]: node ...}` 按编号索引（`dialogue.py:378`），
   堆元素为 `(步数, 选项编号序列, 入堆序号, 节点编号, 路线)`
   （`dialogue.py:383`），其中入堆序号只作并列时的稳定次序，保证
   比较不会落到节点编号或路线本身上。

实现用最小堆按上述比较键逐条弹出候选路线（`dialogue.py:384-400`）：
节点**首次弹出**即得到它的最优路线（`dialogue.py:385-390`），之后再
弹出该节点直接跳过（`dialogue.py:386-388`），扩展时目标已访问也不再
入堆（`dialogue.py:393-394`）。

**合法循环不会导致校验失败，也不会让查询无限进行**：

- 校验的引用检查只确认每个 `target` 指向已存在的节点，注释明确
  「允许循环引用」（`dialogue.py:149-157`），不检查是否成环；自引用、
  多节点互指都合法。
- 搜索时 `visited` 集合（`dialogue.py:379`、`dialogue.py:386-394`）同时
  充当去重与终止条件：自引用（如 `a` 的选项指向 `a`）在
  `dialogue.py:393-394` 被跳过，多节点循环与多个选项指向同一节点也只
  各展开一次，集合以节点总数为上界，搜索必然有限结束。

两个边界结果：

- **目标就是起点**：`best_route()` 在 `dialogue.py:376-377` 直接返回
  `[]`，表示零步路线，仍是成功结果。
- **目标存在但不可达**：堆耗尽仍未弹出目标，`dialogue.py:401` 返回
  `None`，JSON 中序列化为 `null`；这同样是成功查询（退出码 0），不是
  错误。区分点在于：不可达的前提是目标编号存在；编号不存在时上一步
  的目标查找就已经失败。

## 完整示例：example.json

以下示例文件仅在本文档中展示，仓库自带的 `sample.json` 保持原样。
`start` 为 `s`，`nodes` 顺序为 `t`、`b`、`s`、`a`、`side`：`s` 的两个
选项依次指向 `a`、`b`；`a` 的两个选项依次指向自身 `a`、`t`；`b` 只有
一个指向 `t` 的选项；`t` 与 `side` 的 `options` 为空。全部节点文字与
选项文字都是合法字符串。把以下内容保存为 `example.json`：

```json
{
  "start": "s",
  "nodes": [
    {
      "id": "t",
      "text": "终点",
      "options": []
    },
    {
      "id": "b",
      "text": "乙节点",
      "options": [
        { "text": "去终点", "target": "t" }
      ]
    },
    {
      "id": "s",
      "text": "起点",
      "options": [
        { "text": "去 a", "target": "a" },
        { "text": "去 b", "target": "b" }
      ]
    },
    {
      "id": "a",
      "text": "甲节点",
      "options": [
        { "text": "留在 a", "target": "a" },
        { "text": "去终点", "target": "t" }
      ]
    },
    {
      "id": "side",
      "text": "旁路",
      "options": []
    }
  ]
}
```

执行：

```
python dialogue.py route example.json --node t
```

**预期结果**——标准输出只有一行紧凑 JSON 加一个结尾换行：

```json
{"start":"s","target":"t","path":[{"source":"s","choice":1,"target":"a"},{"source":"a","choice":2,"target":"t"}]}
```

退出码为 0，标准错误为空，输入文件字节不变（程序以只读方式打开文件，
从不写入）。

结果解读：从 `s` 到 `t` 有两条两步路线——

- 经 `s` 的选项 1 到 `a`、再经 `a` 的选项 2 到 `t`，选项编号序列为
  `[1, 2]`；
- 经 `s` 的选项 2 到 `b`、再经 `b` 的选项 1 到 `t`，选项编号序列为
  `[2, 1]`。

两者步数相同（均为 2），按完整选项编号序列的数值字典序，`(1, 2)` 小于
`(2, 1)`，所以取前者。`a` 的选项 1 指向自身是合法自引用，搜索到 `a` 后
该目标已在 `visited` 中而被跳过（`dialogue.py:393-394`），不影响结果
也不会造成死循环。该选择只取决于选项编号序列，与节点在 `nodes` 中的
排列无关——本例 `t`、`b` 在文件中甚至排在起点 `s` 之前。

## 独立变体：一步直达优先于两步路线

只在上例 `s` 节点的 `options` **末尾追加**第三个指向 `t` 的选项，其余
一律不变，另存为 `example2.json`：

```json
{
  "start": "s",
  "nodes": [
    {
      "id": "t",
      "text": "终点",
      "options": []
    },
    {
      "id": "b",
      "text": "乙节点",
      "options": [
        { "text": "去终点", "target": "t" }
      ]
    },
    {
      "id": "s",
      "text": "起点",
      "options": [
        { "text": "去 a", "target": "a" },
        { "text": "去 b", "target": "b" },
        { "text": "直达终点", "target": "t" }
      ]
    },
    {
      "id": "a",
      "text": "甲节点",
      "options": [
        { "text": "留在 a", "target": "a" },
        { "text": "去终点", "target": "t" }
      ]
    },
    {
      "id": "side",
      "text": "旁路",
      "options": []
    }
  ]
}
```

执行：

```
python dialogue.py route example2.json --node t
```

**预期结果**：

```json
{"start":"s","target":"t","path":[{"source":"s","choice":3,"target":"t"}]}
```

退出码为 0，标准错误为空，标准输出只有这一行 JSON 加一个结尾换行，
输入文件字节不变。新增的选项 3 给出一步路线 `[3]`；虽然它的字典序比
`[1, 2]` 大，但**步数最少是第一优先级**，一步的 `[3]` 胜过两步的
`[1, 2]`（及 `[2, 1]`）。原两步路线仍可在图中走通，只是不再被选为
答案。

## 起点与不可达目标：仍属成功

对主例 `example.json` 分别查询起点与旁路：

```
python dialogue.py route example.json --node s
```

**预期结果**（目标就是起点，零步路线为空数组）：

```json
{"start":"s","target":"s","path":[]}
```

```
python dialogue.py route example.json --node side
```

**预期结果**（`side` 存在但没有任何选项指向它，不可达，路线为
`null`）：

```json
{"start":"s","target":"side","path":null}
```

两次查询退出码均为 0，标准错误为空，标准输出各为一行紧凑 JSON 加一个
结尾换行，输入文件字节不变。注意 `side` 不可达**不是错误**：它的编号
确实存在，所以通过了目标查找；只有编号本身不存在时才按失败处理。

## 确定的失败结果

所有失败均为：退出码 2、标准输出为空、标准错误只有一条中文说明加一个
结尾换行、不输出调用栈（由 `fail()`，`dialogue.py:62-65` 统一保证），
且输入文件字节不变。

- **目标编号不存在**：文件合法但查询一个不存在的编号：

  ```
  python dialogue.py route example.json --node missing
  ```

  目标查找（`dialogue.py:409-410`）失败，标准错误只有：

  ```
  文件中不存在编号为 'missing' 的节点
  ```

  退出码 2，标准输出为空。编号按原值引用（`{!r}`），首尾空白也会原样
  出现在消息中。

- **整份校验失败先于目标查找**：把主例 `example.json` 中 `side` 节点的
  `text` 字段删除（`side` 是 `nodes` 的第 5 个节点，下标为 4），另存为
  `example_bad.json`，即使查询一个不存在的编号：

  ```
  python dialogue.py route example_bad.json --node missing
  ```

  也不会进入目标查找，而是先由整份校验报告
  （`validate_dialogue()` 在 `dialogue.py:121-123` 发现缺少字段，
  `load_validated_dialogue()` 在 `dialogue.py:174` 加上前缀）。标准
  错误只有：

  ```
  校验失败：缺少字段 nodes[4].text
  ```

  退出码 2，标准输出为空，错误中不出现「不存在」。即使 `side` 从
  `start` 不可达，它的结构错误同样阻止路线输出。

- **参数格式错误先于文件读取**：缺少目标值（如
  `python dialogue.py route example.json --node`）、重复 `--node`
  （如 `python dialogue.py route example.json --node t --node s`）、
  缺少文件路径、未知或额外参数、`--node=t` 连写、`--node` 位于路径
  之前、路径位置是以减号开头的记号等，都由 `main()` 在
  `dialogue.py:510-512` 于**读取文件之前**拒绝。标准错误只含现有 route
  单行用法加一个结尾换行：

  ```
  python dialogue.py route <文件路径> --node <目标编号>
  ```

  退出码 2，标准输出为空。即使给定路径不存在或文件内容是坏的，参数
  格式检查也优先，不会变成文件类错误，也不会创建该路径。

- **合法参数下的文件类失败**（`load_dialogue()`，
  `dialogue.py:73-89`），沿用各命令既有的同一分类：
  - 无法读取文件（如路径不存在）：`无法读取文件 <路径>：<系统原因>`
    （`dialogue.py:78-80`）；
  - UTF-8 解码失败：`文件 <路径> 的 UTF-8 解码失败：<细节>`
    （`dialogue.py:81-84`）；
  - JSON 语法错误：`文件 <路径> 存在 JSON 语法错误（第 <行> 行第
    <列> 列）：<说明>`（`dialogue.py:85-89`），行列定位取自
    `JSONDecodeError` 的 `lineno` 与 `colno`，予以保留。

  三类失败同样以退出码 2 结束，标准输出为空，不输出调用栈。
