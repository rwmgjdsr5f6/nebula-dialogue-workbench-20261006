# -*- coding: utf-8 -*-
"""dialogue.py preview 命令参数格式回归测试。

固定 preview 既有的参数拒绝规则：缺文件路径、缺 --choice、未知开关、
多余位置参数、--choice=1 写法、开关缺值、--choice/--node 重复出现等，
均应以退出码 2 拒绝，标准输出为空，标准错误仅为完整用法文字加一个
结尾换行；且参数格式检查先于文件读取。另含少量成功对照及
--choice 非整数（语义错误而非格式错误）的对照。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

所有合法对话均使用 sample.json 的临时字节副本，样例原件与业务源码
保持原样；每次调用前后核对输入文件字节不变，临时副本结束后清理。
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

# 既有的完整用法文字（fail() 会在末尾补一个换行）。在此硬编码以固定
# 现有文案：源码若改动该文案，本回归测试应失败。新增 inspect 命令后
# 用法文字同步追加对应行。
USAGE_TEXT = (
    "用法：\n"
    "  python dialogue.py validate <文件路径>\n"
    "  python dialogue.py preview <文件路径> --choice <选项编号> "
    "[--node <节点编号>]\n"
    "  python dialogue.py inspect <文件路径> [--node <节点编号>]\n"
)


class PreviewArgsTestCase(unittest.TestCase):
    """通过公开命令入口核对退出码、标准输出与标准错误。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)
        # 合法对话使用 sample.json 的临时字节副本（原样复制，不重新序列化）。
        self.sample_copy = self.tmp_dir / "sample_copy.json"
        shutil.copyfile(SAMPLE, self.sample_copy)
        self._sample_original_bytes = SAMPLE.read_bytes()

    def tearDown(self):
        # 仓库自带样例在任何用例后都必须字节不变。
        self.assertEqual(
            SAMPLE.read_bytes(),
            self._sample_original_bytes,
            "sample.json 在测试过程中被修改",
        )

    def run_preview(self, rest):
        """执行 preview，rest 为文件路径位置开始的完整参数列表（不抛异常）。"""
        argv = [sys.executable, str(DIALOGUE), "preview"] + [str(a) for a in rest]
        return subprocess.run(argv, capture_output=True)

    def describe(self, rest):
        return " ".join(str(a) for a in rest)

    def assert_usage_error(self, rest, input_path=None):
        """格式错误：退出码 2、stdout 为空、stderr 仅为用法文字加换行。"""
        if input_path is not None:
            before = input_path.read_bytes()
        result = self.run_preview(rest)
        label = "参数：preview {}".format(self.describe(rest))
        self.assertEqual(
            result.returncode, 2,
            "{}：应为退出码 2，实际 {}；stderr={!r}".format(
                label, result.returncode, result.stderr),
        )
        self.assertEqual(
            result.stdout, b"",
            "{}：格式错误时标准输出应为空，实际 {!r}".format(
                label, result.stdout),
        )
        stderr = result.stderr.decode("utf-8")
        self.assertEqual(
            stderr, USAGE_TEXT,
            "{}：标准错误应仅为完整用法文字加末尾换行，实际 {!r}".format(
                label, stderr),
        )
        self.assertNotIn(
            "Traceback", stderr,
            "{}：标准错误不应包含调用栈".format(label),
        )
        self.assertNotIn(
            "森林", stderr,
            "{}：格式错误时标准错误不应包含节点文字".format(label),
        )
        if input_path is not None:
            self.assertEqual(
                input_path.read_bytes(), before,
                "{}：输入文件在执行后发生变化".format(label),
            )
        return result

    def assert_success_forest(self, rest):
        """成功对照：退出码 0、stderr 为空、stdout 仅为森林文字加换行。"""
        before = self.sample_copy.read_bytes()
        result = self.run_preview(rest)
        label = "参数：preview {}".format(self.describe(rest))
        self.assertEqual(
            result.returncode, 0,
            "{}：应为退出码 0，实际 {}；stderr={!r}".format(
                label, result.returncode, result.stderr),
        )
        self.assertEqual(
            result.stderr, b"",
            "{}：成功时标准错误应为空，实际 {!r}".format(
                label, result.stderr),
        )
        self.assertEqual(
            result.stdout.decode("utf-8"), "你到了森林。\n",
            "{}：标准输出应仅为森林文字加一个结尾换行，实际 {!r}".format(
                label, result.stdout),
        )
        self.assertEqual(
            self.sample_copy.read_bytes(), before,
            "{}：输入文件在执行后发生变化".format(label),
        )
        return result


class TestPreviewUsageErrors(PreviewArgsTestCase):
    """preview 参数格式错误：一律只输出用法文字，退出码 2。"""

    def test_missing_file_path(self):
        """缺少文件路径：只有 preview 本身。"""
        self.assert_usage_error([])

    def test_only_file_path(self):
        """只有文件路径，缺少 --choice 一对。"""
        self.assert_usage_error([self.sample_copy])

    def test_only_node_without_choice(self):
        """只有 --node start 而缺少 --choice。"""
        self.assert_usage_error([self.sample_copy, "--node", "start"],
                               input_path=self.sample_copy)

    def test_choice_without_value_at_end(self):
        """末尾的 --choice 没有值。"""
        self.assert_usage_error([self.sample_copy, "--choice"],
                               input_path=self.sample_copy)

    def test_node_without_value_at_end(self):
        """末尾的 --node 没有值。"""
        self.assert_usage_error(
            [self.sample_copy, "--choice", "1", "--node"],
            input_path=self.sample_copy,
        )

    def test_unknown_switch_after_path(self):
        """文件路径之后的参数名位置出现未知开关。"""
        self.assert_usage_error(
            [self.sample_copy, "--choice", "1", "--bogus"],
            input_path=self.sample_copy,
        )

    def test_extra_positional_argument(self):
        """文件路径之后出现额外位置参数。"""
        self.assert_usage_error(
            [self.sample_copy, "--choice", "1", "extra"],
            input_path=self.sample_copy,
        )

    def test_equals_form_choice_is_rejected(self):
        """--choice=1 这种连写形式不被支持，按用法错误拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--choice=1"],
            input_path=self.sample_copy,
        )

    def test_duplicate_choice_same_value(self):
        """--choice 重复出现，即使两次值相同仍是用法错误。"""
        self.assert_usage_error(
            [self.sample_copy, "--choice", "1", "--choice", "1"],
            input_path=self.sample_copy,
        )

    def test_duplicate_node_same_value(self):
        """--node 重复出现，即使两次值相同仍是用法错误。"""
        self.assert_usage_error(
            [self.sample_copy, "--choice", "1",
             "--node", "start", "--node", "start"],
            input_path=self.sample_copy,
        )

    def test_duplicate_choice_with_nonexistent_path_still_usage_error(self):
        """重复参数 + 不存在的文件路径：参数格式检查先于文件读取，
        仍只报用法错误，不变成无法读取文件，也不创建该路径。"""
        missing = self.tmp_dir / "never_created.json"
        self.assertFalse(missing.exists(), "前置条件：路径尚不存在")
        result = self.assert_usage_error(
            [missing, "--choice", "1", "--choice", "1"],
        )
        self.assertNotIn(
            "无法读取文件", result.stderr.decode("utf-8"),
            "参数格式错误应先于文件读取，不应出现无法读取文件",
        )
        self.assertFalse(
            missing.exists(),
            "格式错误直接退出，不应创建传入的不存在路径",
        )


class TestPreviewSuccessControls(PreviewArgsTestCase):
    """少量成功对照：省略/显式 --node 及参数顺序互换结果一致。"""

    def test_omit_node_choice_1_outputs_forest(self):
        """省略 --node 时从 start 出发，--choice 1 到森林。"""
        self.assert_success_forest([self.sample_copy, "--choice", "1"])

    def test_explicit_start_choice_1_outputs_forest(self):
        """显式 --node start 与省略 --node 结果相同。"""
        self.assert_success_forest(
            [self.sample_copy, "--choice", "1", "--node", "start"]
        )

    def test_swapped_pair_order_matches(self):
        """显式指定节点时交换 --node/--choice 两对参数的顺序，结果一致。"""
        node_first = self.assert_success_forest(
            [self.sample_copy, "--node", "start", "--choice", "1"]
        )
        choice_first = self.run_preview(
            [self.sample_copy, "--choice", "1", "--node", "start"]
        )
        self.assertEqual(
            node_first.returncode, choice_first.returncode,
            "两种参数顺序的退出码应一致",
        )
        self.assertEqual(
            node_first.stdout, choice_first.stdout,
            "两种参数顺序的标准输出应一致",
        )
        self.assertEqual(
            node_first.stderr, choice_first.stderr,
            "两种参数顺序的标准错误应一致",
        )


class TestPreviewChoiceValueError(PreviewArgsTestCase):
    """格式正确但 --choice 值非整数：属于选择值错误，不是用法格式错误。"""

    def test_non_integer_choice_reports_parse_error_not_usage(self):
        before = self.sample_copy.read_bytes()
        result = self.run_preview([self.sample_copy, "--choice", "abc"])
        label = "参数：preview {} --choice abc".format(self.sample_copy)
        self.assertEqual(
            result.returncode, 2,
            "{}：应为退出码 2，实际 {}；stderr={!r}".format(
                label, result.returncode, result.stderr),
        )
        self.assertEqual(
            result.stdout, b"",
            "{}：失败时标准输出应为空，实际 {!r}".format(label, result.stdout),
        )
        stderr = result.stderr.decode("utf-8")
        self.assertIn(
            "无法解析为整数", stderr,
            "{}：标准错误应说明无法解析为整数，实际 {!r}".format(label, stderr),
        )
        self.assertIn(
            "起点编号", stderr,
            "{}：省略 --node 时应说明起点编号，实际 {!r}".format(label, stderr),
        )
        self.assertIn(
            "start", stderr,
            "{}：标准错误应包含起点编号 start，实际 {!r}".format(label, stderr),
        )
        self.assertNotIn(
            "用法：", stderr,
            "{}：选择值错误不应混入用法提示，实际 {!r}".format(label, stderr),
        )
        self.assertNotEqual(
            stderr, USAGE_TEXT,
            "{}：选择值错误的标准错误不应等于用法文字".format(label),
        )
        self.assertNotIn(
            "Traceback", stderr,
            "{}：标准错误不应包含调用栈".format(label),
        )
        self.assertEqual(
            self.sample_copy.read_bytes(), before,
            "{}：输入文件在执行后发生变化".format(label),
        )


if __name__ == "__main__":
    unittest.main()
