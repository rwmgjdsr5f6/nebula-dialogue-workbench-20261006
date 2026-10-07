# no-ending 命令流程说明

本文说明 `dialogue.py` 的 `no-ending` 命令如何报告「能从 `start` 进入、
却不存在任何有限步路径走到结尾」的节点，帮助判断可进入的节点是否还
存在通往结尾的路径。本文仅作文档用途：不新增命令或参数，不改动
`dialogue.py`、现有文档、现有测试与 `sample.json`，六个公开命令
（validate、preview、inspect、references、unreachable、no-ending）的
行为保持不变。文中所有结论均可逐项对照源码复核，行号以当前
`dialogue.py` 为准。

## 命令形式

```
python dialogue.py no-ending <文件路径>
```

`no-ending` 只接受一个文件路径，不接受任何选项参数。

## 处理流程与源码对应

`no-ending` 的一次执行按以下先后关系进行，每步对应现有函数：

1. **参数检查**：`main()`（`dialogue.py:406`）在 `dialogue.py:436-441`
   分发到 no-ending 分支，先检查参数个数必须恰好为 3（程序名、命令名、
   文件路径），且路径位置不得以减号开头（`dialogue.py:439`）。缺少路径、
   多余参数、任何选项参数或路径以减号开头时，都在**读取文件之前**调用
   `fail(NO_ENDING_USAGE)`（`dialogue.py:440`）。`NO_ENDING_USAGE`
   （`dialogue.py:47`）是单行用法文字
   `python dialogue.py no-ending <文件路径>`；`fail()`
   （`dialogue.py:54-57`）向标准错误写一条说明加一个换行并以退出码 2
   结束，不输出调用栈。
2. **读取文件**：参数合法后，`cmd_no_ending()`（`dialogue.py:335`）调用
   `load_validated_dialogue(path)`（`dialogue.py:154-166`），其内部先调用
   `load_dialogue(path)`（`dialogue.py:65-81`）。该函数依次尝试：以二进制
   读取文件（`OSError` 报「无法读取文件」）、按 UTF-8 解码
   （`UnicodeDecodeError` 报「UTF-8 解码失败」）、`json.loads` 解析
   （`JSONDecodeError` 报「JSON 语法错误」，消息含第几行第几列）。三类
   失败都经 `fail()` 以退出码 2 结束。
3. **整份校验**：`load_validated_dialogue()` 随后调用
   `validate_dialogue(data)`（`dialogue.py:84-151`），对整份对话数据
   （含无法从起点到达的节点）做结构校验与引用校验；失败时抛出
   `DialogueError`，由 `load_validated_dialogue()` 在 `dialogue.py:165-166`
   捕获后以 `fail("校验失败：…")` 报告，说明中带 JSON 字段位置（如
   `nodes[4].text`）。校验先于任何报告计算，因此即使错误位于不可达节点
   或纯循环内部，也先报校验失败，不产生部分报告。
4. **计算两个集合并生成报告**：校验通过后，`cmd_no_ending()` 在
   `dialogue.py:343` 调用 `reachable_node_ids(start, nodes)`
   （`dialogue.py:176-193`）求从 `start` 沿选项 `target` 正向可达的节点
   集合（起点本身始终可达），在 `dialogue.py:344` 调用
   `ending_reachable_ids(nodes)`（`dialogue.py:196-221`）求能在有限步内
   走到某个结尾的节点集合，再在 `dialogue.py:345-349` 取两者之差——
   已可达、却走不到任何结尾的节点。结果按原 `nodes` 数组顺序排列且
   不重复，不可达节点不列入。最后 `dialogue.py:350-353` 把
   `{"start": 起点编号, "no_ending": [...]}` 以紧凑 JSON
   （`separators=(",", ":")`、`ensure_ascii=False`）单行写出，末尾加
   一个换行，返回退出码 0。

## 结果语义

- **一条通往结尾的路径就足以让节点不被报告**。
  `ending_reachable_ids()`（`dialogue.py:196-221`）从全部结尾出发沿
  **反向**引用扩散：先在 `dialogue.py:205-213` 建立每个节点的入向来源
  表 `reverse` 并把全部结尾（`options` 为空数组的节点）放入 `good`，
  再在 `dialogue.py:215-220` 反复把「任一选项目标已在 `good` 中」的
  前驱节点并入 `good`。因此一个节点只要**任一**选项的目标能到结尾，
  它本身就被计入能到结尾；其余选项进入循环不影响结论。报告取的是
  可达集合与 `good` 的差集（`dialogue.py:345-349`），所以存在一条到
  结尾路径的节点不会出现在报告中。
- **合法循环本身不算校验错误**。`validate_dialogue()` 的第二遍
  （`dialogue.py:141-149`，注释明确「允许循环引用」）只检查 `start`
  与每个 `target` 是否指向已存在的节点编号，不检查是否成环；自引用、
  多节点互指循环都能通过校验，只会影响报告内容。
- **循环和重复指向不会让查询无限进行**。`reachable_node_ids()` 用
  `seen` 集合同时充当去重与终止条件（`dialogue.py:184-193`）：只有
  不在 `seen` 中的目标才会入队，自引用、多节点循环和多个选项指向同一
  节点都只会各展开一次。`ending_reachable_ids()` 同理用 `good` 集合
  充当去重与终止条件（`dialogue.py:215-220`）：已在 `good` 中的前驱
  不会再次入队。两个集合都只增不减且以节点总数为上界，因此循环必然
  正常结束；困在纯循环里的节点始终进不了 `good`，会被留在报告中。
- **结尾本身按零步到达处理**。`ending_reachable_ids()` 在
  `dialogue.py:208-211` 把每个 `options` 为空数组的节点直接放入
  `good` 并入队，不需要经过任何选项，因此结尾节点永远不会被报告，
  即使它是起点。
- **整份文件没有结尾时报告全部可达节点**。此时 `dialogue.py:208-211`
  找不到任何结尾，`good` 从空集开始也无法扩散，`ending_reachable_ids()`
  返回空集；`dialogue.py:345-349` 的差集于是等于整个可达集合。
- **不可达节点被排除**。报告只取 `reachable` 与 `good` 之差
  （`dialogue.py:345-349`），与 `start` 断开的节点（哪怕是纯循环）
  不列入；不可达的结尾照常进入 `good`，但救不了与它断开的可达循环。
- **结果按文件节点顺序排列**。`dialogue.py:345-349` 按原 `nodes`
  数组顺序过滤，每个编号只出现一次，与可达或扩散的先后无关。

## 完整示例

以下示例文件仅在本文档中展示，仓库自带的 `sample.json` 保持原样。
`start` 为 `s`，`nodes` 顺序为 `s`、`b`、`a`、`e`、`side`：`s` 的
两个选项依次指向 `a` 和 `e`，`a` 只指向 `b`，`b` 只指向 `a`（`a` 与
`b` 互指成环），`e` 没有选项（是结尾），`side` 只指向自身且从 `s`
不可达。节点与选项文字均为中文字符串。把以下内容保存为
`example.json`：

```json
{
  "start": "s",
  "nodes": [
    {
      "id": "s",
      "text": "你站在路口。",
      "options": [
        { "text": "走向甲地", "target": "a" },
        { "text": "走向终点", "target": "e" }
      ]
    },
    {
      "id": "b",
      "text": "你在乙地打转。",
      "options": [
        { "text": "回到甲地", "target": "a" }
      ]
    },
    {
      "id": "a",
      "text": "你在甲地徘徊。",
      "options": [
        { "text": "前往乙地", "target": "b" }
      ]
    },
    {
      "id": "e",
      "text": "故事到此结束。",
      "options": []
    },
    {
      "id": "side",
      "text": "一条无人走过的旁路。",
      "options": [
        { "text": "留在旁路", "target": "side" }
      ]
    }
  ]
}
```

执行：

```
python dialogue.py no-ending example.json
```

标准输出为单行 JSON 加一个结尾换行：

```json
{"start":"s","no_ending":["b","a"]}
```

退出码为 0，标准错误为空，输入文件字节不变（程序只读文件，从不
写入）。结果解读：

- `a` 与 `b` 互指成环，没有任何选项能离开这个环到达结尾，且都能从
  `s` 经选项 1 到达，因此被报告。
- 报告按文件中 `nodes` 的顺序排列：`b` 在文件中排在 `a` 之前，所以
  输出是 `["b","a"]` 而非 `["a","b"]`。
- `s` 的选项 2 指向结尾 `e`：存在一条通往结尾的路径就足以让 `s`
  不被报告，尽管选项 1 会进入循环。
- `e` 是结尾，按零步到达结尾处理，不会被报告。
- `side` 与 `start` 断开、不可达，即使是自引用纯循环也被排除在报告
  之外。

## 变体示例：为 b 增加一条通往结尾的出路

仅在上述 `example.json` 的 `b` 节点选项末尾追加一个指向 `e` 的选项，
其余不变，保存为 `example2.json`：

```json
{
  "start": "s",
  "nodes": [
    {
      "id": "s",
      "text": "你站在路口。",
      "options": [
        { "text": "走向甲地", "target": "a" },
        { "text": "走向终点", "target": "e" }
      ]
    },
    {
      "id": "b",
      "text": "你在乙地打转。",
      "options": [
        { "text": "回到甲地", "target": "a" },
        { "text": "直奔终点", "target": "e" }
      ]
    },
    {
      "id": "a",
      "text": "你在甲地徘徊。",
      "options": [
        { "text": "前往乙地", "target": "b" }
      ]
    },
    {
      "id": "e",
      "text": "故事到此结束。",
      "options": []
    },
    {
      "id": "side",
      "text": "一条无人走过的旁路。",
      "options": [
        { "text": "留在旁路", "target": "side" }
      ]
    }
  ]
}
```

执行：

```
python dialogue.py no-ending example2.json
```

标准输出为：

```json
{"start":"s","no_ending":[]}
```

退出码为 0，标准错误为空，标准输出只有这一行 JSON 加一个结尾换行，
输入文件字节不变。`b` 的新选项让它能到结尾，`a` 经 `b` 也能到结尾，
原来的环不再是死路，报告因此为空；`side` 仍不可达，依旧不列入。

## 确定的失败结果

所有失败均为：退出码 2、标准输出为空、标准错误无调用栈（由
`fail()`，`dialogue.py:54-57` 统一保证），且不会产生部分报告——
报告只在整份校验通过后一次性输出（`dialogue.py:350-353`）。

- **校验失败先于报告**：把第一个示例中 `side` 节点的 `text` 字段删除
  （其余不变，保存为 `example_bad.json`），即使 `side` 不可达，整份
  校验也会先失败。`side` 是 `nodes` 的第 5 个节点，下标为 4，
  `validate_dialogue()` 在 `dialogue.py:113-115` 抛出缺少字段的
  `DialogueError`，由 `load_validated_dialogue()` 在
  `dialogue.py:165-166` 转为：

  ```
  python dialogue.py no-ending example_bad.json
  ```

  标准错误只有一行加一个结尾换行：

  ```
  校验失败：缺少字段 nodes[4].text
  ```

  退出码 2，标准输出为空，不输出调用栈，也不会输出任何无结尾路径的
  部分结果。

- **参数格式错误先于文件读取**：缺少文件路径、路径之后有多余参数、
  出现任何选项参数，或路径位置是以减号开头的记号（如 `-example.json`）
  时，`main()` 在 `dialogue.py:439-440` 于**读取文件之前**拒绝。标准
  错误仅为单行用法加一个结尾换行：

  ```
  python dialogue.py no-ending <文件路径>
  ```

  退出码 2，标准输出为空。即使路径不存在或文件内容非法，参数格式
  检查也优先，不会变成文件类错误。

- **合法参数下的文件类失败**（`load_dialogue`，`dialogue.py:65-81`）：
  - 无法读取文件（如路径不存在）：`无法读取文件 <路径>：<原因>`；
  - UTF-8 解码失败：`文件 <路径> 的 UTF-8 解码失败：<细节>`；
  - JSON 语法错误：`文件 <路径> 存在 JSON 语法错误（第 <行> 行第
    <列> 列）：<说明>`，含行列位置。

  三类失败同样以退出码 2 结束，标准输出为空，不输出调用栈。
