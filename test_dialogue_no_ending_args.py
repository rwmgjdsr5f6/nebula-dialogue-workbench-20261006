# -*- coding: utf-8 -*-
"""dialogue.py no-ending 命令参数格式回归测试。

固定 no-ending 的参数拒绝规则：只接受一个文件路径。缺少路径、
额外位置参数、任何选项参数（--node/--choice/未知选项/连写形式）、
路径位置出现形似选项的记号等，均应在读取文件前以退出码 2 拒绝，
标准输出为空，标准错误仅为
``python dialogue.py no-ending <文件路径>`` 加一个结尾换行。
另含一个合法路径的成功对照，防止把所有调用都误判成拒绝。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

合法对话使用 sample.json 的临时字节副本，样例原件与业务源码保持原样；
每次调用前后核对输入文件字节不变，临时数据结束后清理。
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIALOGUE = PROJECT_DIR / "dialogue.py"
SAMPLE = PROJECT_DIR / "sample.json"

# no-ending 参数错误专用的单行用法文字（fail() 会在末尾补一个换行）。
# 在此硬编码以固定文案；与其余五条命令的用法互不影响。
NO_ENDING_USAGE_TEXT = "python dialogue.py no-ending <文件路径>\n"

# sample.json 既有报告结果（按解析后的 JSON 核对）。
EXPECTED_SAMPLE = {"start": "start", "no_ending": []}


class NoEndingArgsTestCase(unittest.TestCase):
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

    def run_no_ending(self, rest):
        """执行 no-ending，rest 为文件路径位置开始的完整参数列表（不抛异常）。"""
        argv = [sys.executable, str(DIALOGUE), "no-ending"] + [
            str(a) for a in rest
        ]
        return subprocess.run(argv, capture_output=True)

    def describe(self, rest):
        return " ".join(str(a) for a in rest)

    def assert_usage_error(self, rest, input_path=None):
        """格式错误：退出码 2、stdout 为空、stderr 仅为单行用法加换行。"""
        if input_path is not None:
            before = input_path.read_bytes()
        result = self.run_no_ending(rest)
        label = "参数：no-ending {}".format(self.describe(rest))
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
            stderr, NO_ENDING_USAGE_TEXT,
            "{}：标准错误应仅为单行用法加末尾换行，实际 {!r}".format(
                label, stderr),
        )
        self.assertNotIn(
            "Traceback", stderr,
            "{}：标准错误不应包含调用栈".format(label),
        )
        self.assertNotIn(
            "岔路口", stderr,
            "{}：格式错误时标准错误不应包含节点文字".format(label),
        )
        if input_path is not None:
            self.assertEqual(
                input_path.read_bytes(), before,
                "{}：输入文件在执行后发生变化".format(label),
            )
        return result

    def assert_success(self, rest):
        """成功对照：退出码 0、stderr 为空、stdout 为报告 JSON 加换行。"""
        before = self.sample_copy.read_bytes()
        result = self.run_no_ending(rest)
        label = "参数：no-ending {}".format(self.describe(rest))
        self.assertEqual(
            result.returncode, 0,
            "{}：应为退出码 0，实际 {}；stderr={!r}".format(
                label, result.returncode, result.stderr),
        )
        self.assertEqual(
            result.stderr, b"",
            "{}：成功时标准错误应为空，实际 {!r}".format(label, result.stderr),
        )
        stdout = result.stdout.decode("utf-8")
        self.assertTrue(
            stdout.endswith("\n"),
            "{}：标准输出应以一个结尾换行结束：{!r}".format(label, stdout),
        )
        self.assertNotIn(
            "\n", stdout[:-1],
            "{}：结尾换行之前不应再有换行：{!r}".format(label, stdout),
        )
        self.assertEqual(
            json.loads(stdout[:-1]), EXPECTED_SAMPLE,
            "{}：解析后的 JSON 应与 sample.json 报告预期一致".format(label),
        )
        self.assertEqual(
            self.sample_copy.read_bytes(), before,
            "{}：输入文件在执行后发生变化".format(label),
        )
        return result


class TestNoEndingUsageErrors(NoEndingArgsTestCase):
    """no-ending 参数格式错误：一律只输出单行用法，退出码 2。"""

    def test_missing_file_path(self):
        """缺少文件路径：只有 no-ending 本身。"""
        self.assert_usage_error([])

    def test_extra_positional_argument(self):
        """文件路径之后出现额外位置参数。"""
        self.assert_usage_error([self.sample_copy, "extra"],
                                input_path=self.sample_copy)

    def test_two_positional_paths(self):
        """出现两个文件路径位置参数：仍是用法错误。"""
        other = self.tmp_dir / "other.json"
        self.assert_usage_error([self.sample_copy, other],
                                input_path=self.sample_copy)

    def test_node_option_rejected(self):
        """no-ending 不接受 --node。"""
        self.assert_usage_error([self.sample_copy, "--node", "forest"],
                                input_path=self.sample_copy)

    def test_choice_option_rejected(self):
        """no-ending 不接受 --choice。"""
        self.assert_usage_error([self.sample_copy, "--choice", "1"],
                                input_path=self.sample_copy)

    def test_unknown_option_rejected(self):
        """未知选项 --verbose 被拒绝。"""
        self.assert_usage_error([self.sample_copy, "--verbose"],
                                input_path=self.sample_copy)

    def test_equals_form_rejected(self):
        """--node=forest 连写形式被拒绝。"""
        self.assert_usage_error([self.sample_copy, "--node=forest"],
                                input_path=self.sample_copy)

    def test_option_before_path_rejected(self):
        """选项出现在路径之前也在读取文件前拒绝。"""
        self.assert_usage_error(["--node", "forest", self.sample_copy],
                                input_path=self.sample_copy)

    def test_single_option_token_not_treated_as_path(self):
        """路径位置只有一个形似选项的记号 --node：不得把它当路径读取。"""
        result = self.assert_usage_error(["--node"])
        self.assertNotIn(
            "无法读取文件", result.stderr.decode("utf-8"),
            "形似选项的记号不应触发文件读取",
        )

    def test_bare_dash_not_treated_as_path(self):
        """孤立的“-”也属于形似选项记号，按用法错误拒绝，不读取文件。"""
        self.assert_usage_error(["-"])

    def test_dash_prefixed_path_not_treated_as_path(self):
        """以减号开头的任意路径位置字符串（如 -sample.json）在读文件前拒绝。"""
        result = self.assert_usage_error(["-sample.json"])
        self.assertNotIn(
            "无法读取文件", result.stderr.decode("utf-8"),
            "减号开头的记号不应触发文件读取",
        )

    def test_extra_arg_with_nonexistent_path_still_usage_error(self):
        """额外参数 + 不存在的路径：参数格式检查先于文件读取，
        仍只报同一用法错误，不变成无法读取文件，也不创建该路径。"""
        missing = self.tmp_dir / "never_created.json"
        self.assertFalse(missing.exists(), "前置条件：路径尚不存在")
        result = self.assert_usage_error([missing, "extra"])
        self.assertNotIn(
            "无法读取文件", result.stderr.decode("utf-8"),
            "参数格式错误应先于文件读取，不应出现无法读取文件",
        )
        self.assertFalse(
            missing.exists(),
            "格式错误直接退出，不应创建传入的不存在路径",
        )

    def test_extra_arg_with_broken_json_still_usage_error(self):
        """额外参数 + 仅含 { 的语法错误文件：参数格式检查先于文件读取，
        仍只报用法错误，不提前报告 JSON 语法错误。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{", encoding="utf-8")
        before = broken.read_bytes()
        result = self.assert_usage_error([broken, "--node", "forest"],
                                         input_path=broken)
        self.assertNotIn(
            "JSON 语法错误", result.stderr.decode("utf-8"),
            "参数格式错误应先于文件读取，不应出现 JSON 语法错误",
        )
        self.assertEqual(
            broken.read_bytes(), before, "语法错误文件在执行后发生变化"
        )


class TestNoEndingSuccessControl(NoEndingArgsTestCase):
    """成功对照：单个合法文件路径正常出报告。"""

    def test_single_valid_path_reports(self):
        """只传 sample.json 的临时副本：正常输出无结尾路径报告。"""
        self.assert_success([self.sample_copy])


if __name__ == "__main__":
    unittest.main()
