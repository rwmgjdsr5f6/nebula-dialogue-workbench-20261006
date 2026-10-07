#!/usr/bin/env python3
"""本地对话命令行程序：校验对话 JSON 结构，并进行一次分支预览、只读节点查看、入向引用查询、不可达节点报告或无结尾路径报告。

用法：
    python dialogue.py validate <文件路径>
    python dialogue.py preview <文件路径> --choice <选项编号> [--node <节点编号>]
    python dialogue.py inspect <文件路径> [--node <节点编号>]
    python dialogue.py references <文件路径> [--node <节点编号>]
    python dialogue.py unreachable <文件路径>
    python dialogue.py no-ending <文件路径>

preview 省略 --node 时从 start 出发；--choice 与 --node 两对参数顺序可互换。
inspect 省略 --node 时查看 start 指定的节点，只输出该节点信息，不选择选项。
references 省略 --node 时查询 start 指定的节点，列出直接指向该节点的选项。
unreachable 先完成与 validate 相同的整份校验，再报告无法从 start 沿选项
target 到达的节点；起点本身始终可达，报告为只读，不改写输入文件。
no-ending 先完成与 validate 相同的整份校验，再报告从 start 沿选项 target
可达、却不存在任何有限步路径走到 options 为空的结尾节点的节点；
结尾本身按零步到达结尾处理，不可达节点不列入报告。
仅使用 Python 3 标准库，无需网络、外部账号或额外依赖。
"""

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

# no-ending 只接受一个文件路径，参数错误专用的单行用法说明。
NO_ENDING_USAGE = "python dialogue.py no-ending <文件路径>"


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


def can_reach_ending_ids(nodes):
    """能够沿选项 target 以有限步走到某个结尾节点的节点编号集合。

    options 为空数组的节点本身是结尾，按零步到达计入；其余节点只要
    存在一个选项的目标已在集合中，就一并计入。从全部结尾出发沿反向
    引用逐层扩展直到不再新增，因此只要存在一条到结尾的路径就计入，
    即使其他选项会进入循环；整份文件没有结尾时返回空集合。
    """
    by_id = {node["id"]: node for node in nodes}
    reverse = {node["id"]: [] for node in nodes}
    good = set()
    for node in nodes:
        if not node["options"]:
            good.add(node["id"])
        for option in node["options"]:
            reverse[option["target"]].append(node["id"])
    pending = list(good)
    while pending:
        target = pending.pop()
        for source in reverse[target]:
            if source not in good:
                good.add(source)
                pending.append(source)
    return good


def cmd_validate(path):
    load_validated_dialogue(path)
    sys.stdout.write("校验通过\n")
    return 0


def cmd_preview(path, choice_arg, node_arg=None):
    # 预览前先完成整份文件校验（未选中分支的结构或引用错误也在此暴露）。
    start, nodes = load_validated_dialogue(path)

    # 省略 --node 时仍从 start 出发；节点编号按原字符串精确匹配。
    origin_id = start if node_arg is None else node_arg
    origin_node = find_node(nodes, origin_id)
    if origin_node is None:
        fail("文件中不存在编号为 {!r} 的节点".format(origin_id))
    options = origin_node["options"]

    try:
        choice = int(choice_arg)
    except ValueError:
        if node_arg is None:
            fail("--choice 的值 {!r} 无法解析为整数（起点编号为 {!r}）".format(
                choice_arg, origin_id))
        fail("--choice 的值 {!r} 无法解析为整数（出发节点编号为 {!r}）".format(
            choice_arg, origin_id))

    if not options:
        if node_arg is None:
            fail("--choice {} 无效：起点 {!r} 是结尾节点，没有有效选项".format(
                choice, origin_id))
        fail("--choice {} 无效：出发节点 {!r} 是结尾节点，没有有效选项".format(
            choice, origin_id))
    if not 1 <= choice <= len(options):
        if node_arg is None:
            fail("--choice {} 不在起点 {!r} 的有效选项编号范围 1 到 {} 内".format(
                choice, origin_id, len(options)))
        fail("--choice {} 不在出发节点 {!r} 的有效选项编号范围 1 到 {} 内".format(
            choice, origin_id, len(options)))

    # 选项编号从 1 开始，依据数组顺序确定；只输出目标节点文字，不前进、不改写文件。
    target_id = options[choice - 1]["target"]
    target_node = find_node(nodes, target_id)
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

    # 只报告从 start 正向可达的节点；再用「能否在有限步内走到结尾」筛除。
    # 结尾节点本身按零步计入能到达结尾，故不会出现在报告中；整份文件
    # 没有结尾时全部可达节点都列入。结果按原 nodes 顺序、去重排列。
    reachable = reachable_node_ids(start, nodes)
    can_end = can_reach_ending_ids(nodes)
    no_ending = [
        node["id"] for node in nodes
        if node["id"] in reachable and node["id"] not in can_end
    ]
    result = {"start": start, "no_ending": no_ending}
    sys.stdout.write(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
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
        # 与 unreachable 相同的参数规则：只接受一个文件路径，路径位置
        # 以减号开头的记号一律在读取文件前以单行用法说明拒绝。
        if len(argv) != 3 or argv[2].startswith("-"):
            fail(NO_ENDING_USAGE)
        return cmd_no_ending(argv[2])
    fail(USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
