# -*- coding: utf-8 -*-
"""dialogue.py validate 对节点与选项结构要求的回归测试。

在 test_dialogue_validate.py 已覆盖的编号取值、重复编号、悬空引用之外，
本文件固定 validate 现有的结构字段要求（每个失败样例相对合法对照只改一处）：

失败路径（退出码 2，标准输出为空，标准错误严格为
``校验失败：<原因>\\n`` 且不含调用栈）：
- nodes[0] 或 nodes[0].options[0] 为 null：报对应路径必须是对象；
- 删除 nodes[0] 的 id/text/options 或 nodes[0].options[0] 的
  text/target：报缺少字段并给出完整路径；
- 节点文字、选项文字为 null、数字或布尔值：报对应路径必须是字符串；
- 节点 options 为 null、字符串或对象：报对应路径必须是数组。

成功路径（退出码 0，标准错误为空，标准输出严格为 ``校验通过\\n``）：
- sample.json 的独立临时字节副本；
- 节点文字或选项文字为空字符串、只含空格和制表符；
- 第一个节点的 options 为空数组（空文字是合法字符串，不是字段缺失）。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：真实退出码与标准输出、标准错误两个流逐一核对；派生样例均为
合法 UTF-8 JSON，每次调用前后核对输入字节不变；临时文件在测试结束后
清理，各用例可单独执行，整组重复执行结果一致。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIALOGUE = PROJECT_DIR / "dialogue.py"
SAMPLE = PROJECT_DIR / "sample.json"

OK_MESSAGE = "校验通过\n"
FAIL_PREFIX = "校验失败："

# 类型错误参数：（取值说明, 实际取值）。覆盖 null、数字、布尔值三种非字符串。
SCALAR_WRONG_TYPES = [
    ("null", None),
    ("数字", 1),
    ("布尔值", True),
]

# options 的三种非数组取值：null、字符串、对象。
OPTIONS_WRONG_TYPES = [
    ("null", None),
    ("字符串", "选项列表"),
    ("对象", {"不是": "数组"}),
]


def run_validate(path):
    """以命令行方式执行 validate，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "validate", str(path)],
        capture_output=True,
    )


class StructureTestCase(unittest.TestCase):
    """公共辅助：临时样例写入与清理、输入字节不变、两个输出流严格断言。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def load_sample_data(self):
        """解析 sample.json 作为派生用例的合法对照数据。"""
        return json.loads(SAMPLE.read_text(encoding="utf-8"))

    def make_sample(self, data, name):
        """把数据写成独立的临时 UTF-8 JSON 样例并自检合法，返回路径。"""
        path = self.tmp_dir / name
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        path.write_text(payload, encoding="utf-8")
        # 固定「所有派生文件都是合法 UTF-8 JSON」：字节可按 UTF-8 解码且能解析回数据。
        raw = path.read_bytes()
        self.assertEqual(
            json.loads(raw.decode("utf-8")),
            data,
            "派生样例 {} 必须是合法 UTF-8 JSON".format(name),
        )
        return path

    def copy_sample_bytes(self, name="sample_copy.json"):
        """把 sample.json 原样复制为独立临时文件（字节级副本），返回路径。"""
        path = self.tmp_dir / name
        path.write_bytes(SAMPLE.read_bytes())
        return path

    def assert_file_unchanged(self, path, before, label):
        """核对一次 validate 调用前后输入文件字节完全一致。"""
        self.assertEqual(
            before,
            path.read_bytes(),
            "样例（{}）执行后输入文件字节发生变化：{}".format(label, path),
        )

    def assert_pass_exact(self, path, label):
        """成功：退出码 0，标准错误为空，标准输出严格为校验通过加一个结尾换行。"""
        before = path.read_bytes()
        result = run_validate(path)
        self.assert_file_unchanged(path, before, label)
        self.assertEqual(
            result.returncode,
            0,
            "样例（{}）应通过，退出码应为 0，stderr={!r}".format(
                label, result.stderr
            ),
        )
        self.assertEqual(
            result.stderr,
            b"",
            "样例（{}）成功时标准错误应为空，实际 {!r}".format(
                label, result.stderr
            ),
        )
        self.assertEqual(
            result.stdout.decode("utf-8"),
            OK_MESSAGE,
            "样例（{}）标准输出应严格为校验通过加一个结尾换行".format(label),
        )

    def assert_fail_exact(self, path, expected_reason, label, field):
        """失败：退出码 2，标准输出为空，标准错误严格为校验失败加原因加一个换行。"""
        before = path.read_bytes()
        result = run_validate(path)
        self.assert_file_unchanged(path, before, label)
        expected_stderr = FAIL_PREFIX + expected_reason + "\n"
        self.assertEqual(
            result.returncode,
            2,
            "样例（{}，字段 {}）失败时退出码应为 2".format(label, field),
        )
        self.assertEqual(
            result.stdout,
            b"",
            "样例（{}，字段 {}）失败时标准输出应为空，实际 {!r}".format(
                label, field, result.stdout
            ),
        )
        stderr = result.stderr.decode("utf-8")
        self.assertEqual(
            stderr,
            expected_stderr,
            "样例（{}，字段 {}）标准错误与预期不符".format(label, field),
        )
        self.assertNotIn(
            "Traceback",
            stderr,
            "样例（{}，字段 {}）标准错误不应包含调用栈".format(label, field),
        )


class TestStructureSuccess(StructureTestCase):
    """成功路径：合法对照与允许空文字、空选项的既有结构要求。"""

    def test_sample_copy_passes(self):
        """sample.json 的独立临时字节副本：输出、错误流、退出码与原文件逐一核对。"""
        path = self.copy_sample_bytes()
        self.assertEqual(
            path.read_bytes(),
            SAMPLE.read_bytes(),
            "合法对照必须是 sample.json 的字节级副本",
        )
        self.assert_pass_exact(path, "sample.json 临时副本")

    def test_node_text_empty_string_passes(self):
        """节点文字改为空字符串：空字符串仍是字符串，不能当作缺少 text 字段。"""
        data = self.load_sample_data()
        data["nodes"][0]["text"] = ""
        path = self.make_sample(data, "node_text_empty.json")
        self.assert_pass_exact(path, "nodes[0].text 为空字符串")

    def test_node_text_whitespace_passes(self):
        """节点文字只含空格和制表符：合法字符串，应通过。"""
        data = self.load_sample_data()
        data["nodes"][0]["text"] = " \t  \t "
        path = self.make_sample(data, "node_text_whitespace.json")
        self.assert_pass_exact(path, "nodes[0].text 只含空格和制表符")

    def test_option_text_empty_string_passes(self):
        """选项文字改为空字符串：空字符串仍是字符串，不能当作缺少 text 字段。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0]["text"] = ""
        path = self.make_sample(data, "option_text_empty.json")
        self.assert_pass_exact(path, "nodes[0].options[0].text 为空字符串")

    def test_option_text_whitespace_passes(self):
        """选项文字只含空格和制表符：合法字符串，应通过。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0]["text"] = " \t  \t "
        path = self.make_sample(data, "option_text_whitespace.json")
        self.assert_pass_exact(
            path, "nodes[0].options[0].text 只含空格和制表符"
        )

    def test_first_node_empty_options_passes(self):
        """第一个节点的 options 改为空数组：结尾节点没有选项合法，应通过。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"] = []
        path = self.make_sample(data, "node_options_empty.json")
        self.assert_pass_exact(path, "nodes[0].options 为空数组")


class TestStructureFailure(StructureTestCase):
    """失败路径：每份样例相对合法对照只改一处，错误定位到完整字段路径。"""

    def test_first_node_null(self):
        """第一个节点改为 null：报 nodes[0] 必须是对象。"""
        data = self.load_sample_data()
        data["nodes"][0] = None
        path = self.make_sample(data, "node_null.json")
        self.assert_fail_exact(
            path, "nodes[0] 必须是对象", "第一个节点为 null", "nodes[0]"
        )

    def test_first_option_null(self):
        """第一个选项改为 null：报 nodes[0].options[0] 必须是对象。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0] = None
        path = self.make_sample(data, "option_null.json")
        self.assert_fail_exact(
            path,
            "nodes[0].options[0] 必须是对象",
            "第一个选项为 null",
            "nodes[0].options[0]",
        )

    def test_first_node_missing_id(self):
        """删除第一个节点的 id：报缺少字段 nodes[0].id。"""
        data = self.load_sample_data()
        del data["nodes"][0]["id"]
        path = self.make_sample(data, "node_missing_id.json")
        self.assert_fail_exact(
            path, "缺少字段 nodes[0].id", "删除 nodes[0].id", "nodes[0].id"
        )

    def test_first_node_missing_text(self):
        """删除第一个节点的 text：报缺少字段 nodes[0].text。"""
        data = self.load_sample_data()
        del data["nodes"][0]["text"]
        path = self.make_sample(data, "node_missing_text.json")
        self.assert_fail_exact(
            path, "缺少字段 nodes[0].text", "删除 nodes[0].text", "nodes[0].text"
        )

    def test_first_node_missing_options(self):
        """删除第一个节点的 options：报缺少字段 nodes[0].options。"""
        data = self.load_sample_data()
        del data["nodes"][0]["options"]
        path = self.make_sample(data, "node_missing_options.json")
        self.assert_fail_exact(
            path,
            "缺少字段 nodes[0].options",
            "删除 nodes[0].options",
            "nodes[0].options",
        )

    def test_first_option_missing_text(self):
        """删除第一个选项的 text：报缺少字段 nodes[0].options[0].text。"""
        data = self.load_sample_data()
        del data["nodes"][0]["options"][0]["text"]
        path = self.make_sample(data, "option_missing_text.json")
        self.assert_fail_exact(
            path,
            "缺少字段 nodes[0].options[0].text",
            "删除 nodes[0].options[0].text",
            "nodes[0].options[0].text",
        )

    def test_first_option_missing_target(self):
        """删除第一个选项的 target：报缺少字段 nodes[0].options[0].target。"""
        data = self.load_sample_data()
        del data["nodes"][0]["options"][0]["target"]
        path = self.make_sample(data, "option_missing_target.json")
        self.assert_fail_exact(
            path,
            "缺少字段 nodes[0].options[0].target",
            "删除 nodes[0].options[0].target",
            "nodes[0].options[0].target",
        )

    def test_node_text_wrong_type(self):
        """节点文字分别改为 null、数字或布尔值：报 nodes[0].text 必须是字符串。"""
        field = "nodes[0].text"
        for index, (value_label, value) in enumerate(SCALAR_WRONG_TYPES):
            with self.subTest(取值=value_label, 字段=field):
                data = self.load_sample_data()
                data["nodes"][0]["text"] = value
                path = self.make_sample(
                    data, "node_text_wrong_type_{}.json".format(index)
                )
                self.assert_fail_exact(
                    path,
                    "nodes[0].text 必须是字符串",
                    "节点文字为{}".format(value_label),
                    field,
                )

    def test_option_text_wrong_type(self):
        """选项文字分别改为 null、数字或布尔值：报完整路径必须是字符串。"""
        field = "nodes[0].options[0].text"
        for index, (value_label, value) in enumerate(SCALAR_WRONG_TYPES):
            with self.subTest(取值=value_label, 字段=field):
                data = self.load_sample_data()
                data["nodes"][0]["options"][0]["text"] = value
                path = self.make_sample(
                    data, "option_text_wrong_type_{}.json".format(index)
                )
                self.assert_fail_exact(
                    path,
                    "nodes[0].options[0].text 必须是字符串",
                    "选项文字为{}".format(value_label),
                    field,
                )

    def test_node_options_wrong_type(self):
        """节点 options 分别改为 null、字符串或对象：报 nodes[0].options 必须是数组。"""
        field = "nodes[0].options"
        for index, (value_label, value) in enumerate(OPTIONS_WRONG_TYPES):
            with self.subTest(取值=value_label, 字段=field):
                data = self.load_sample_data()
                data["nodes"][0]["options"] = value
                path = self.make_sample(
                    data, "node_options_wrong_type_{}.json".format(index)
                )
                self.assert_fail_exact(
                    path,
                    "nodes[0].options 必须是数组",
                    "节点 options 为{}".format(value_label),
                    field,
                )


if __name__ == "__main__":
    unittest.main()
