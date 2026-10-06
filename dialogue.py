#!/usr/bin/env python3
"""本地对话命令行程序：校验对话 JSON 结构，进行一次分支预览或只读节点查看。

用法：
    python dialogue.py validate <文件路径>
    python dialogue.py preview <文件路径> --choice <选项编号> [--node <节点编号>]
    python dialogue.py inspect <文件路径> [--node <节点编号>]

preview 省略 --node 时从 start 出发；--choice 与 --node 两对参数顺序可互换。
inspect 省略 --node 时查看 start 指定的节点，只输出该节点信息，不选择选项。
仅使用 Python 3 标准库，无需网络、外部账号或额外依赖。
"""

import json
import sys

USAGE = (
    "用法：\n"
    "  python dialogue.py validate <文件路径>\n"
    "  python dialogue.py preview <文件路径> --choice <选项编号> "
    "[--node <节点编号>]\n"
    "  python dialogue.py inspect <文件路径> [--node <节点编号>]"
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


def find_node(nodes, node_id):
    for node in nodes:
        if node["id"] == node_id:
            return node
    return None  # 校验通过后不会发生


def cmd_validate(path):
    data = load_dialogue(path)
    try:
        validate_dialogue(data)
    except DialogueError as exc:
        fail("校验失败：{}".format(exc))
    sys.stdout.write("校验通过\n")
    return 0


def cmd_preview(path, choice_arg, node_arg=None):
    # 预览前先完成整份文件校验（未选中分支的结构或引用错误也在此暴露）。
    data = load_dialogue(path)
    try:
        start, nodes = validate_dialogue(data)
    except DialogueError as exc:
        fail("校验失败：{}".format(exc))

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
    # 查看前先完成整份文件校验（含不可达节点的结构或引用错误）。
    data = load_dialogue(path)
    try:
        start, nodes = validate_dialogue(data)
    except DialogueError as exc:
        fail("校验失败：{}".format(exc))

    # 省略 --node 时查看 start 指定的节点；节点编号按原字符串精确匹配。
    node_id = start if node_arg is None else node_arg
    node = find_node(nodes, node_id)
    if node is None:
        fail("文件中不存在编号为 {!r} 的节点".format(node_id))

    # 只读查看：不选择选项、不沿 target 继续访问、不保存状态、不改写文件。
    result = {
        "id": node["id"],
        "text": node["text"],
        "options": [
            {"choice": i + 1, "text": option["text"], "target": option["target"]}
            for i, option in enumerate(node["options"])
        ],
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


def parse_inspect_args(rest):
    """解析 inspect 可选的 --node 键值对（至多一次，不接受其他参数）。

    rest 为空表示省略 --node；形如 ['--node', 'n'] 时返回节点编号；
    多余、重复或缺值参数都按既有用法错误处理，在读取文件前结束。
    """
    if not rest:
        return None
    if len(rest) == 2 and rest[0] == "--node":
        return rest[1]
    fail(USAGE)


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
            fail(USAGE)
        node_arg = parse_inspect_args(argv[3:])
        return cmd_inspect(argv[2], node_arg)
    fail(USAGE)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
