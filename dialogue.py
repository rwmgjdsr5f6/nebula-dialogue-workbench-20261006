#!/usr/bin/env python3
"""本地对话命令行程序：校验对话 JSON 结构，并进行一次分支预览、只读节点查看、入向引用查询、不可达节点报告、无结尾路径报告、路线查询或节点重命名。

用法：
    python dialogue.py validate <文件路径>
    python dialogue.py preview <文件路径> --choice <选项编号> [--node <节点编号>]
    python dialogue.py inspect <文件路径> [--node <节点编号>]
    python dialogue.py references <文件路径> [--node <节点编号>]
    python dialogue.py unreachable <文件路径>
    python dialogue.py no-ending <文件路径>
    python dialogue.py route <文件路径> --node <目标编号>
    python dialogue.py rename-node <文件路径> --node <旧编号> --to <新编号>
    python dialogue.py retarget-option <文件路径> --node <来源编号> --choice <选项编号> --to <目标编号>

preview 省略 --node 时从 start 出发；--choice 与 --node 两对参数顺序可互换。
inspect 省略 --node 时查看 start 指定的节点，只输出该节点信息，不选择选项。
references 省略 --node 时查询 start 指定的节点，列出直接指向该节点的选项。
unreachable 先完成与 validate 相同的整份校验，再报告无法从 start 沿选项
target 到达的节点；起点本身始终可达，报告为只读，不改写输入文件。
no-ending 先完成与 validate 相同的整份校验，再报告从 start 沿选项 target
可达、却不存在任何有限步路径走到结尾（options 为空数组的节点）的节点；
结尾本身按零步到达结尾处理，不可达节点不列入报告，报告为只读。
route 先完成与 validate 相同的整份校验，再给出从 start 到指定节点的
路线：依次经过的选项编号序列，经过选项数量最少者优先，并列时取完整
选项编号序列数值字典序最小者；目标不可达时路线为 null，查询为只读。
rename-node 先完成与 validate 相同的整份校验，再把指定节点的 id 改为
新编号：start 等于旧编号时同步更新，整份对话中所有等于旧编号的
options[].target 一并更新（含不可达来源、重复引用、自引用与循环中的
引用），随后把修改后的完整对话对象以单行 JSON 输出到标准输出；
输入文件字节保持不变，不创建结果文件。
retarget-option 先完成与 validate 相同的整份校验，再只把来源节点
options 中指定选项（编号从 1 开始、按数组顺序确定）的 target 改为
新目标编号：来源与目标均按原字符串精确匹配，不可达来源或目标、
自引用与合法循环都允许，目标与原 target 相同时也成功输出等价对象；
随后把修改后的完整对话对象以单行 JSON 输出到标准输出；输入文件字节
保持不变，不创建结果文件。
仅使用 Python 3 标准库，无需网络、外部账号或额外依赖。
"""

import heapq
import json
import sys

USAGE = (
    "用法：\n"
    "  python dialogue.py validate <文件路径>\n"
    "  python dialogue.py preview <文件路径> --choice <选项编号> "
    "[--node <节点编号>]"
)

# inspect 参数错误专用的用法说明；validate/preview 的用法输出保持原样。
INSPECT_USAGE = USAGE + (
    "\n  python dialogue.py inspect <文件路径> [--node <节点编号>]"
)

# references 参数错误专用的用法说明。
REFERENCES_USAGE = INSPECT_USAGE + (
    "\n  python dialogue.py references <文件路径> [--node <节点编号>]"
)

# unreachable 只接受一个文件路径，参数错误专用的单行用法说明。
UNREACHABLE_USAGE = "python dialogue.py unreachable <文件路径>"

# no-ending 同样只接受一个文件路径，参数错误专用的单行用法说明。
NO_ENDING_USAGE = "python dialogue.py no-ending <文件路径>"

# route 只接受一个文件路径加一次分写的 --node，参数错误专用的单行用法说明。
ROUTE_USAGE = "python dialogue.py route <文件路径> --node <目标编号>"

# rename-node 只接受「路径 + --node 旧编号 + --to 新编号」的固定顺序，
# 参数错误专用的单行用法说明。
RENAME_USAGE = (
    "python dialogue.py rename-node <文件路径> --node <旧编号> --to <新编号>"
)

# retarget-option 只接受「路径 + --node 来源编号 + --choice 选项编号 +
# --to 目标编号」的固定顺序，参数错误专用的单行用法说明。
RETARGET_USAGE = (
    "python dialogue.py retarget-option <文件路径> --node <来源编号>"
    " --choice <选项编号> --to <目标编号>"
)


class DialogueError(Exception):
    """对话文件结构校验失败。"""


def fail(message):
    """向标准错误写一条说明并以退出码 2 结束，不输出调用栈。"""
    sys.stderr.write(message + "\n")
    sys.exit(2)


def is_id_string(value):
    """id、start、target 的要求：至少含一个非空白字符的字符串。"""
    return isinstance(value, str) and value.strip() != ""


def load_dialogue(path):
    """读取并解析 JSON 文件；文件类错误在此统一报告。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        detail = exc.strerror or str(exc)
        fail("无法读取文件 {}：{}".format(path, detail))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("文件 {} 的 UTF-8 解码失败：{}".format(path, exc))
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        fail("文件 {} 存在 JSON 语法错误（第 {} 行第 {} 列）：{}".format(
            path, exc.lineno, exc.colno, exc.msg))


def validate_dialogue(data):
    """校验整份对话数据（含无法从起点到达的节点）。

    成功时返回 (start, nodes)；失败时抛出 DialogueError，
    说明中带 JSON 字段位置，如 nodes[1].id。
    """
    if not isinstance(data, dict):
        raise DialogueError("顶层 JSON 必须是对象")

    if "start" not in data:
        raise DialogueError("缺少字段 start")
    if not is_id_string(data["start"]):
        raise DialogueError("start 必须是至少含一个非空白字符的字符串")
    start = data["start"]

    if "nodes" not in data:
        raise DialogueError("缺少字段 nodes")
    nodes = data["nodes"]
    if not isinstance(nodes, list):
        raise DialogueError("nodes 必须是数组")
    if not nodes:
        raise DialogueError("nodes 必须是非空数组")

    # 第一遍：逐节点校验结构并收集编号，检查重复。
    id_locations = {}
    for i, node in enumerate(nodes):
        loc = "nodes[{}]".format(i)
        if not isinstance(node, dict):
            raise DialogueError("{} 必须是对象".format(loc))
        for field in ("id", "text", "options"):
            if field not in node:
                raise DialogueError("缺少字段 {}.{}".format(loc, field))
        if not is_id_string(node["id"]):
            raise DialogueError("{}.id 必须是至少含一个非空白字符的字符串".format(loc))
        node_id = node["id"]
        if node_id in id_locations:
            raise DialogueError("节点编号重复：{} 与 {}.id 同为 {!r}".format(
                id_locations[node_id], loc, node_id))
        id_locations[node_id] = loc + ".id"
        if not isinstance(node["text"], str):
            raise DialogueError("{}.text 必须是字符串".format(loc))
        options = node["options"]
        if not isinstance(options, list):
            raise DialogueError("{}.options 必须是数组".format(loc))
        for j, option in enumerate(options):
            oloc = "{}.options[{}]".format(loc, j)
            if not isinstance(option, dict):
                raise DialogueError("{} 必须是对象".format(oloc))
            for field in ("text", "target"):
                if field not in option:
                    raise DialogueError("缺少字段 {}.{}".format(oloc, field))
            if not isinstance(option["text"], str):
                raise DialogueError("{}.text 必须是字符串".format(oloc))
            if not is_id_string(option["target"]):
                raise DialogueError(
                    "{}.target 必须是至少含一个非空白字符的字符串".format(oloc))

    # 第二遍：校验 start 与所有 target 的引用（允许循环引用）。
    if start not in id_locations:
        raise DialogueError("start 引用了不存在的节点 {!r}".format(start))
    for i, node in enumerate(nodes):
        for j, option in enumerate(node["options"]):
            if option["target"] not in id_locations:
                raise DialogueError(
                    "nodes[{}].options[{}].target 引用了不存在的节点 {!r}".format(
                        i, j, option["target"]))

    return start, nodes


def load_validated_dialogue(path):
    """读取文件、解析 JSON 并完成整份校验，是各命令共用的前置流程。

    依次复用 load_dialogue（文件读取、UTF-8 解码、JSON 语法错误的报告）
    与 validate_dialogue（含不可达节点在内的结构与引用校验）；校验失败
    在此统一转换为「校验失败：…」说明并以退出码 2 结束。成功时返回
    (start, nodes)，与 validate_dialogue 的返回值一致。
    """
    data = load_dialogue(path)
    try:
        return validate_dialogue(data)
    except DialogueError as exc:
        fail("校验失败：{}".format(exc))


def find_node(nodes, node_id):
    for node in nodes:
        if node["id"] == node_id:
            return node
    return None  # 校验通过后不会发生


def reachable_node_ids(start, nodes):
    """从 start 沿选项 target 可达的节点编号集合。

    起点本身始终计入可达（即使没有选项）；任意分支、任意步数都展开，
    只沿 target 的正向引用访问，不反向。visited 同时充当终止条件，
    因此自引用、重复指向和多节点循环都能正常结束且不重复。
    """
    by_id = {node["id"]: node for node in nodes}
    seen = {start}
    pending = [start]
    while pending:
        current = by_id[pending.pop()]
        for option in current["options"]:
            target = option["target"]
            if target not in seen:
                seen.add(target)
                pending.append(target)
    return seen


def ending_reachable_ids(nodes):
    """能在有限步内沿选项 target 走到某个结尾（options 为空数组）的节点集合。

    结尾本身按零步到达计入；一个节点只要任一选项目标能到结尾，它本身
    也能到结尾（其他选项进入循环不影响结论）。从全部结尾出发沿反向
    引用扩散即可：good 集合同时充当去重与终止条件，因此自引用、多节点
    循环和多个选项指向同一节点都能正常结束，困在纯循环里的节点不会被
    计入；整份文件没有结尾时集合为空。
    """
    reverse = {node["id"]: [] for node in nodes}
    pending = []
    good = set()
    for node in nodes:
        if not node["options"]:
            good.add(node["id"])
            pending.append(node["id"])
        for option in node["options"]:
            reverse[option["target"]].append(node["id"])

    while pending:
        current = pending.pop()
        for predecessor in reverse[current]:
            if predecessor not in good:
                good.add(predecessor)
                pending.append(predecessor)
    return good


def cmd_validate(path):
    load_validated_dialogue(path)
    sys.stdout.write("校验通过\n")
    return 0


def locate_option(options, choice_arg, origin_id, origin_label):
    """按编号定位选项，preview 与 retarget-option 共用的判定流程。

    在出发节点已确定后调用，依次执行：把编号文本解析为整数（沿用 int()
    语义，01、+1 与带首尾空白的 1 均等同于编号 1）、判断结尾无选项、
    检查编号是否在 1 到选项总数范围内（选项按 options 数组顺序从 1
    编号）。任一步失败都以对应说明结束（退出码 2）；origin_label 为
    「起点」或「出发节点」，只决定失败说明中的措辞。成功时返回选中的
    选项对象本身，调用方可读取或改写其 target。
    """
    try:
        choice = int(choice_arg)
    except ValueError:
        fail("--choice 的值 {!r} 无法解析为整数（{}编号为 {!r}）".format(
            choice_arg, origin_label, origin_id))
    if not options:
        fail("--choice {} 无效：{} {!r} 是结尾节点，没有有效选项".format(
            choice, origin_label, origin_id))
    if not 1 <= choice <= len(options):
        fail("--choice {} 不在{} {!r} 的有效选项编号范围 1 到 {} 内".format(
            choice, origin_label, origin_id, len(options)))
    return options[choice - 1]


def cmd_preview(path, choice_arg, node_arg=None):
    # 预览前先完成整份文件校验（未选中分支的结构或引用错误也在此暴露）。
    start, nodes = load_validated_dialogue(path)

    # 省略 --node 时仍从 start 出发；节点编号按原字符串精确匹配。
    origin_id = start if node_arg is None else node_arg
    origin_node = find_node(nodes, origin_id)
    if origin_node is None:
        fail("文件中不存在编号为 {!r} 的节点".format(origin_id))

    # 编号定位选项的流程与 retarget-option 共用一处；省略 --node 时
    # 失败说明使用「起点」措辞，显式指定时使用「出发节点」措辞。
    origin_label = "起点" if node_arg is None else "出发节点"
    option = locate_option(
        origin_node["options"], choice_arg, origin_id, origin_label)

    # 只输出目标节点文字，不前进、不改写文件。
    target_node = find_node(nodes, option["target"])
    sys.stdout.write(target_node["text"] + "\n")
    return 0


def cmd_inspect(path, node_arg=None):
    # 查看前先完成整份文件校验（不可达节点的结构或引用错误也在此暴露）。
    start, nodes = load_validated_dialogue(path)

    # 省略 --node 时查看 start 指定的节点；节点编号按原字符串精确匹配。
    origin_id = start if node_arg is None else node_arg
    origin_node = find_node(nodes, origin_id)
    if origin_node is None:
        fail("文件中不存在编号为 {!r} 的节点".format(origin_id))

    # 只读查看：不选择选项、不沿引用继续访问，也不保存当前节点或改写文件。
    result = {
        "id": origin_node["id"],
        "text": origin_node["text"],
        "options": [
            {"choice": i + 1, "text": option["text"], "target": option["target"]}
            for i, option in enumerate(origin_node["options"])
        ],
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


def cmd_references(path, node_arg=None):
    # 查询前先完成整份文件校验（不可达节点的结构或引用错误也在此暴露）。
    start, nodes = load_validated_dialogue(path)

    # 省略 --node 时查询 start 指定的节点；节点编号按原字符串精确匹配。
    target_id = start if node_arg is None else node_arg
    if find_node(nodes, target_id) is None:
        fail("文件中不存在编号为 {!r} 的节点".format(target_id))

    # 只统计各节点 options 里的直接引用：覆盖整份文件（含不可达来源），
    # 逐项保留同一来源的多个选项，自引用照常计入；start 字段本身不算引用，
    # 也不沿循环关系展开间接引用。结果按 nodes 顺序及各自 options 顺序排列。
    references = []
    for node in nodes:
        for i, option in enumerate(node["options"]):
            if option["target"] == target_id:
                references.append({
                    "source": node["id"],
                    "choice": i + 1,
                    "text": option["text"],
                })
    result = {"id": target_id, "references": references}
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


def cmd_unreachable(path):
    # 报告前先完成与 validate 相同的整份结构与引用校验；不可达节点的
    # 结构或引用非法时同样以校验失败告终，不输出报告。
    start, nodes = load_validated_dialogue(path)

    # 只沿选项 target 的正向引用求可达集合；不可达节点指向可达节点
    # 属于反向边，不会因此被计入。结果按原 nodes 顺序、去重排列。
    reachable = reachable_node_ids(start, nodes)
    unreachable = [node["id"] for node in nodes if node["id"] not in reachable]
    result = {"start": start, "unreachable": unreachable}
    sys.stdout.write(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
    return 0


def cmd_no_ending(path):
    # 报告前先完成与 validate 相同的整份结构与引用校验；不可达节点的
    # 结构或引用非法时同样以校验失败告终，不输出报告。
    start, nodes = load_validated_dialogue(path)

    # 先求从 start 沿 target 的可达集合，再求能在有限步走到结尾的集合；
    # 报告两者之差——已经能进入、却无法走到任何结尾的节点。结果按原
    # nodes 顺序排列且不重复；不可达节点不列入。
    reachable = reachable_node_ids(start, nodes)
    ending_reachable = ending_reachable_ids(nodes)
    no_ending = [
        node["id"]
        for node in nodes
        if node["id"] in reachable and node["id"] not in ending_reachable
    ]
    result = {"start": start, "no_ending": no_ending}
    sys.stdout.write(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
    return 0


def best_route(start, target, nodes):
    """从 start 到 target 的最优路线；不可达时返回 None。

    路线是若干 {"source", "choice", "target"} 步骤组成的列表，按行走
    顺序排列，choice 为从 1 开始的选项编号。优先级：经过选项数量最少
    者；并列时完整选项编号序列按数值字典序最小者（与 nodes 顺序无关）。
    用堆按 (步数, 选项编号序列) 逐条弹出候选路线：每步追加一个选项后
    该比较键保持单调（步数更小者追加后仍不更大，等长时字典序在共同
    前缀下保持），因此节点首次弹出即为其最优路线。visited 充当终止
    条件，自引用、多节点循环与重复指向都能有限结束。
    """
    if start == target:
        return []
    by_id = {node["id"]: node for node in nodes}
    visited = set()
    counter = 0
    # 堆元素：(步数, 选项编号序列, 入堆序号, 节点编号, 路线)；入堆序号
    # 只作并列时的稳定次序，保证不会比较到节点编号或路线本身。
    heap = [(0, (), counter, start, [])]
    while heap:
        length, sequence, _, current, path = heapq.heappop(heap)
        if current in visited:
            continue
        visited.add(current)
        if current == target:
            return path
        for i, option in enumerate(by_id[current]["options"]):
            next_id = option["target"]
            if next_id in visited:
                continue
            counter += 1
            step = {"source": current, "choice": i + 1, "target": next_id}
            heapq.heappush(heap, (
                length + 1, sequence + (i + 1,), counter, next_id,
                path + [step],
            ))
    return None


def cmd_route(path, node_arg):
    # 查询前先完成整份校验（不可达节点的结构或引用错误也在此暴露）。
    start, nodes = load_validated_dialogue(path)

    # 目标编号按原字符串精确匹配，不裁剪首尾空白。
    if find_node(nodes, node_arg) is None:
        fail("文件中不存在编号为 {!r} 的节点".format(node_arg))

    # 只读查询：不沿路线前进、不保存进度，也不改写输入文件。
    result = {"start": start, "target": node_arg,
              "path": best_route(start, node_arg, nodes)}
    sys.stdout.write(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
    return 0


def cmd_rename_node(path, old_id, new_id):
    # 重命名前先完成与 validate 相同的整份结构与引用校验；不可达节点中的
    # 错误同样先于此处报告。保留 load_dialogue 返回的原始对象并在其上
    # 修改，使顶层额外字段、键顺序与全部未涉及的 JSON 值原样保留。
    data = load_dialogue(path)
    try:
        start, nodes = validate_dialogue(data)
    except DialogueError as exc:
        fail("校验失败：{}".format(exc))

    # 旧编号与新编号均按原字符串精确匹配，不裁剪首尾空白。
    if find_node(nodes, old_id) is None:
        fail("文件中不存在编号为 {!r} 的节点".format(old_id))
    if new_id.strip() == "":
        fail("新编号必须包含非空白字符")
    # 新旧编号相同时不视为冲突（占用者就是被重命名的节点本身）。
    if new_id != old_id and find_node(nodes, new_id) is not None:
        fail("新编号已被其他节点使用")

    # 只改 id、start 与等于旧编号的 options[].target：覆盖不可达来源、
    # 同一来源的多个选项、自引用与循环中的引用；节点与选项数组顺序、
    # 全部文字及额外字段的 JSON 值保持原样，即使碰巧等于旧编号也不替换。
    if start == old_id:
        data["start"] = new_id
    for node in nodes:
        if node["id"] == old_id:
            node["id"] = new_id
        for option in node["options"]:
            if option["target"] == old_id:
                option["target"] = new_id

    # 只向标准输出写修改后的完整对话对象（单行 JSON 加换行，中文不转义）；
    # 输入文件字节不变，也不创建任何结果文件。
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    return 0


def cmd_retarget_option(path, source_id, choice_arg, target_id):
    # 重定向前先完成与 validate 相同的整份结构与引用校验；未选中的分支、
    # 不可达节点中的错误，以及待改 target 本身的悬空引用都先在此报出。
    # 保留 load_dialogue 返回的原始对象并在其上修改，使顶层额外字段、
    # 键顺序与全部未涉及的 JSON 值原样保留。
    data = load_dialogue(path)
    try:
        start, nodes = validate_dialogue(data)
    except DialogueError as exc:
        fail("校验失败：{}".format(exc))

    # 来源编号按原字符串精确匹配，不裁剪首尾空白。
    source_node = find_node(nodes, source_id)
    if source_node is None:
        fail("文件中不存在编号为 {!r} 的节点".format(source_id))

    # 编号定位选项的流程与 preview 共用一处，措辞固定为「出发节点」；
    # 新目标的存在性检查在选项定位成功之后才进行。
    option = locate_option(
        source_node["options"], choice_arg, source_id, "出发节点")

    # 目标编号按原字符串精确匹配，不裁剪首尾空白；不可达目标、自引用与
    # 合法循环都允许，因此此处只检查编号存在，不再做可达性分析。
    if find_node(nodes, target_id) is None:
        fail("文件中不存在编号为 {!r} 的节点".format(target_id))

    # 只改选中项的 target：start、节点编号、全部文字、其他选项的引用、
    # 额外字段的 JSON 值及节点与选项数组顺序全部保持原样；目标与原
    # target 相同时这一赋值为幂等操作，输出与原对象等价。
    option["target"] = target_id

    # 只向标准输出写修改后的完整对话对象（单行 JSON 加换行，中文不转义）；
    # 输入文件字节不变，也不创建任何结果文件。
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    return 0


def parse_optional_node_args(rest, usage):
    """解析可选的 --node 键值对（至多一次），inspect 与 references 共用。

    rest 形如 [] 或 ['--node', 'n']：省略时返回 None，显式给出时按
    原字符串返回节点编号（不裁剪空白，空字符串及形似选项的值也照收，
    留给后续节点查找）。任何多余、重复、缺值或 --node=编号 连写形式的
    参数都按用法错误处理，以调用方给定的 usage 文字报告，
    并在读取文件前结束。
    """
    if not rest:
        return None
    if len(rest) == 2 and rest[0] == "--node":
        return rest[1]
    fail(usage)


def parse_inspect_args(rest):
    """解析 inspect 可选的 --node 键值对，规则与 references 共用一处。"""
    return parse_optional_node_args(rest, INSPECT_USAGE)


def parse_references_args(rest):
    """解析 references 可选的 --node 键值对，规则与 inspect 共用一处。"""
    return parse_optional_node_args(rest, REFERENCES_USAGE)


def parse_preview_args(rest):
    """解析 preview 的 --choice/--node 键值对（顺序可互换、各至多一次）。

    rest 形如 ['--choice', '2', '--node', 'n']；任何多余、
    重复或缺值参数都按既有用法错误处理。
    """
    values = {}
    i = 0
    while i < len(rest):
        name = rest[i]
        if name not in ("--choice", "--node"):
            fail(USAGE)
        if name in values:
            fail(USAGE)
        if i + 1 >= len(rest):
            fail(USAGE)
        values[name] = rest[i + 1]
        i += 2
    if "--choice" not in values:
        fail(USAGE)
    return values["--choice"], values.get("--node")


def main(argv):
    if len(argv) < 2:
        fail(USAGE)
    command = argv[1]
    if command == "validate":
        if len(argv) != 3:
            fail(USAGE)
        return cmd_validate(argv[2])
    if command == "preview":
        if len(argv) < 5:
            fail(USAGE)
        choice_arg, node_arg = parse_preview_args(argv[3:])
        return cmd_preview(argv[2], choice_arg, node_arg)
    if command == "inspect":
        if len(argv) < 3:
            fail(INSPECT_USAGE)
        node_arg = parse_inspect_args(argv[3:])
        return cmd_inspect(argv[2], node_arg)
    if command == "references":
        if len(argv) < 3:
            fail(REFERENCES_USAGE)
        node_arg = parse_references_args(argv[3:])
        return cmd_references(argv[2], node_arg)
    if command == "unreachable":
        # 只接受一个文件路径：缺少路径、额外位置参数或任何选项参数
        # 都在读取文件前以单行用法说明拒绝。形如选项的记号也不当作路径，
        # 避免对其触发文件读取。
        if len(argv) != 3 or argv[2].startswith("-"):
            fail(UNREACHABLE_USAGE)
        return cmd_unreachable(argv[2])
    if command == "no-ending":
        # 规则与 unreachable 相同：只接受一个文件路径，任何缺参、多余
        # 参数、选项参数或路径位置形似选项的记号都在读文件前拒绝。
        if len(argv) != 3 or argv[2].startswith("-"):
            fail(NO_ENDING_USAGE)
        return cmd_no_ending(argv[2])
    if command == "route":
        # 只接受「一个文件路径 + 一次分写的 --node 目标」：缺少路径或目标
        # 值、--node 重复、未知或额外参数、--node=编号 连写形式，以及路径
        # 位置形似选项的记号，都在读取文件前以单行用法说明拒绝。
        if (len(argv) != 5 or argv[2].startswith("-")
                or argv[3] != "--node"):
            fail(ROUTE_USAGE)
        return cmd_route(argv[2], argv[4])
    if command == "rename-node":
        # 只接受「一个文件路径 + 一次分写的 --node 旧编号 + 一次分写的
        # --to 新编号」的固定顺序：缺少路径或编号值、--node/--to 重复、
        # 未知或额外参数、--node=编号 或 --to=编号 连写形式、两对参数
        # 顺序颠倒，以及路径位置形似选项的记号，都在读取文件前以单行
        # 用法说明拒绝。
        if (len(argv) != 7 or argv[2].startswith("-")
                or argv[3] != "--node" or argv[5] != "--to"):
            fail(RENAME_USAGE)
        return cmd_rename_node(argv[2], argv[4], argv[6])
    if command == "retarget-option":
        # 只接受「一个文件路径 + 一次分写的 --node 来源编号 + 一次分写的
        # --choice 选项编号 + 一次分写的 --to 目标编号」的固定顺序：缺少
        # 路径或任一编号值、--node/--choice/--to 重复、未知或额外参数、
        # --node=编号、--choice=1 或 --to=编号 连写形式、三对参数顺序
        # 颠倒，以及路径位置形似选项的记号，都在读取文件前以单行用法
        # 说明拒绝。
        if (len(argv) != 9 or argv[2].startswith("-")
                or argv[3] != "--node" or argv[5] != "--choice"
                or argv[7] != "--to"):
            fail(RETARGET_USAGE)
        return cmd_retarget_option(argv[2], argv[4], argv[6], argv[8])
    fail(USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
