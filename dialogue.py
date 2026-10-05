#!/usr/bin/env python3
"""本地对话文件校验与分支预览工具（仅使用 Python 3 标准库）。

用法：
    python dialogue.py validate <文件路径>
    python dialogue.py preview <文件路径> --choice <选项编号>
"""

import argparse
import json
import sys


class DialogueError(Exception):
    """一切面向用户的错误：消息写入标准错误，退出码为 2。"""


def fail(message):
    raise DialogueError(message)


def is_valid_id(value):
    """id / start / target：至少含一个非空白字符的字符串。"""
    return isinstance(value, str) and value.strip() != ""


def load_dialogue(path):
    """读取并解析 JSON 文件，文件与语法错误在此统一转换。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        fail("无法读取文件 %s：%s" % (path, exc.strerror or exc))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("文件 %s 不是有效的 UTF-8：%s" % (path, exc))
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        fail("文件 %s 存在 JSON 语法错误（第 %d 行第 %d 列）：%s"
             % (path, exc.lineno, exc.colno, exc.msg))


def validate_structure(data):
    """校验整份文件结构，返回 {节点 id: 节点} 映射。"""
    if not isinstance(data, dict):
        fail("结构错误：顶层必须是 JSON 对象")

    start = data.get("start")
    if "start" not in data:
        fail("结构错误：缺少字段 start")
    if not is_valid_id(start):
        fail("结构错误：start 必须是至少含一个非空白字符的字符串")

    if "nodes" not in data:
        fail("结构错误：缺少字段 nodes")
    nodes = data["nodes"]
    if not isinstance(nodes, list) or not nodes:
        fail("结构错误：nodes 必须是非空数组")

    by_id = {}
    for i, node in enumerate(nodes):
        loc = "nodes[%d]" % i
        if not isinstance(node, dict):
            fail("结构错误：%s 必须是对象" % loc)

        if "id" not in node:
            fail("结构错误：%s 缺少字段 id" % loc)
        node_id = node["id"]
        if not is_valid_id(node_id):
            fail("结构错误：%s.id 必须是至少含一个非空白字符的字符串" % loc)
        if node_id in by_id:
            fail("结构错误：节点编号 %r 重复，出现在 %s.id 和 %s.id"
                 % (node_id, by_id[node_id][0], loc))
        by_id[node_id] = (loc, node)

        if "text" not in node:
            fail("结构错误：%s 缺少字段 text" % loc)
        if not isinstance(node["text"], str):
            fail("结构错误：%s.text 必须是字符串" % loc)

        if "options" not in node:
            fail("结构错误：%s 缺少字段 options" % loc)
        options = node["options"]
        if not isinstance(options, list):
            fail("结构错误：%s.options 必须是数组" % loc)

        for j, option in enumerate(options):
            oloc = "%s.options[%d]" % (loc, j)
            if not isinstance(option, dict):
                fail("结构错误：%s 必须是对象" % oloc)
            if "text" not in option:
                fail("结构错误：%s 缺少字段 text" % oloc)
            if not isinstance(option["text"], str):
                fail("结构错误：%s.text 必须是字符串" % oloc)
            if "target" not in option:
                fail("结构错误：%s 缺少字段 target" % oloc)
            if not is_valid_id(option["target"]):
                fail("结构错误：%s.target 必须是至少含一个非空白字符的字符串"
                     % oloc)

    if start not in by_id:
        fail("结构错误：start 引用了不存在的节点 %r" % start)

    for i, node in enumerate(nodes):
        for j, option in enumerate(node["options"]):
            target = option["target"]
            if target not in by_id:
                fail("结构错误：nodes[%d].options[%d].target 引用了不存在的节点 %r"
                     % (i, j, target))

    return {node_id: node for node_id, (_, node) in by_id.items()}


def cmd_validate(path):
    data = load_dialogue(path)
    validate_structure(data)
    print("校验通过")
    return 0


def cmd_preview(path, choice_raw):
    data = load_dialogue(path)
    by_id = validate_structure(data)
    start_node = by_id[data["start"]]
    options = start_node["options"]

    try:
        choice = int(choice_raw, 10)
    except ValueError:
        fail("--choice 的值 %r 不是整数；起点 %r 的有效编号为 1 到 %d"
             % (choice_raw, data["start"], len(options)))
    if not 1 <= choice <= len(options):
        if not options:
            fail("--choice 无效：起点 %r 是结尾节点，没有有效选项"
                 % data["start"])
        fail("--choice 的值 %d 超出范围；起点 %r 的有效编号为 1 到 %d"
             % (choice, data["start"], len(options)))

    target_id = options[choice - 1]["target"]
    print(by_id[target_id]["text"])
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dialogue.py",
        description="对话文件校验与分支预览")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="校验对话文件")
    p_validate.add_argument("path", help="对话 JSON 文件路径（可含空格）")

    p_preview = sub.add_parser("preview", help="预览起点某选项的目标文本")
    p_preview.add_argument("path", help="对话 JSON 文件路径（可含空格）")
    p_preview.add_argument("--choice", required=True,
                           help="选项编号，从 1 开始")

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return cmd_validate(args.path)
        return cmd_preview(args.path, args.choice)
    except DialogueError as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
