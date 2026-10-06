# -*- coding: utf-8 -*-
"""dialogue.py 文件读取阶段（load_dialogue）命令行回归测试。

覆盖 validate 与 preview --choice 1 读取相同异常输入时的公开结果：
路径不存在、UTF-8 解码失败、空文件与多行 JSON 语法错误，以及
sample.json 临时副本的读取成功对照。语法错误样例另以 --choice abc
调用 preview，确认文件语法错误优先于选项编号错误报告。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出、标准错误（错误类别、传入路径、语法位置），
以及实际存在的输入文件在执行前后字节不变。系统读取错误的附加文字
（如 No such file or directory）不要求跨操作系统一致，不作断言。
所有临时样例独立写入临时目录并自动清理，仓库 sample.json 与业务源码
保持原样，用例可重复运行且结果一致。
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIALOGUE = PROJECT_DIR / "dialogue.py"
SAMPLE = PROJECT_DIR / "sample.json"

OK_MESSAGE = "校验通过\n"
FOREST_MESSAGE = "你到了森林。\n"


def run_validate(path):
    """以命令行方式执行 validate，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "validate", str(path)],
        capture_output=True,
    )


def run_preview(path, choice):
    """以命令行方式执行 preview，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "preview", str(path), "--choice", str(choice)],
        capture_output=True,
    )


class LoadTestCase(unittest.TestCase):
    """公共断言：临时样例写入与清理、文件字节不变、读取失败输出格式。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def make_sample_bytes(self, content, name="case.json"):
        """把原始字节写成独立的临时样例文件，返回路径。"""
        path = self.tmp_dir / name
        path.write_bytes(content)
        return path

    def assert_file_unchanged(self, path, before):
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )

    def assert_no_traceback(self, stderr):
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")

    def assert_read_failure(self, result, path, expected_parts):
        """读取阶段失败的公共断言：退出码 2、标准输出为空、标准错误含
        错误类别与传入路径、无调用栈、不误报为结构校验失败、不含节点文字。"""
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertNotIn("校验失败", stderr, "读取阶段失败不应误报为结构校验失败")
        self.assertNotIn("你到了森林", stderr, "标准错误中不应出现节点文字")
        self.assertIn(str(path), stderr, "标准错误应包含传入路径")
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return stderr

    def run_existing_and_assert_failure(self, run, path, expected_parts):
        """对已存在的输入执行命令：先记录字节，执行后核对不变，再断言失败输出。"""
        before = path.read_bytes()
        result = run(path)
        self.assert_file_unchanged(path, before)
        return self.assert_read_failure(result, path, expected_parts)


class TestMissingPath(LoadTestCase):
    """路径不存在：两个命令均报无法读取文件，且不会创建该文件。"""

    def setUp(self):
        super().setUp()
        self.missing = self.tmp_dir / "missing.json"

    def assert_missing_failure(self, result):
        self.assert_read_failure(result, self.missing, ["无法读取文件"])
        self.assertFalse(
            self.missing.exists(), "失败后不应创建传入路径 {}".format(self.missing)
        )

    def test_validate_missing_path(self):
        self.assert_missing_failure(run_validate(self.missing))

    def test_preview_missing_path(self):
        self.assert_missing_failure(run_preview(self.missing, 1))


class TestInvalidUtf8(LoadTestCase):
    """文件仅含一个 0xFF 字节：两个命令均报 UTF-8 解码失败。"""

    def setUp(self):
        super().setUp()
        self.path = self.make_sample_bytes(b"\xff", "bad_utf8.json")

    def test_validate_invalid_utf8(self):
        self.run_existing_and_assert_failure(
            run_validate, self.path, ["UTF-8 解码失败"]
        )

    def test_preview_invalid_utf8(self):
        self.run_existing_and_assert_failure(
            lambda p: run_preview(p, 1), self.path, ["UTF-8 解码失败"]
        )


class TestEmptyFile(LoadTestCase):
    """空文件：两个命令均报第 1 行第 1 列的 JSON 语法错误。"""

    def setUp(self):
        super().setUp()
        self.path = self.make_sample_bytes(b"", "empty.json")

    def test_validate_empty_file(self):
        self.run_existing_and_assert_failure(
            run_validate, self.path, ["JSON 语法错误", "第 1 行第 1 列"]
        )

    def test_preview_empty_file(self):
        self.run_existing_and_assert_failure(
            lambda p: run_preview(p, 1),
            self.path,
            ["JSON 语法错误", "第 1 行第 1 列"],
        )


class TestBrokenJson(LoadTestCase):
    """三行文本 {、!、}：两个命令均报第 2 行第 1 列的 JSON 语法错误。"""

    def setUp(self):
        super().setUp()
        self.path = self.make_sample_bytes(
            "{\n!\n}\n".encode("utf-8"), "broken.json"
        )

    def test_validate_broken_json(self):
        self.run_existing_and_assert_failure(
            run_validate, self.path, ["JSON 语法错误", "第 2 行第 1 列"]
        )

    def test_preview_broken_json(self):
        self.run_existing_and_assert_failure(
            lambda p: run_preview(p, 1),
            self.path,
            ["JSON 语法错误", "第 2 行第 1 列"],
        )

    def test_preview_bad_choice_still_reports_syntax_error(self):
        """--choice abc 作用于语法错误样例：文件语法错误优先于选项编号错误。"""
        stderr = self.run_existing_and_assert_failure(
            lambda p: run_preview(p, "abc"),
            self.path,
            ["JSON 语法错误", "第 2 行第 1 列"],
        )
        self.assertNotIn(
            "无法解析为整数", stderr, "文件语法错误应优先于选项编号错误报告"
        )


class TestLoadSuccess(LoadTestCase):
    """读取成功对照：sample.json 的临时副本，两个命令均退出码 0、标准错误为空。"""

    def setUp(self):
        super().setUp()
        self.path = self.make_sample_bytes(SAMPLE.read_bytes(), "sample_copy.json")

    def test_validate_sample_copy_ok(self):
        before = self.path.read_bytes()
        result = run_validate(self.path)
        self.assert_file_unchanged(self.path, before)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"),
            OK_MESSAGE,
            "标准输出应只有校验通过和一个结尾换行",
        )

    def test_preview_sample_copy_choice_1_ok(self):
        before = self.path.read_bytes()
        result = run_preview(self.path, 1)
        self.assert_file_unchanged(self.path, before)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"),
            FOREST_MESSAGE,
            "标准输出应只有目标节点文字和一个结尾换行",
        )


if __name__ == "__main__":
    unittest.main()
