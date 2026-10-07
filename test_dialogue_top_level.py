# -*- coding: utf-8 -*-
"""dialogue.py validate 对顶层 JSON 结构要求的命令行回归测试。

在 test_dialogue_validate.py 与 test_dialogue_structure.py 已覆盖的节点、
选项与编号规则之外，本文件固定「能解析为 JSON、却不能作为对话使用」的
顶层输入边界（每个失败样例都是合法 UTF-8 JSON，可被正常读取和解析）：

失败路径（退出码 2，标准输出为空，标准错误严格为
``校验失败：<原因>\\n`` 且不含调用栈或文件/JSON 语法错误说明）：
- 顶层分别为 []、null、"文字"、1、true：报顶层 JSON 必须是对象；
- 从合法样例单独删除 start 或 nodes：分别报缺少字段 start/nodes；
- 空对象 {}：只报缺少字段 start；
- start 保持有效，nodes 分别为 null、字符串、对象、数字、布尔值：
  报 nodes 必须是数组；nodes 为 []：报 nodes 必须是非空数组。

成功路径（退出码 0，标准错误为空，标准输出严格为 ``校验通过\\n``）：
- sample.json 的独立临时字节副本；
- 仅在副本顶层增加 note 字段且值为“草稿”（额外字段不影响校验）。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：真实退出码与标准输出、标准错误两个流逐字节核对；派生样例均为
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

# 能解析为合法 JSON、却不能作为对话顶层使用的五种非对象取值。
TOP_LEVEL_NON_OBJECTS = [
    ("空数组", []),
    ("null", None),
    ("字符串", "文字"),
    ("数字", 1),
    ("布尔值", True),
]

# start 保持合法时 nodes 的六种取值及其对应原因。
NODES_BAD_VALUES = [
    ("null", None, "nodes 必须是数组"),
    ("字符串", "节点列表", "nodes 必须是数组"),
    ("对象", {}, "nodes 必须是数组"),
    ("数字", 1, "nodes 必须是数组"),
    ("布尔值", True, "nodes 必须是数组"),
    ("空数组", [], "nodes 必须是非空数组"),
]

# 这些标记只应出现在文件读取/JSON 解析失败时；结构校验失败不得误报。
FILE_OR_JSON_ERROR_MARKERS = ("无法读取文件", "UTF-8 解码失败", "JSON 语法错误")


def run_validate(path):
    """以命令行方式执行 validate，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "validate", str(path)],
        capture_output=True,
    )


class TopLevelTestCase(unittest.TestCase):
    """公共辅助：临时样例写入与清理、输入字节不变、两个输出流严格断言。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def load_sample_data(self):
        """深拷贝样例数据，派生用例之间互不影响。"""
        return json.loads(SAMPLE.read_text(encoding="utf-8"))

    def write_json(self, value, name):
        """把任意 JSON 数据写成独立的临时 UTF-8 JSON 样例并自检合法，返回路径。"""
        path = self.tmp_dir / name
        payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        path.write_text(payload, encoding="utf-8")
        # 固定「所有派生文件都是可正常读取和解析的合法 UTF-8 JSON」：
        # 字节可按 UTF-8 解码且能原样解析回数据，不与 JSON 语法错误混淆。
        raw = path.read_bytes()
        self.assertEqual(
            json.loads(raw.decode("utf-8")),
            value,
            "派生样例 {} 必须是合法 UTF-8 JSON".format(name),
        )
        return path

    def make_sample(self, data, name):
        """把对话数据写成独立的临时 UTF-8 JSON 样例，返回路径。"""
        return self.write_json(data, name)

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
            "样例（{}）标准输出应严格为校验通过加一个结尾换行，实际 {!r}".format(
                label, result.stdout
            ),
        )

    def assert_fail_exact(self, path, expected_reason, label):
        """失败：退出码 2，标准输出为空，标准错误严格为校验失败加原因加一个换行。"""
        before = path.read_bytes()
        result = run_validate(path)
        self.assert_file_unchanged(path, before, label)
        expected_stderr = FAIL_PREFIX + expected_reason + "\n"
        stderr = result.stderr.decode("utf-8")
        self.assertEqual(
            result.returncode,
            2,
            "样例（{}）失败时退出码应为 2，实际 {}，stdout={!r}，stderr={!r}".format(
                label, result.returncode, result.stdout, result.stderr
            ),
        )
        self.assertEqual(
            result.stdout,
            b"",
            "样例（{}）失败时标准输出应为空，实际 {!r}".format(
                label, result.stdout
            ),
        )
        self.assertEqual(
            stderr,
            expected_stderr,
            "样例（{}）标准错误与预期不符：预期 {!r}，实际 {!r}".format(
                label, expected_stderr, stderr
            ),
        )
        self.assertNotIn(
            "Traceback",
            stderr,
            "样例（{}）标准错误不应包含调用栈".format(label),
        )
        for marker in FILE_OR_JSON_ERROR_MARKERS:
            self.assertNotIn(
                marker,
                stderr,
                "样例（{}）文件本身合法，不应被误判为文件或 JSON 语法错误（{}）".format(
                    label, marker
                ),
            )


class TestTopLevelFailure(TopLevelTestCase):
    """失败路径：每份样例都是合法 JSON，只是顶层结构不能作为对话使用。"""

    def test_top_level_not_object(self):
        """顶层分别为 []、null、字符串、数字、布尔值：报顶层 JSON 必须是对象。"""
        reason = "顶层 JSON 必须是对象"
        for index, (value_label, value) in enumerate(TOP_LEVEL_NON_OBJECTS):
            with self.subTest(顶层取值=value_label):
                path = self.write_json(
                    value, "top_level_non_object_{}.json".format(index)
                )
                self.assert_fail_exact(
                    path, reason, "顶层为{}".format(value_label)
                )

    def test_missing_start(self):
        """从合法样例单独删除 start：报缺少字段 start（不报 nodes 相关问题）。"""
        data = self.load_sample_data()
        del data["start"]
        path = self.make_sample(data, "missing_start.json")
        self.assert_fail_exact(path, "缺少字段 start", "删除 start")

    def test_missing_nodes(self):
        """从合法样例单独删除 nodes：报缺少字段 nodes。"""
        data = self.load_sample_data()
        del data["nodes"]
        path = self.make_sample(data, "missing_nodes.json")
        self.assert_fail_exact(path, "缺少字段 nodes", "删除 nodes")

    def test_empty_object(self):
        """空对象 {}：start 先于 nodes 检查，只报缺少字段 start。"""
        path = self.write_json({}, "empty_object.json")
        self.assert_fail_exact(path, "缺少字段 start", "空对象 {}")

    def test_nodes_wrong_type_or_empty(self):
        """start 保持有效，nodes 为非数组值报必须是数组，为 [] 报必须是非空数组。"""
        for index, (value_label, value, reason) in enumerate(NODES_BAD_VALUES):
            with self.subTest(nodes取值=value_label):
                data = self.load_sample_data()
                data["nodes"] = value
                path = self.make_sample(
                    data, "nodes_bad_value_{}.json".format(index)
                )
                self.assert_fail_exact(
                    path, reason, "nodes 为{}".format(value_label)
                )


class TestTopLevelSuccess(TopLevelTestCase):
    """成功路径：合法对照与顶层额外字段不影响校验的既有行为。"""

    def test_sample_copy_passes(self):
        """sample.json 的独立临时字节副本：输出、错误流、退出码与原文件逐一核对。"""
        path = self.copy_sample_bytes()
        self.assertEqual(
            path.read_bytes(),
            SAMPLE.read_bytes(),
            "合法对照必须是 sample.json 的字节级副本",
        )
        self.assert_pass_exact(path, "sample.json 临时副本")

    def test_extra_top_level_note_passes(self):
        """仅在副本顶层增加 note="草稿"：额外字段不参与校验，应通过。"""
        data = self.load_sample_data()
        data["note"] = "草稿"
        path = self.make_sample(data, "extra_top_level_note.json")
        self.assert_pass_exact(path, "顶层增加 note 字段")


if __name__ == "__main__":
    unittest.main()
