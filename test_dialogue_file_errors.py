# -*- coding: utf-8 -*-
"""dialogue.py 文件读取阶段（load_dialogue）命令行回归测试。

在既有结构、引用与选项错误覆盖之外，补齐 validate 与 preview
读取同一异常输入时的公开结果：路径不存在、UTF-8 解码失败、
JSON 语法错误（空文件与三行语法错误样例），以及语法错误先于
--choice 选项编号错误的优先级。另以 sample.json 的临时副本作为
读取成功的对照。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出、标准错误（错误类别、传入路径、
JSON 行列位置、无调用栈、无节点文字、不误报为结构校验失败），
以及输入文件在执行前后字节不变；路径不存在时确认文件未被创建。
所有样例独立写入临时目录并自动清理，sample.json 与业务源码保持
原样，用例可重复运行且结果一致。系统读取错误的附加文字不要求
跨操作系统一致，故只核对错误类别与路径。
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIALOGUE = PROJECT_DIR / "dialogue.py"
SAMPLE = PROJECT_DIR / "sample.json"

VALIDATE_OK_MESSAGE = "校验通过\n"
PREVIEW_CHOICE_1_MESSAGE = "你到了森林。\n"

# 失败时标准错误中不应出现 sample.json 任一节点的文字。
NODE_TEXTS = ("你来到岔路口。", "你到了森林。", "你到了河边。")


def run_validate(path):
    """以命令行方式执行 validate，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "validate", str(path)],
        capture_output=True,
    )


def run_preview(path, choice):
    """以命令行方式执行 preview --choice，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [
            sys.executable, str(DIALOGUE), "preview", str(path),
            "--choice", str(choice),
        ],
        capture_output=True,
    )


class FileErrorsTestCase(unittest.TestCase):
    """公共断言：临时样例写入与清理、文件字节不变、无调用栈与节点文字。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def write_raw(self, raw, name="case.json"):
        """把固定字节直接写成临时样例（不经 JSON 序列化），返回路径。"""
        path = self.tmp_dir / name
        path.write_bytes(raw)
        return path

    def copy_sample(self, name="sample_copy.json"):
        """把仓库 sample.json 按字节复制为独立临时副本，返回副本路径。"""
        path = self.tmp_dir / name
        shutil.copyfile(str(SAMPLE), str(path))
        return path

    def assert_no_traceback(self, stderr):
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")

    def assert_read_failure(self, path, result, expected_parts, *,
                            before_bytes=None, absent_parts=()):
        """核对两个命令读取异常输入时的统一失败形态。

        退出码 2、标准输出为空；标准错误含错误类别、传入路径及要求的
        片段，但无调用栈、无节点文字，也不误报为结构校验失败。
        before_bytes 为 None 表示路径本不存在，额外确认调用后仍未创建；
        否则逐字节比对，确认现有文件保持原样。
        """
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertNotIn(
            "校验失败", stderr, "文件读取阶段的错误不应误报为结构校验失败"
        )
        for text in NODE_TEXTS:
            self.assertNotIn(text, stderr, "失败输出中不应出现节点文字")
        self.assertIn(
            str(path), stderr, "标准错误应包含传入的文件路径 {!r}".format(path)
        )
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        for part in absent_parts:
            self.assertNotIn(part, stderr, "标准错误不应包含 {!r}".format(part))
        if before_bytes is None:
            self.assertFalse(
                path.exists(), "读取不存在的路径后不应创建该文件：{}".format(path)
            )
        else:
            self.assertEqual(
                before_bytes,
                path.read_bytes(),
                "输入文件在执行后发生变化：{}".format(path),
            )
        return result

    def assert_failure_for_existing(self, path, result, expected_parts,
                                    absent_parts=()):
        """记录现有文件字节，统一核对失败形态并确认字节不变。"""
        return self.assert_read_failure(
            path, result, expected_parts,
            before_bytes=path.read_bytes(), absent_parts=absent_parts,
        )

    def assert_failure_for_missing(self, path, result, expected_parts):
        """路径不存在：调用前即不存在，调用后也不得被创建。"""
        self.assertFalse(path.exists(), "前置条件：路径不应存在：{}".format(path))
        return self.assert_read_failure(
            path, result, expected_parts, before_bytes=None
        )


class TestPathNotFound(FileErrorsTestCase):
    """路径不存在：两个命令均以退出码 2 结束，且不创建该文件。"""

    def missing_path(self):
        return self.tmp_dir / "不存在的文件.json"

    def test_validate_nonexistent_path(self):
        path = self.missing_path()
        result = run_validate(path)
        self.assert_failure_for_missing(path, result, ["无法读取文件"])

    def test_preview_nonexistent_path(self):
        path = self.missing_path()
        result = run_preview(path, 1)
        self.assert_failure_for_missing(path, result, ["无法读取文件"])


class TestUtf8DecodeFailure(FileErrorsTestCase):
    """文件仅含一个 0xFF 字节：报告 UTF-8 解码失败而非语法或结构错误。"""

    def setUp(self):
        super().setUp()
        self.path = self.write_raw(b"\xff", name="bad_utf8.json")

    def test_validate_invalid_utf8(self):
        result = run_validate(self.path)
        self.assert_failure_for_existing(
            self.path, result, ["UTF-8 解码失败"]
        )

    def test_preview_invalid_utf8(self):
        result = run_preview(self.path, 1)
        self.assert_failure_for_existing(
            self.path, result, ["UTF-8 解码失败"]
        )


class TestJsonSyntaxFailure(FileErrorsTestCase):
    """JSON 语法错误：两个命令都报告行列位置；字节保持原样。"""

    def test_validate_empty_file_reports_line_1_column_1(self):
        """空文件：第 1 行第 1 列的 JSON 语法错误。"""
        path = self.write_raw(b"", name="empty.json")
        result = run_validate(path)
        self.assert_failure_for_existing(
            path, result, ["JSON 语法错误", "第 1 行第 1 列"]
        )

    def test_preview_empty_file_reports_line_1_column_1(self):
        path = self.write_raw(b"", name="empty.json")
        result = run_preview(path, 1)
        self.assert_failure_for_existing(
            path, result, ["JSON 语法错误", "第 1 行第 1 列"]
        )

    def test_validate_second_line_syntax_error(self):
        """三行样例（{ / ! / }，无尾换行）：第 2 行第 1 列的语法错误。"""
        path = self.write_raw("{\n!\n}".encode("utf-8"), name="syntax.json")
        result = run_validate(path)
        self.assert_failure_for_existing(
            path, result, ["JSON 语法错误", "第 2 行第 1 列"]
        )

    def test_preview_second_line_syntax_error(self):
        path = self.write_raw("{\n!\n}".encode("utf-8"), name="syntax.json")
        result = run_preview(path, 1)
        self.assert_failure_for_existing(
            path, result, ["JSON 语法错误", "第 2 行第 1 列"]
        )

    def test_preview_syntax_error_precedes_bad_choice_on_three_line_file(self):
        """三行语法错误样例以 --choice abc 调用：应优先报告第 2 行第 1 列
        的同一文件语法错误，而不是选项编号无法解析。"""
        path = self.write_raw("{\n!\n}".encode("utf-8"), name="syntax.json")
        result = run_preview(path, "abc")
        self.assert_failure_for_existing(
            path,
            result,
            ["JSON 语法错误", "第 2 行第 1 列"],
            absent_parts=["无法解析为整数"],
        )

    def test_preview_syntax_error_precedes_bad_choice_on_empty_file(self):
        """空文件以 --choice abc 调用：仍先报告第 1 行第 1 列语法错误。"""
        path = self.write_raw(b"", name="empty.json")
        result = run_preview(path, "abc")
        self.assert_failure_for_existing(
            path,
            result,
            ["JSON 语法错误", "第 1 行第 1 列"],
            absent_parts=["无法解析为整数"],
        )


class TestReadSuccessOnSampleCopy(FileErrorsTestCase):
    """读取成功对照：sample.json 的临时副本，两个命令各自的成功公开结果。"""

    def test_validate_sample_copy_passes(self):
        """validate：退出码 0，标准输出仅为「校验通过」加一个换行。"""
        path = self.copy_sample()
        before = path.read_bytes()
        result = run_validate(path)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"),
            VALIDATE_OK_MESSAGE,
            "标准输出应只有校验通过和一个结尾换行",
        )
        self.assertEqual(before, SAMPLE.read_bytes())
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )

    def test_preview_choice_1_on_sample_copy_outputs_forest(self):
        """preview --choice 1：退出码 0，标准输出仅为森林文字加一个换行。"""
        path = self.copy_sample()
        before = path.read_bytes()
        result = run_preview(path, 1)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"),
            PREVIEW_CHOICE_1_MESSAGE,
            "标准输出应只有目标节点文字和一个结尾换行",
        )
        self.assertEqual(before, SAMPLE.read_bytes())
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )


if __name__ == "__main__":
    unittest.main()
