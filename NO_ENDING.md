# no-ending 命令流程说明

本文说明 `dialogue.py` 的 `no-ending` 报告如何帮助判断：从起点可以进入的
节点里，哪些已经不存在任何有限步路径可以走到对话结尾。本文仅作文档用途：
不新增命令或参数，不改动 `dialogue.py`、已有文档、测试与 `sample.json`，
六个公开命令（validate、preview、inspect、references、unreachable、
no-ending）的行为保持不变。文中所有结论均可逐项对照源码复核，行号以当前
`dialogue.py` 为准。

## 1. 这份报告回答什么问题

“结尾”指 `options` 为空数组的节点：走到它时不再有选项可选。游戏作者关心
的是：玩家从 `start` 真正能走到的每个节点，是否**至少保留一条**顺着选项
走到某个结尾的出路。困在循环里出不来的节点，玩家一旦进入就永远无法结束
对话，应当被找出来修改。

`no-ending` 的输出就是这份“可进入但无路可终”的节点编号清单：

```json
{"start": "s", "no_ending": ["b", "a"]}
```

- `start`：本份文件的起点编号。
- `no_ending`：从 `start` 沿选项 `target` **可达**、却**不存在任何有限步
  路径走到结尾**的节点编号。

反过来读这份报告：凡是可达而没有出现在 `no_ending` 里的节点，都至少还有
一条通往结尾的路径（即使它的另一些选项会走进循环）；不可达的节点根本无法
进入，不在本报告范围内。

## 2. 命令形式

```
python dialogue.py no-ending <文件路径>
```

只接受恰好一个文件路径，没有其他选项。

## 3. 处理流程的先后关系

一次 `no-ending` 调用严格按“参数检查 → 读取文件 → 整份校验 → 生成报告”
的顺序进行，前一步失败就以退出码 2 结束，不会进入后面的步骤：

1. **参数检查（在读文件之前）**：入口 `main()`（`dialogue.py:406-442`）
   在 `dialogue.py:436-441` 分发 no-ending 分支，
   `dialogue.py:439` 用 `len(argv) != 3 or argv[2].startswith("-")`
   一次性拒绝三种情况：缺少文件路径、文件路径之外有多余参数、路径位置是
   以减号开头的记号。拒绝时调用 `fail(NO_ENDING_USAGE)`
   （`dialogue.py:440`），此时 `cmd_no_ending()` 尚未被调用
   （`dialogue.py:441`），因此不会发生任何文件读取。用法文字定义在
   `NO_ENDING_USAGE`（`dialogue.py:47`）。
2. **读取文件**：`cmd_no_ending()`（`dialogue.py:335-354`）在
   `dialogue.py:338` 调用共用前置流程
   `load_validated_dialogue()`（`dialogue.py:154-166`），后者先调用
   `load_dialogue()`（`dialogue.py:65-81`）：以二进制只读方式打开文件
   （`dialogue.py:68`），再按 UTF-8 解码（`dialogue.py:73-76`），再用
   `json.loads` 解析（`dialogue.py:77-81`）。无法读取、解码失败、JSON
   语法错误分别在这三处经 `fail()` 以退出码 2 结束。
3. **整份校验（在任何报告计算之前）**：`load_validated_dialogue()` 随后
   调用 `validate_dialogue()`（`dialogue.py:84-151`），对整份数据做结构
   与引用校验，**包括从起点不可达的节点**。校验失败抛出 `DialogueError`，
   在 `dialogue.py:163-166` 被统一改写为
   `fail("校验失败：{}".format(exc))`，退出码 2。因为这一步发生在
   `dialogue.py:343` 的集合计算和 `dialogue.py:351-353` 的输出之前，
   校验不过时不会产生任何部分报告，标准输出为空。
4. **生成报告**：校验通过后，`cmd_no_ending()` 在
   `dialogue.py:343` 求可达集合，在 `dialogue.py:344` 求“能到结尾”
   集合，在 `dialogue.py:345-349` 按 `nodes` 顺序取两者之差，最后在
   `dialogue.py:350-353` 组成
   `{"start": ..., "no_ending": [...]}` 写成单行 JSON 加一个换行，
   返回 0（经 `dialogue.py:445-446` 的 `sys.exit(main(sys.argv))`
   成为进程退出码）。

`fail()`（`dialogue.py:54-57`）始终是“向标准错误写一条消息加换行，再
`sys.exit(2)`”，不抛异常、不输出调用栈。

## 4. 关键判定与源码依据

报告由两个集合之差得到，全部逻辑在 `cmd_no_ending()`
（`dialogue.py:335-354`）中：

- **可达集合**：`reachable_node_ids(start, nodes)`
  （`dialogue.py:176-193`）。`seen = {start}`（`dialogue.py:184`）
  保证起点本身始终计入；从 `pending` 取出节点后只沿它各选项的 `target`
  正向展开（`dialogue.py:187-192`），不反向访问，所以不可达节点不会
  因为指向了可达节点而被计入。
- **能到结尾集合**：`ending_reachable_ids(nodes)`
  （`dialogue.py:196-221`）。从全部结尾出发，沿**反向**引用扩散：
  `dialogue.py:205` 建反向邻接表，`dialogue.py:212-213` 填入
  “谁的选项指向我”；`dialogue.py:215-220` 从结尾向外扩散前驱。
- **取差并排序**：`dialogue.py:345-349` 按 `nodes` 数组原顺序逐个判断
  “可达且不在能到结尾集合中”，每个节点只出现一次。

### 4.1 结尾本身按零步到达处理

`dialogue.py:208-211` 扫描节点时，凡是 `options` 为空数组的节点，不经过
任何一条边就直接加入 `good` 并作为扩散起点。也就是说结尾到结尾是零步，
结尾节点本身不会被报告；若起点自己就没有选项，报告同样为空
（`good` 初始即含起点，差集为空）。

### 4.2 一条通往结尾的路径就足够

扩散规则是“一个节点的**任一**选项目标已经能到结尾，它本身就能到结尾”：
`dialogue.py:217-220` 枚举前驱时，只要该前驱尚未在 `good` 中就加入。
这是存在性判断而非全称判断——节点有一个选项走向结尾即可，其余选项即使
全部进入循环也不影响结论。因此一条出路就能让节点不出现在报告里。

### 4.3 合法循环本身不是校验错误

`validate_dialogue()` 的第二遍引用检查（`dialogue.py:141-149`）只核对
每个 `target`（以及 `start`，`dialogue.py:142-143`）指向的编号确实
存在，`dialogue.py:141` 的注释明确“允许循环引用”。自引用、两节点互指、
更长的环都合法，`validate` 与 `no-ending` 都不会因此报错；循环只在
“能否走到结尾”的语义分析中才产生效果（困在纯循环里的节点进不了 `good`）。

### 4.4 循环和重复指向不会让查询无限进行

两次集合遍历都用“已访问集合同时充当初始化与终止条件”：

- 正向遍历里，目标只有在 `target not in seen` 时才入队
  （`dialogue.py:190-192`）；
- 反向扩散里，前驱只有在 `predecessor not in good` 时才入队
  （`dialogue.py:218-220`）。构建反向表时同一来源的多个选项会逐项追加
  （`dialogue.py:212-213`），所以多个选项指向同一节点会产生重复边，但
  重复的前驱第二次出现时已在集合中，不会再次入队。

节点总数有限，每个节点至多入队一次、每条边至多扫描一次，`pending`
必然排空，自引用、多节点循环、重复指向都不会造成死循环。

### 4.5 整份文件没有结尾时报告全部可达节点

没有任何 `options` 为空的节点时，`dialogue.py:208-211` 不播种任何结尾，
扩散循环（`dialogue.py:215-220`）一次也不执行，`good` 保持为空
（见函数文档字符串 `dialogue.py:203`）。于是 `dialogue.py:345-349`
的条件对每个可达节点都成立，报告全部可达节点；不可达节点仍被排除。
例如下份只有 `s → a → b → a` 的文件：

```json
{
  "start": "s",
  "nodes": [
    { "id": "s", "text": "起点。",
      "options": [ { "text": "去甲", "target": "a" } ] },
    { "id": "a", "text": "甲。",
      "options": [ { "text": "去乙", "target": "b" } ] },
    { "id": "b", "text": "乙。",
      "options": [ { "text": "回甲", "target": "a" } ] }
  ]
}
```

输出为 `{"start":"s","no_ending":["s","a","b"]}`（外加结尾换行）。

## 5. 完整示例：example.json

下面是一份完整的合法对话，可直接保存为 `example.json`。`start` 为 `s`，
`nodes` 顺序为 **s、b、a、e、side**；节点文字与选项文字均为中文字符串。
`s` 的两个选项依次指向 `a` 和 `e`；`a` 只有一个选项指向 `b`，`b` 只有
一个选项指向 `a`（二者互指成环）；`e` 没有选项，是结尾；`side` 的唯一
选项指向它自身，且没有任何选项指向 `side`：

```json
{
  "start": "s",
  "nodes": [
    {
      "id": "s",
      "text": "你站在起点。",
      "options": [
        { "text": "去甲节点", "target": "a" },
        { "text": "直接结束", "target": "e" }
      ]
    },
    {
      "id": "b",
      "text": "乙节点。",
      "options": [
        { "text": "回到甲", "target": "a" }
      ]
    },
    {
      "id": "a",
      "text": "甲节点。",
      "options": [
        { "text": "去乙节点", "target": "b" }
      ]
    },
    {
      "id": "e",
      "text": "对话结束。",
      "options": []
    },
    {
      "id": "side",
      "text": "无人抵达的旁路。",
      "options": [
        { "text": "留在旁路", "target": "side" }
      ]
    }
  ]
}
```

执行：

```sh
python dialogue.py no-ending example.json
```

标准输出只有下面这一行 JSON 和一个结尾换行：

```
{"start":"s","no_ending":["b","a"]}
```

逐条对照源码可核对该结果：

- **排序是文件节点顺序，不是选项展开顺序**：`dialogue.py:345-349`
  按 `nodes` 数组遍历，`b`（下标 1）在 `a`（下标 2）之前，所以输出
  `["b","a"]`，尽管 `s` 的第一个选项先指向 `a`。
- **`s` 不被报告**：`e` 作为结尾被零步播种（`dialogue.py:208-211`），
  `s` 有一个选项指向 `e`，经反向扩散进入 `good`
  （`dialogue.py:217-220`）。存在“`s → e`”这一条出路即足够，
  另一个选项走进 `a ↔ b` 循环不影响 `s` 的结论。
- **`a`、`b` 被报告**：两者互指成环，环上没有任何选项通向 `e`，
  反向扩散永远到不了它们，二者可达却不在 `good` 中。
- **`e` 不被报告**：它是结尾，按零步到达计入 `good`。
- **`side` 被排除**：正向可达集合从 `{s}` 出发（`dialogue.py:184`），
  没有任何选项的 `target` 是 `side`，自引用不会让它凭空变得可达；
  不可达节点在 `dialogue.py:348` 的 `node["id"] in reachable`
  条件处被过滤。它的自引用循环同样不影响可达部分的分析。

## 6. 变体：仅在 b 末尾追加一个指向 e 的选项

在第 5 节文件的基础上，只改动 `b` 一个节点：在其 `options` **末尾**
追加一个指向 `e` 的选项“走向结尾”。完整变体如下（其余四个节点一字不改）：

```json
{
  "start": "s",
  "nodes": [
    {
      "id": "s",
      "text": "你站在起点。",
      "options": [
        { "text": "去甲节点", "target": "a" },
        { "text": "直接结束", "target": "e" }
      ]
    },
    {
      "id": "b",
      "text": "乙节点。",
      "options": [
        { "text": "回到甲", "target": "a" },
        { "text": "走向结尾", "target": "e" }
      ]
    },
    {
      "id": "a",
      "text": "甲节点。",
      "options": [
        { "text": "去乙节点", "target": "b" }
      ]
    },
    {
      "id": "e",
      "text": "对话结束。",
      "options": []
    },
    {
      "id": "side",
      "text": "无人抵达的旁路。",
      "options": [
        { "text": "留在旁路", "target": "side" }
      ]
    }
  ]
}
```

执行同一条命令：

```sh
python dialogue.py no-ending example.json
```

（把变体保存为任意文件名并替换路径即可。）标准输出为：

```
{"start":"s","no_ending":[]}
```

环上只是多了一条出路：`e` 播种后，`b` 因新增的“走向结尾”选项进入
`good`（`dialogue.py:217-220`），`a` 的唯一选项指向已经是 `good` 的
`b`，随后也进入 `good`。于是所有可达节点 `s、b、a、e` 都能在有限步
走到结尾，差集为空；`side` 仍不可达，照常排除。这也印证了 4.2 节：
`b` 保留“回到甲”这个入环选项并不妨碍它靠另一条出路脱离报告。

## 7. 两次成功调用的统一约定

第 5、6 节两次调用的进程行为完全同构：

- 退出码为 **0**（`cmd_no_ending()` 返回 0，`dialogue.py:354`，
  经 `dialogue.py:446` 退出）。
- 标准错误为**空**（成功路径上没有任何 `sys.stderr.write`）。
- 标准输出**只有单行 JSON 和一个结尾换行**：
  `dialogue.py:351-353` 用 `json.dumps(..., ensure_ascii=False,
  separators=(",", ":"))` 生成无多余空白的紧凑 JSON（中文不转义），
  再显式追加一个 `"\n"`；字段顺序固定为对象字面量中的 `start`、
  `no_ending`（`dialogue.py:350`），即逐字节分别为
  `{"start":"s","no_ending":["b","a"]}\n` 与
  `{"start":"s","no_ending":[]}\n`。
- **输入文件字节不变**：程序只在 `dialogue.py:68` 以 `"rb"`
  只读方式打开文件，全文没有任何写回或另存动作；报告只写到标准输出。

## 8. 确定的失败结果

所有失败都经 `fail()`（`dialogue.py:54-57`）处理：退出码 **2**、
标准输出为空、标准错误只有一条中文说明加一个换行、没有调用栈。

### 8.1 校验失败：删除 side 的 text 字段

把第 5 节的 `example.json` 中第五个节点 `side` 的 `text` 字段删掉
（其余完全不变），该节点变为：

```json
    {
      "id": "side",
      "options": [
        { "text": "留在旁路", "target": "side" }
      ]
    }
```

另存为例如 `example_bad.json`，执行：

```sh
python dialogue.py no-ending example_bad.json
```

结果为：

- 退出码 **2**；
- 标准输出为**空**——不产生任何部分报告；
- 标准错误恰好是下面这一行（一个换行结尾），且不含调用栈：

```
校验失败：缺少字段 nodes[4].text
```

对应源码：必查字段循环在 `dialogue.py:113-115` 依次要求每个节点具备
`id、text、options`，`side` 是第 5 个节点、下标为 4，故定位为
`nodes[4].text`；`DialogueError` 在 `dialogue.py:165-166` 被加上
“校验失败：”前缀，再由 `fail()` 补换行并 `sys.exit(2)`
（`dialogue.py:56-57`）。尽管 `side` 不可达，整份校验仍覆盖它
（`validate_dialogue()` 遍历全部 `nodes`，`dialogue.py:109`）；
由于失败发生在 `dialogue.py:338`、早于报告计算（`dialogue.py:343`）
和输出（`dialogue.py:351`），标准输出不可能出现半截报告。

### 8.2 参数错误：在读文件前拒绝

以下三类调用都在参数检查阶段被拒绝，**不会读取文件**：

- 缺少路径：`python dialogue.py no-ending`
- 多余参数：如 `python dialogue.py no-ending example.json extra`
  （两个路径位置参数同理）；
- 路径位置以减号开头：如 `python dialogue.py no-ending -sample.json`，
  孤立的 `-`、`--node` 等形似选项的记号也在此列。

三者结果相同：退出码 **2**，标准输出为空，标准错误**仅为**下面这一行
用法说明加一个换行，没有调用栈：

```
python dialogue.py no-ending <文件路径>
```

对应源码：判定集中在 `dialogue.py:439`
（`len(argv) != 3` 覆盖缺路径与多余参数，`argv[2].startswith("-")`
覆盖减号开头的记号），随即在 `dialogue.py:440` 调用
`fail(NO_ENDING_USAGE)`；用法文字定义于 `dialogue.py:47`。
真正读取文件的 `cmd_no_ending(argv[2])` 在 `dialogue.py:441`，
参数不合法时不会执行，因此即使路径不存在或文件内容是坏的，也只会得到
同一行用法错误，不会变成“无法读取文件”或 JSON 语法错误。
