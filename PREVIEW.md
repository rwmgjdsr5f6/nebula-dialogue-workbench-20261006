# preview 命令流程说明

本文说明 `python dialogue.py preview` 从命令输入到文字输出的完整流程，
每个关键结论都注明 `dialogue.py` 中对应的函数与源码位置，可逐项对照
当前源码核验。文中样例仅用于说明，仓库中不新增对应的 JSON 文件。

## 命令形式

```
python dialogue.py preview <文件路径> --choice <选项编号> [--node <节点编号>]
```

- `--choice` 必填，`--node` 可省略（省略时从 `start` 出发）。
- `--choice` 与 `--node` 两对参数顺序可互换，且各至多出现一次。
- 选项编号从 1 开始，按出发节点 `options` 数组的顺序确定。
- 节点编号按原字符串精确匹配，首尾空白不裁剪。

## 处理流程的先后关系

preview 的处理严格按以下顺序进行，前一步失败则后续步骤不会执行。
注意其中若干步骤由共享函数承担，并非 `cmd_preview` 内部的代码。

1. **参数检查**（读取文件之前）
   - `main`（dialogue.py:784）在 792–796 行分发 preview：先要求
     `len(argv) >= 5`（793–794 行），再调用
     `parse_preview_args(argv[3:])`（795 行）。
   - `parse_preview_args`（dialogue.py:697）逐项扫描键值对：出现未知
     参数、同一参数重复、缺值，或最终缺少 `--choice`，都调用
     `fail(USAGE)`（dialogue.py:708、710、712、716）。`USAGE` 定义在
     dialogue.py:70–75。
   - `fail`（dialogue.py:134）向标准错误写一行说明并以退出码 2 结束，
     不输出调用栈。参数错误一律发生在任何文件读取之前。

2. **文件读取与解析**
   - `cmd_preview`（dialogue.py:349）首先调用
     `load_validated_dialogue(path)`（dialogue.py:351）。
   - `load_validated_dialogue`（dialogue.py:250）本身不直接读写文件，
     而是在 dialogue.py:258 委托给共享前置流程
     `load_dialogue_for_edit`（dialogue.py:234，编辑命令也共用），
     后者在 dialogue.py:242 调用 `load_dialogue`。
   - `load_dialogue`（dialogue.py:145）以二进制读取文件、按 UTF-8
     解码、用 `json.loads` 解析；读取失败、解码失败、JSON 语法错误
     分别在此报告并以退出码 2 结束（dialogue.py:152、156、159–161），
     其中语法错误的说明包含出错行号与列号。

3. **整份校验**
   - 解析成功后，`load_dialogue_for_edit` 在 dialogue.py:244 调用
     `validate_dialogue`（dialogue.py:164）对整份数据做结构与引用
     校验，包括无法从起点到达的节点；`DialogueError` 在此被转换为
     「校验失败：…」说明，以退出码 2 结束（dialogue.py:245–246）。
   - 因此未选中分支、甚至不可达节点里的结构或引用错误，也会先于
     任何节点查找或选项检查暴露。

4. **出发节点查找**
   - 校验通过后，`cmd_preview` 确定出发节点：省略 `--node` 时用
     `start`，否则用 `--node` 的原字符串（dialogue.py:354）。
   - `find_node`（dialogue.py:262）按 `id` 精确匹配查找；找不到时
     报「文件中不存在编号为 … 的节点」（dialogue.py:356–357）。
   - 因为整份校验只检查 `start` 与各 `target` 的引用是否有效
     （`validate_dialogue` 第二遍，dialogue.py:221–229），并不要求
     节点可达，所以不可达节点也能作为显式出发节点；但不可达节点
     内部的非法结构或引用仍会在第 3 步阻止整份文件通过校验。

5. **选项定位**（共享函数 `locate_option`）
   - `cmd_preview` 在 dialogue.py:361–362 调用
     `locate_option`（dialogue.py:323，preview 与 retarget-option、
     set-option-text 共用），整数解析、结尾检查与范围检查都在该
     共享函数内依次进行，不在 `cmd_preview` 内部。
   - 先用 `int()` 解析 `--choice` 的值，无法解析为整数时报错
     （dialogue.py:332–336）；整数解析沿用 `int()` 的既有语义，
     `01`、`+1` 与带首尾空白的 `1` 都等同于 1，选中第一项。注意
     这一步先于「结尾节点没有选项」的检查。
   - 再检查出发节点是否为结尾（`options` 为空，dialogue.py:338–340）：
     对 `forest` 这样的结尾节点使用整数编号，报「--choice 1 无效：
     出发节点 'forest' 是结尾节点，没有有效选项」。
   - 最后检查编号是否在 1 到选项数的范围内（dialogue.py:341–343），
     只有非结尾节点才会走到这一步；越界时报「--choice 3 不在出发
     节点 'side' 的有效选项编号范围 1 到 1 内」。
   - 省略 `--node` 时上述错误说明用「起点」措辞，显式指定时用
     「出发节点」，由 `cmd_preview` 在 dialogue.py:360 决定后传入。
   - 三步都通过时，`locate_option` 在 dialogue.py:346 返回
     `options[choice - 1]`，即按数组顺序从 1 编号定位到的选项。

6. **输出**
   - `cmd_preview` 用选中选项的 `target` 经 `find_node` 找到目标
     节点（dialogue.py:365），只向标准输出写目标节点的 `text`
     加一个结尾换行（dialogue.py:366），以退出码 0 结束。预览只
     走一步：即使目标节点的选项指回自身（自引用），也只输出该
     节点文字一次，不继续前进、不保存进度、不改写输入文件，输入
     文件字节保持不变。

## 成功样例

以下 `example.json` 以 `sample.json` 为基础，仅在 `nodes` 末尾追加
`id` 为 `side`、`text` 为 `旁路入口` 的节点，其唯一选项文字为
`原地停留`、`target` 为 `side`，原有三个节点保持原样：

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

注意 `side` 从 `start` 出发沿选项 `target` 不可达，但仍可作为显式
出发节点；它的唯一选项是自引用，预览也只走一步。

### 例一：省略 --node，从 start 出发

```
python dialogue.py preview example.json --choice 1
```

标准输出（只有目标文字加一个结尾换行）：

```
你到了森林。
```

标准错误为空，退出码 0，不保存进度，输入文件字节保持不变。

### 例二：显式指定不可达的自引用节点

```
python dialogue.py preview example.json --node side --choice 1
```

标准输出：

```
旁路入口
```

标准错误为空，退出码 0，不保存进度，输入文件字节保持不变。`side`
不可达不影响它作为 `--node` 的显式出发节点；选项 1 的 `target`
指回 `side` 自身，也只输出一次「旁路入口」即结束。

## 错误优先顺序

下列三例使用 `example.json` 的独立变体或原样，说明各阶段报错的
先后：整份校验先于出发节点查找，出发节点查找先于 `--choice` 的
整数解析，整数解析先于结尾节点检查。每例标准输出均为空，退出码
均为 2，标准错误均无调用栈，均不产生部分预览。

### 例一：校验失败先于节点查找与编号解析

变体：删除 `side` 节点的 `text` 字段（其余与上文 `example.json`
相同）。即使同时指定不存在的节点和无法解析的编号，也先报校验失败：

```
python dialogue.py preview example_no_text.json --node missing --choice abc
```

标准错误全文：

```
校验失败：缺少字段 nodes[3].text
```

（`validate_dialogue` 第一遍逐节点检查必填字段，dialogue.py:193–195；
经 `load_dialogue_for_edit` 加上「校验失败：」前缀，
dialogue.py:245–246。）

### 例二：节点查找先于编号解析

对合法的 `example.json` 同时指定不存在的节点与无法解析的编号，
先报节点不存在：

```
python dialogue.py preview example.json --node missing --choice abc
```

标准错误全文：

```
文件中不存在编号为 'missing' 的节点
```

（`cmd_preview` 中 `find_node` 返回 `None` 后的报错，
dialogue.py:356–357。）

### 例三：编号解析先于结尾检查

`forest` 是结尾节点（`options` 为空），但 `--choice abc` 先触发
整数解析失败，而不是「结尾节点没有选项」：

```
python dialogue.py preview example.json --node forest --choice abc
```

标准错误全文：

```
--choice 的值 'abc' 无法解析为整数（出发节点编号为 'forest'）
```

（共享函数 `locate_option` 中 `int()` 解析失败的分支，
dialogue.py:332–336；结尾检查在其后的 dialogue.py:338–340。）

## 参数错误：重复 --choice

参数解析在任何文件读取之前完成。重复 `--choice` 时，即使文件根本
不存在，也直接输出用法说明：

```
python dialogue.py preview example.json --choice 1 --choice 2
```

标准错误全文（即 `USAGE`，dialogue.py:70–75）：

```
用法：
  python dialogue.py validate <文件路径>
  python dialogue.py preview <文件路径> --choice <选项编号> [--node <节点编号>]
```

标准输出为空，退出码 2，无调用栈。同一参数重复由
`parse_preview_args` 中的 `if name in values` 分支拒绝
（dialogue.py:709–710），发生在 `cmd_preview` 被调用、即文件被
读取之前。
