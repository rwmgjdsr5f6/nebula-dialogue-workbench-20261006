# -*- coding: utf-8 -*-
"""dialogue.py preview 命令参数格式的回归测试。

固定既有的参数拒绝规则（不新增命令、不改变错误文案）：

- 缺少文件路径、只有文件路径、只有 --node 而缺少 --choice；
- 末尾的 --choice 或 --node 没有值；
- 文件路径之后出现未知开关、额外位置参数或 --choice=1 等号写法；
- --choice 或 --node 重复出现（即使重复值相同）。

以上每种情况分别调用命令，预期退出码 2、标准输出为空、
标准错误仅为 dialogue.py 现有的完整用法文字及末尾换行，
不含调用栈或节点文字。另以重复参数搭配不存在的文件路径，
验证参数格式检查先于文件读取（仍报用法错误且不创建该路径）。

成功对照：省略 --node 与显式 --node start 按 --choice 1 均输出
森林文字；显式指定节点时交换两对参数顺序结果一致。
格式正确但选择值为 abc 时报无法解析为整数（含起点编号 start），
而非用法提示。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

合法对话使用 sample.json 的临时副本，每次调用前后核对输入文件
字节不变，临时副本在结束后自动清理，sample.json 保持原样，
用例可重复运行且结果一致、不依赖执行顺序。
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIALOGUE = PROJECT_DIR / "dialogue.py"
SAMPLE = PROJECT_DIR / "sample.json"

# 用法文字以 dialogue.py 中的现状为准，避免在测试中重复硬编码。
sys.path.insert(0, str(PROJECT_DIR))
from dialogue import USAGE  # noqa: E402

EXPECTED_USAGE_STDERR = (USAGE + "\n").encode("utf-8")


class PreviewArgsTestCase(unittest.TestCase):
    """公共环境：sample.json 临时副本、逐次调用、字节不变核对。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)
        self.sample_copy = self.tmp_dir / "case.json"
        self.sample_copy.write_bytes(SAMPLE.read_bytes())

    def run_preview(self, args):
        """以命令行方式执行 preview，args 为 preview 之后的完整参数列表。"""
        return subprocess.run(
            [sys.executable, str(DIALOGUE), "preview"]
            + [str(arg) for arg in args],
            capture_output=True,
        )

    def assert_copy_unchanged(self, before):
        self.assertEqual(
            before,
            self.sample_copy.read_bytes(),
            "输入文件在执行后发生变化：{}".format(self.sample_copy),
        )

    def run_and_assert_usage_error(self, args):
        """用法错误：退出码 2、标准输出为空、标准错误仅为完整用法文字。"""
        before = self.sample_copy.read_bytes()
        result = self.run_preview(args)
        self.assert_copy_unchanged(before)
        label = "参数 {!r}".format([str(arg) for arg in args])
        self.assertEqual(result.returncode, 2, label)
        self.assertEqual(result.stdout, b"", label + "：标准输出应为空")
        self.assertEqual(
            result.stderr,
            EXPECTED_USAGE_STDERR,
            label + "：标准错误应仅为现有完整用法文字及末尾换行",
        )
        self.assertNotIn(b"Traceback", result.stderr, label)
        return result

    def run_and_assert_ok(self, args, expected_stdout):
        """成功：退出码 0、标准错误为空、输出仅目标节点文字加换行。"""
        before = self.sample_copy.read_bytes()
        result = self.run_preview(args)
        self.assert_copy_unchanged(before)
        label = "参数 {!r}".format([str(arg) for arg in args])
        self.assertEqual(
            result.returncode, 0, label + "，stderr: {!r}".format(result.stderr)
        )
        self.assertEqual(result.stderr, b"", label + "：标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"),
            expected_stdout,
            label + "：标准输出应只有目标节点文字和一个结尾换行",
        )
        return result


class TestPreviewArgsUsageError(PreviewArgsTestCase):
    """参数格式错误：均为退出码 2 与同一完整用法文字。"""

    def test_missing_file_path(self):
        self.run_and_assert_usage_error([])

    def test_only_file_path(self):
        self.run_and_assert_usage_error([self.sample_copy])

    def test_node_without_choice(self):
        self.run_and_assert_usage_error(
            [self.sample_copy, "--node", "start"]
        )

    def test_trailing_choice_without_value(self):
        self.run_and_assert_usage_error(
            [self.sample_copy, "--node", "start", "--choice"]
        )

    def test_trailing_node_without_value(self):
        self.run_and_assert_usage_error(
            [self.sample_copy, "--choice", "1", "--node"]
        )

    def test_unknown_switch_after_path(self):
        self.run_and_assert_usage_error(
            [self.sample_copy, "--choice", "1", "--verbose", "x"]
        )

    def test_extra_positional_argument(self):
        self.run_and_assert_usage_error(
            [self.sample_copy, "--choice", "1", "extra"]
        )

    def test_equals_style_choice_is_rejected(self):
        self.run_and_assert_usage_error(
            [self.sample_copy, "--node", "start", "--choice=1"]
        )

    def test_duplicate_choice_same_value(self):
        self.run_and_assert_usage_error(
            [self.sample_copy, "--choice", "1", "--choice", "1"]
        )

    def test_duplicate_choice_different_values(self):
        self.run_and_assert_usage_error(
            [self.sample_copy, "--choice", "1", "--choice", "2"]
        )

    def test_duplicate_node_same_value(self):
        self.run_and_assert_usage_error(
            [self.sample_copy, "--node", "start", "--node", "start",
             "--choice", "1"]
        )

    def test_duplicate_args_with_missing_path_still_usage_error(self):
        """重复参数搭配不存在的路径：仍是同一用法错误。

        验证参数格式检查先于文件读取：不得报无法读取文件，
        也不得创建该路径。
        """
        missing = self.tmp_dir / "no_such_file.json"
        self.assertFalse(missing.exists(), "前置条件：路径不应存在")
        args = [missing, "--choice", "1", "--choice", "1"]
        result = self.run_and_assert_usage_error(args)
        self.assertNotIn(
            "无法读取文件".encode("utf-8"),
            result.stderr,
            "参数格式错误不应变成无法读取文件",
        )
        self.assertFalse(missing.exists(), "执行后不应创建该路径")


class TestPreviewArgsSuccess(PreviewArgsTestCase):
    """成功对照：退出码 0、标准错误为空、输出森林文字加换行。"""

    def test_omit_node_choice_1_outputs_forest_text(self):
        self.run_and_assert_ok(
            [self.sample_copy, "--choice", "1"], "你到了森林。\n"
        )

    def test_explicit_start_choice_1_outputs_forest_text(self):
        self.run_and_assert_ok(
            [self.sample_copy, "--choice", "1", "--node", "start"],
            "你到了森林。\n",
        )

    def test_swapped_pair_order_gives_same_result(self):
        """显式指定节点时交换 --choice 与 --node 两对参数的顺序。"""
        choice_first = self.run_and_assert_ok(
            [self.sample_copy, "--choice", "1", "--node", "start"],
            "你到了森林。\n",
        )
        node_first = self.run_and_assert_ok(
            [self.sample_copy, "--node", "start", "--choice", "1"],
            "你到了森林。\n",
        )
        self.assertEqual(choice_first.stdout, node_first.stdout)
        self.assertEqual(choice_first.stderr, node_first.stderr)
        self.assertEqual(choice_first.returncode, node_first.returncode)


class TestPreviewArgsChoiceValue(PreviewArgsTestCase):
    """格式正确但选择值无法解析：报选择值错误而非用法提示。"""

    def test_choice_abc_reports_value_error_not_usage(self):
        before = self.sample_copy.read_bytes()
        args = [self.sample_copy, "--choice", "abc"]
        result = self.run_preview(args)
        self.assert_copy_unchanged(before)
        label = "参数 {!r}".format([str(arg) for arg in args])
        self.assertEqual(result.returncode, 2, label)
        self.assertEqual(result.stdout, b"", label + "：标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assertNotIn("Traceback", stderr, label)
        self.assertIn("无法解析为整数", stderr, label)
        self.assertIn("'abc'", stderr, label)
        self.assertIn("start", stderr, label + "：应包含起点编号 start")
        self.assertNotIn("用法", stderr, label + "：选择值错误不应混入用法提示")


if __name__ == "__main__":
    unittest.main()
