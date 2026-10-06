# -*- coding: utf-8 -*-
"""dialogue.py 节点编号及引用匹配规则（validate）命令行回归测试。

只覆盖编号字段（start、nodes[*].id、options[*].target）的取值要求与
编号的精确匹配规则，不涉及参数解析或文件解码：

- 以小型合法对话为成功对照，逐字段把 start、nodes[0].id、
  nodes[0].options[0].target 分别改为空字符串、仅含空格/制表/换行的
  字符串、null、数字、布尔值（每份样例只改一个字段），均以退出码 2
  拒绝，标准错误逐字指出被修改字段及编号取值要求；
- 不可达节点的空白 id 同样在整份校验中被拒绝，定位对应该节点 id，
  不因其没有被任何选项引用而跳过；
- 编号不做首尾空白归一化："room" 与 " room " 是两个不同编号，
  start 与一个选项分别精确引用它们时通过；中文编号同样精确匹配；
- 只存在 " room " 时，start 或选项 target 写成不带空格的 "room"，
  分别报 start 与该选项 target 的悬空引用，错误中包含不存在的编号；
- 两个完全相同的 " room " 仍被视为重复，错误同时定位两个 id 字段。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：真实退出码、标准输出、标准错误（逐字核对，而非仅检查进程
结束），以及输入文件在调用前后字节一致。所有派生样例独立写入临时
目录（小型 UTF-8 JSON）并自动清理，不改动 sample.json、业务源码与
既有测试，用例可重复运行且结果一致。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIALOGUE = PROJECT_DIR / "dialogue.py"

OK_MESSAGE = "校验通过\n"
FAIL_PREFIX = "校验失败："
ID_REQUIREMENT = "必须是至少含一个非空白字符的字符串"

PADDED_ID = " room "
PLAIN_ID = "room"


def base_dialogue():
    """小型合法对话：start 精确引用 nodes[0]，其选项引用 nodes[1]。"""
    return {
        "start": "room",
        "nodes": [
            {
                "id": "room",
                "text": "你在房间里。",
                "options": [{"text": "走进走廊", "target": "hall"}],
            },
            {"id": "hall", "text": "你来到走廊尽头。", "options": []},
        ],
    }


# 每个元组：(文件名片段, 只改动一个字段的函数, 错误信息中的字段定位)。
def _set_start(data, value):
    data["start"] = value


def _set_first_node_id(data, value):
    data["nodes"][0]["id"] = value


def _set_first_option_target(data, value):
    data["nodes"][0]["options"][0]["target"] = value


FIELD_CASES = [
    ("start", _set_start, "start"),
    ("nodes_0_id", _set_first_node_id, "nodes[0].id"),
    (
        "nodes_0_options_0_target",
        _set_first_option_target,
        "nodes[0].options[0].target",
    ),
]

# 五类非法取值：空字符串、仅含空格/制表/换行的字符串、null、数字、布尔值。
BAD_VALUES = [
    ("empty_string", ""),
    ("spaces_tab_newline", "  \t\n  "),
    ("null", None),
    ("number", 123),
    ("boolean", True),
]


def run_validate(path):
    """通过公开入口 python dialogue.py validate 调用，返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "validate", str(path)],
        capture_output=True,
    )


class IdsTestCase(unittest.TestCase):
    """公共断言：临时 UTF-8 JSON 样例写入与清理、文件字节不变、流与退出码。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def write_case(self, data, name="case.json"):
        """把数据写成独立的小型临时 UTF-8 JSON 样例文件，返回路径。"""
        path = self.tmp_dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def assert_success(self, path):
        """成功：退出码 0，标准错误为空，标准输出仅为校验通过加一个结尾换行。"""
        before = path.read_bytes()
        result = run_validate(path)
        self.assertEqual(
            before, path.read_bytes(), "输入文件在执行后发生变化：{}".format(path)
        )
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"),
            OK_MESSAGE,
            "标准输出应只有校验通过和一个结尾换行",
        )

    def assert_failure_line(self, path, expected_line):
        """失败：退出码 2，标准输出为空，标准错误逐字等于预期单行（含换行）。

        expected_line 必须以「校验失败：」开头；另显式拒绝调用栈，
        并核对调用前后输入文件字节不变。
        """
        before = path.read_bytes()
        result = run_validate(path)
        self.assertEqual(
            before, path.read_bytes(), "输入文件在执行后发生变化：{}".format(path)
        )
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assertTrue(
            stderr.startswith(FAIL_PREFIX),
            "标准错误应以校验失败：开头，实际为 {!r}".format(stderr),
        )
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")
        self.assertEqual(stderr, expected_line, "标准错误应逐字等于预期提示")


class TestValidControl(IdsTestCase):
    """成功对照：未改动的小型合法对话。"""

    def test_control_dialogue_passes(self):
        """合法对话：退出码 0，标准输出仅校验通过加换行，标准错误为空。"""
        self.assert_success(self.write_case(base_dialogue()))


class TestInvalidIdFieldValues(IdsTestCase):
    """三个编号字段分别取五类非法值：每份样例只改变一个字段。"""

    def test_each_field_rejects_each_bad_value(self):
        for file_stem, mutate, location in FIELD_CASES:
            for value_name, value in BAD_VALUES:
                with self.subTest(field=location, value=value_name):
                    data = base_dialogue()
                    mutate(data, value)
                    path = self.write_case(
                        data, "{}_{}.json".format(file_stem, value_name)
                    )
                    self.assert_failure_line(
                        path,
                        "{}{} {}\n".format(FAIL_PREFIX, location, ID_REQUIREMENT),
                    )


class TestUnreachableBlankId(IdsTestCase):
    """不可达节点的编号问题仍在整份校验中暴露。"""

    def test_unreachable_node_whitespace_id_rejected(self):
        """追加无任何选项指向的节点，其 id 仅含空格/制表/换行：
        定位到 nodes[2].id，不因不可达而跳过。"""
        data = base_dialogue()
        data["nodes"].append(
            {"id": "  \t\n  ", "text": "无人抵达的角落。", "options": []}
        )
        path = self.write_case(data)
        self.assert_failure_line(
            path,
            "{}nodes[2].id {}\n".format(FAIL_PREFIX, ID_REQUIREMENT),
        )


class TestExactIdMatchingSuccess(IdsTestCase):
    """编号按原字符串精确匹配，不自动去除首尾空白。"""

    def test_padded_and_plain_ids_coexist_as_distinct_nodes(self):
        """room 与带首尾空格的 room 同时作为不同节点编号；start 精确
        引用带空格编号，选项精确引用不带空格编号，校验通过。"""
        data = {
            "start": PADDED_ID,
            "nodes": [
                {
                    "id": PADDED_ID,
                    "text": "编号带首尾空格的房间。",
                    "options": [
                        {"text": "进入不带空格的房间", "target": PLAIN_ID}
                    ],
                },
                {"id": PLAIN_ID, "text": "编号不带空格的房间。", "options": []},
            ],
        }
        self.assert_success(self.write_case(data))

    def test_chinese_ids_matched_exactly(self):
        """中文编号及其精确引用（start 与选项各一处）校验通过。"""
        data = {
            "start": "房间",
            "nodes": [
                {
                    "id": "房间",
                    "text": "你在房间里。",
                    "options": [{"text": "走向大厅", "target": "大厅"}],
                },
                {"id": "大厅", "text": "你来到大厅。", "options": []},
            ],
        }
        self.assert_success(self.write_case(data))


class TestNoWhitespaceNormalization(IdsTestCase):
    """只存在带首尾空格编号时，不带空格的引用必须报悬空引用。"""

    def test_start_plain_id_does_not_match_padded_id(self):
        """start 改为不带空格的 room，节点只有带空格的 room：
        报告 start 的悬空引用并包含不存在的编号，选项引用仍然有效。"""
        data = {
            "start": PLAIN_ID,
            "nodes": [
                {
                    "id": PADDED_ID,
                    "text": "只有带空格编号的房间。",
                    "options": [{"text": "留在原地", "target": PADDED_ID}],
                }
            ],
        }
        path = self.write_case(data)
        self.assert_failure_line(
            path,
            "{}start 引用了不存在的节点 {!r}\n".format(FAIL_PREFIX, PLAIN_ID),
        )

    def test_target_plain_id_does_not_match_padded_id(self):
        """start 精确引用带空格编号，唯一选项 target 改为不带空格的
        room：报告该选项 target 的悬空引用并包含不存在的编号。"""
        data = {
            "start": PADDED_ID,
            "nodes": [
                {
                    "id": PADDED_ID,
                    "text": "只有带空格编号的房间。",
                    "options": [{"text": "走进房间", "target": PLAIN_ID}],
                }
            ],
        }
        path = self.write_case(data)
        self.assert_failure_line(
            path,
            "{}nodes[0].options[0].target 引用了不存在的节点 {!r}\n".format(
                FAIL_PREFIX, PLAIN_ID
            ),
        )

    def test_identical_padded_ids_are_duplicates(self):
        """两个完全相同的带空格编号仍被视为重复，错误同时定位两个 id。"""
        data = {
            "start": PADDED_ID,
            "nodes": [
                {
                    "id": PADDED_ID,
                    "text": "第一间带空格编号的房间。",
                    "options": [{"text": "转身", "target": PADDED_ID}],
                },
                {"id": PADDED_ID, "text": "第二间带空格编号的房间。", "options": []},
            ],
        }
        path = self.write_case(data)
        self.assert_failure_line(
            path,
            "{}节点编号重复：nodes[0].id 与 nodes[1].id 同为 {!r}\n".format(
                FAIL_PREFIX, PADDED_ID
            ),
        )


if __name__ == "__main__":
    unittest.main()
