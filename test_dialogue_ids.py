# -*- coding: utf-8 -*-
"""dialogue.py validate 对节点标识与引用匹配规则的命令行回归测试。

只覆盖标识字段（start、nodes[i].id、options[j].target）的取值规则
与编号精确匹配规则：

- 三类标识字段都必须是至少含一个非空白字符的字符串：空字符串、仅含
  空格/制表/换行的字符串、null、数字、布尔值一律拒绝，错误定位到
  被修改的具体字段；每份样例只改变一个字段。
- 整份校验不跳过不可达节点：没有被任何选项引用的节点，其空白 id
  同样被拒绝，错误位置对应该节点的 id。
- 编号不做首尾空白归一化："room" 与 " room " 是两个不同的节点编号，
  start 与选项按原字符串精确引用时校验通过；中文编号同理。
- 仅存在带首尾空格编号时，把 start 或选项 target 写成不带空格的
  room 分别报 start 悬空引用与该选项 target 悬空引用，并点名不存在
  的编号；两个完全相同的带空格编号仍算重复，同时定位两个 id 字段。

不在本文件范围：命令参数解析、文件读取与 UTF-8/JSON 解码（分别由
test_dialogue_*_args.py、test_dialogue_load.py 覆盖），也不改动
sample.json 与业务源码。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：真实退出码、标准输出、标准错误（以「校验失败：」开头、
无调用栈）以及调用前后输入文件字节一致，而非仅检查进程结束。
所有派生样例独立写入临时目录并自动清理，可重复运行且结果一致。
"""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIALOGUE = PROJECT_DIR / "dialogue.py"

OK_MESSAGE = "校验通过\n"

# 独立的小型合法对话：start 与 nodes[0].id 精确相等，nodes[0] 的唯一
# 选项指向 nodes[1]。标识类用例以此为对照，每份只改其中一个字段。
VALID_DIALOGUE = {
    "start": "room",
    "nodes": [
        {
            "id": "room",
            "text": "你在房间里。",
            "options": [{"text": "走进走廊", "target": "hall"}],
        },
        {"id": "hall", "text": "你到了走廊。", "options": []},
    ],
}

# (错误信息中的字段定位, 在对话数据中的取值路径)
ID_FIELDS = [
    ("start", ("start",)),
    ("nodes[0].id", ("nodes", 0, "id")),
    (
        "nodes[0].options[0].target",
        ("nodes", 0, "options", 0, "target"),
    ),
]

# (用例说明, 非法取值)
BAD_ID_VALUES = [
    ("空字符串", ""),
    ("仅含空格制表换行的字符串", "  \t\n "),
    ("null", None),
    ("数字", 42),
    ("布尔值", True),
]


def run_validate(path):
    """以命令行方式执行 validate，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "validate", str(path)],
        capture_output=True,
    )


def assign(data, keys, value):
    """沿 keys 路径把嵌套字段改为 value（keys 至少一个元素）。"""
    target = data
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value


class IdRulesTestCase(unittest.TestCase):
    """公共断言：临时样例写入与清理、文件字节不变、退出码与两个输出流。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def valid_dialogue(self):
        """深拷贝合法对照数据，各用例之间互不影响。"""
        return copy.deepcopy(VALID_DIALOGUE)

    def make_sample(self, data, name="case.json"):
        """把数据写成独立的临时 UTF-8 JSON 样例文件，返回路径。"""
        path = self.tmp_dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def run_and_assert_ok(self, path):
        """成功：退出码 0，标准错误为空，标准输出仅为校验通过加一个换行。"""
        before = path.read_bytes()
        result = run_validate(path)
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"),
            OK_MESSAGE,
            "标准输出应只有校验通过和一个结尾换行",
        )
        return result

    def run_and_assert_fail(self, path, expected_stderr):
        """失败：退出码 2，标准输出为空，标准错误与预期逐字节相等。

        expected_stderr 必须以「校验失败：」开头并带恰好一个结尾换行，
        且不含调用栈。
        """
        before = path.read_bytes()
        result = run_validate(path)
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assertEqual(stderr, expected_stderr)
        self.assertTrue(
            stderr.startswith("校验失败："),
            "标准错误应以校验失败：开头，实际为 {!r}".format(stderr),
        )
        self.assertTrue(stderr.endswith("\n"), "标准错误应以一个换行结尾")
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")
        return result


class TestValidIds(IdRulesTestCase):
    """成功路径：合法标识与精确引用。"""

    def test_valid_control_dialogue_passes(self):
        """合法对话对照：退出码 0、标准错误空、标准输出仅校验通过加换行。"""
        path = self.make_sample(self.valid_dialogue())
        self.run_and_assert_ok(path)

    def test_padded_id_is_distinct_from_unpadded_id(self):
        """room 与带首尾空格的 " room " 同时作为不同节点编号。

        start 精确引用 room，一个选项精确引用 " room "；编号不做
        去首尾空白处理，校验通过（若偷偷 strip，两者会被判为重复）。
        """
        data = {
            "start": "room",
            "nodes": [
                {
                    "id": "room",
                    "text": "你在房间里。",
                    "options": [{"text": "走进隔壁", "target": " room "}],
                },
                {"id": " room ", "text": "你到了隔壁房间。", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_ok(path)

    def test_chinese_ids_with_exact_references_pass(self):
        """中文编号及对它的精确 start/选项引用：校验通过。"""
        data = {
            "start": "房间",
            "nodes": [
                {
                    "id": "房间",
                    "text": "你在房间里。",
                    "options": [{"text": "走进森林", "target": "森林"}],
                },
                {"id": "森林", "text": "你到了森林。", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_ok(path)


class TestInvalidIdValues(IdRulesTestCase):
    """标识字段取值规则：三类字段分别只引入一个非法值。"""

    def test_each_id_field_rejects_invalid_values(self):
        """start/nodes[0].id/nodes[0].options[0].target 分别改为空串、
        纯空白、null、数字、布尔：退出码 2 且错误点名被修改的字段。"""
        for field_label, field_path in ID_FIELDS:
            for value_label, bad_value in BAD_ID_VALUES:
                with self.subTest(field=field_label, value=value_label):
                    data = self.valid_dialogue()
                    assign(data, field_path, bad_value)
                    path = self.make_sample(data)
                    expected_stderr = (
                        "校验失败：{} 必须是至少含一个非空白字符的字符串\n".format(
                            field_label
                        )
                    )
                    self.run_and_assert_fail(path, expected_stderr)

    def test_unreachable_node_blank_id_is_still_rejected(self):
        """追加一个无任何选项引用的不可达节点，其 id 为纯空白：
        整份校验仍拒绝它，定位 nodes[2].id，不因不可达而跳过。"""
        data = self.valid_dialogue()
        data["nodes"].append(
            {"id": "  \t\n ", "text": "无人抵达的角落。", "options": []}
        )
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path,
            "校验失败：nodes[2].id 必须是至少含一个非空白字符的字符串\n",
        )


class TestExactIdMatching(IdRulesTestCase):
    """编号精确匹配：空白不参与归一化，悬空与重复按原字符串判定。"""

    def test_start_dangling_when_only_padded_id_exists(self):
        """只有编号 " room " 的节点，start 写成不带空格的 room：
        报 start 的悬空引用并点名不存在的编号 room。"""
        data = {
            "start": "room",
            "nodes": [
                {"id": " room ", "text": "你到了隔壁房间。", "options": []}
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "校验失败：start 引用了不存在的节点 'room'\n"
        )

    def test_option_target_dangling_when_only_padded_id_exists(self):
        """start 精确引用 " room "，而选项 target 写成不带空格的 room：
        报该选项 target 的悬空引用，定位 nodes[0].options[0].target
        并点名不存在的编号 room。"""
        data = {
            "start": " room ",
            "nodes": [
                {
                    "id": " room ",
                    "text": "你在房间里。",
                    "options": [{"text": "走出去", "target": "room"}],
                }
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path,
            "校验失败：nodes[0].options[0].target 引用了不存在的节点 'room'\n",
        )

    def test_identical_padded_ids_are_duplicates(self):
        """两个完全相同的带首尾空格编号仍视为重复，错误同时定位
        nodes[0].id 与 nodes[1].id 并给出相同的编号。"""
        data = {
            "start": " room ",
            "nodes": [
                {"id": " room ", "text": "第一个房间。", "options": []},
                {"id": " room ", "text": "第二个房间。", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path,
            "校验失败：节点编号重复：nodes[0].id 与 nodes[1].id 同为 ' room '\n",
        )


if __name__ == "__main__":
    unittest.main()
