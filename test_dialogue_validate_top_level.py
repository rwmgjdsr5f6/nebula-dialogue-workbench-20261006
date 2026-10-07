# -*- coding: utf-8 -*-
"""dialogue.py validate 命令的顶层结构命令行回归测试。

固定「能解析为合法 UTF-8 JSON、却不能作为对话使用」的输入边界：
顶层非对象（数组、null、字符串、数字、布尔）、缺少 start 或 nodes
字段、nodes 不是数组或为空数组；以及成功对照（sample.json 独立副本、
顶层附加 note 字段的副本）。所有失败样例都能正常读取和解析，不应被
误判为文件或 JSON 语法错误。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：真实退出码、标准输出与标准错误逐字内容，以及输入文件在
执行前后字节不变。所有派生样例独立写入临时目录并自动清理，
sample.json 保持原样，用例可重复运行且结果一致。
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


def run_validate(path):
    """以命令行方式执行 validate，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "validate", str(path)],
        capture_output=True,
    )


class TopLevelValidateTestCase(unittest.TestCase):
    """公共断言：临时样例写入与清理、文件字节不变、流逐字核对。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def load_sample_data(self):
        """深拷贝样例数据，派生用例之间互不影响。"""
        return json.loads(SAMPLE.read_text(encoding="utf-8"))

    def make_sample(self, data, name):
        """把数据写成独立的临时 UTF-8 JSON 样例文件，返回路径。"""
        path = self.tmp_dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def assert_file_unchanged(self, path, before, case_label):
        self.assertEqual(
            before,
            path.read_bytes(),
            "样例 {} 的输入文件在执行后发生变化：{}".format(case_label, path),
        )

    def run_and_assert_fail(self, path, reason, case_label):
        """失败：退出码 2，标准输出为空，标准错误逐字等于校验失败加原因。"""
        before = path.read_bytes()
        result = run_validate(path)
        self.assert_file_unchanged(path, before, case_label)
        stderr = result.stderr.decode("utf-8")
        self.assertEqual(
            result.returncode,
            2,
            "样例 {} 的退出码应为 2，实际为 {}（stderr: {!r}）".format(
                case_label, result.returncode, stderr
            ),
        )
        self.assertEqual(
            result.stdout,
            b"",
            "样例 {} 失败时标准输出应为空，实际为 {!r}".format(
                case_label, result.stdout
            ),
        )
        self.assertEqual(
            stderr,
            FAIL_PREFIX + reason + "\n",
            "样例 {} 的标准错误应逐字等于 {!r}，实际为 {!r}".format(
                case_label, FAIL_PREFIX + reason + "\n", stderr
            ),
        )
        self.assertNotIn("Traceback", stderr, "样例 {} 不应出现调用栈".format(case_label))

    def run_and_assert_ok(self, path, case_label):
        """成功：退出码 0，标准输出仅为校验通过加一个结尾换行，标准错误为空。"""
        before = path.read_bytes()
        result = run_validate(path)
        self.assert_file_unchanged(path, before, case_label)
        stderr = result.stderr.decode("utf-8")
        self.assertEqual(
            result.returncode,
            0,
            "样例 {} 的退出码应为 0，实际为 {}（stderr: {!r}）".format(
                case_label, result.returncode, stderr
            ),
        )
        self.assertEqual(
            result.stderr,
            b"",
            "样例 {} 成功时标准错误应为空，实际为 {!r}".format(case_label, stderr),
        )
        self.assertEqual(
            result.stdout.decode("utf-8"),
            OK_MESSAGE,
            "样例 {} 的标准输出应只有校验通过和一个结尾换行，实际为 {!r}".format(
                case_label, result.stdout
            ),
        )


class TestTopLevelNotObject(TopLevelValidateTestCase):
    """顶层是合法 JSON 但不是对象：统一报「顶层 JSON 必须是对象」。"""

    REASON = "顶层 JSON 必须是对象"

    def check(self, data, case_label):
        path = self.make_sample(data, case_label + ".json")
        self.run_and_assert_fail(path, self.REASON, case_label)

    def test_top_level_array(self):
        """顶层为 []：是合法 JSON 数组，不是对话对象。"""
        self.check([], "top_level_array")

    def test_top_level_null(self):
        """顶层为 null。"""
        self.check(None, "top_level_null")

    def test_top_level_string(self):
        """顶层为字符串 "文字"。"""
        self.check("文字", "top_level_string")

    def test_top_level_number(self):
        """顶层为数字 1。"""
        self.check(1, "top_level_number")

    def test_top_level_boolean(self):
        """顶层为 true。"""
        self.check(True, "top_level_boolean")


class TestMissingTopLevelField(TopLevelValidateTestCase):
    """顶层是对象但缺少必需字段：按字段检查顺序报告第一个缺失。"""

    def test_missing_start(self):
        """从合法样例单独删除 start：报「缺少字段 start」。"""
        data = self.load_sample_data()
        del data["start"]
        path = self.make_sample(data, "missing_start.json")
        self.run_and_assert_fail(path, "缺少字段 start", "missing_start")

    def test_missing_nodes(self):
        """从合法样例单独删除 nodes：报「缺少字段 nodes」。"""
        data = self.load_sample_data()
        del data["nodes"]
        path = self.make_sample(data, "missing_nodes.json")
        self.run_and_assert_fail(path, "缺少字段 nodes", "missing_nodes")

    def test_empty_object(self):
        """空对象 {} 同时缺两个字段：只报告先检查的「缺少字段 start」。"""
        path = self.make_sample({}, "empty_object.json")
        self.run_and_assert_fail(path, "缺少字段 start", "empty_object")


class TestNodesNotArray(TopLevelValidateTestCase):
    """start 保持有效，nodes 不是数组或为空数组。"""

    def check(self, nodes_value, reason, case_label):
        data = self.load_sample_data()
        data["nodes"] = nodes_value
        path = self.make_sample(data, case_label + ".json")
        self.run_and_assert_fail(path, reason, case_label)

    def test_nodes_null(self):
        """nodes 为 null：报「nodes 必须是数组」。"""
        self.check(None, "nodes 必须是数组", "nodes_null")

    def test_nodes_string(self):
        """nodes 为字符串 "节点列表"：报「nodes 必须是数组」。"""
        self.check("节点列表", "nodes 必须是数组", "nodes_string")

    def test_nodes_object(self):
        """nodes 为对象 {}：报「nodes 必须是数组」。"""
        self.check({}, "nodes 必须是数组", "nodes_object")

    def test_nodes_number(self):
        """nodes 为数字 1：报「nodes 必须是数组」。"""
        self.check(1, "nodes 必须是数组", "nodes_number")

    def test_nodes_boolean(self):
        """nodes 为 true：报「nodes 必须是数组」。"""
        self.check(True, "nodes 必须是数组", "nodes_boolean")

    def test_nodes_empty_array(self):
        """nodes 为 []：是数组但为空，报「nodes 必须是非空数组」。"""
        self.check([], "nodes 必须是非空数组", "nodes_empty_array")


class TestTopLevelSuccess(TopLevelValidateTestCase):
    """成功对照：独立副本与附加额外字段的副本都应通过。"""

    def test_sample_copy_passes(self):
        """sample.json 的独立副本：逐字核对输出、错误流与退出码。"""
        data = self.load_sample_data()
        path = self.make_sample(data, "sample_copy.json")
        self.run_and_assert_ok(path, "sample_copy")

    def test_extra_top_level_field_passes(self):
        """副本顶层增加 note 字段（值为 "草稿"）：额外字段不影响校验。"""
        data = self.load_sample_data()
        data["note"] = "草稿"
        path = self.make_sample(data, "extra_note.json")
        self.run_and_assert_ok(path, "extra_note")


if __name__ == "__main__":
    unittest.main()
