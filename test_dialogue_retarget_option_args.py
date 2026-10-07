# -*- coding: utf-8 -*-
"""dialogue.py retarget-option 命令参数格式回归测试。

固定 retarget-option 的参数拒绝规则：只接受「一个文件路径 + 一次分写的
--node <来源编号> + 一次分写的 --choice <选项编号> + 一次分写的
--to <目标编号>」的固定顺序。缺少路径或任一编号值、--node/--choice/
--to 重复、未知或额外参数、--node=编号、--choice=1 或 --to=编号 连写
形式、三对参数顺序颠倒、路径位置出现形似选项的记号等，均应在读取
文件前以退出码 2 拒绝，标准输出为空，标准错误仅为
``python dialogue.py retarget-option <文件路径> --node <来源编号>
--choice <选项编号> --to <目标编号>`` 加一个结尾换行。另含合法参数的
成功对照，防止把所有调用都误判成拒绝。

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

# retarget-option 参数错误专用的单行用法文字（fail() 会在末尾补一个换行）。
RETARGET_USAGE_TEXT = (
    "python dialogue.py retarget-option <文件路径> --node <来源编号>"
    " --choice <选项编号> --to <目标编号>\n"
)

# sample.json 把起点第 1 个选项改指 river 的既有结果（按解析后的 JSON 核对）。
EXPECTED_BOTH_RIVER = {
    "start": "start",
    "nodes": [
        {"id": "start", "text": "你来到岔路口。", "options": [
            {"text": "向左走", "target": "river"},
            {"text": "向右走", "target": "river"},
        ]},
        {"id": "forest", "text": "你到了森林。", "options": []},
        {"id": "river", "text": "你到了河边。", "options": []},
    ],
}


class RetargetArgsTestCase(unittest.TestCase):
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

    def run_retarget(self, rest):
        """执行 retarget-option，rest 为文件路径位置开始的完整参数列表。"""
        argv = [sys.executable, str(DIALOGUE), "retarget-option"] + [
            str(a) for a in rest
        ]
        return subprocess.run(argv, capture_output=True)

    def describe(self, rest):
        return " ".join(str(a) for a in rest)

    def assert_usage_error(self, rest, input_path=None):
        """格式错误：退出码 2、stdout 为空、stderr 仅为单行用法加换行。"""
        if input_path is not None:
            before = input_path.read_bytes()
        result = self.run_retarget(rest)
        label = "参数：retarget-option {}".format(self.describe(rest))
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
            stderr, RETARGET_USAGE_TEXT,
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

    def assert_success(self, rest, expected_object):
        """成功对照：退出码 0、stderr 为空、stdout 为结果 JSON 加换行。"""
        before = self.sample_copy.read_bytes()
        result = self.run_retarget(rest)
        label = "参数：retarget-option {}".format(self.describe(rest))
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
            json.loads(stdout[:-1]), expected_object,
            "{}：解析后的 JSON 应与预期一致".format(label),
        )
        self.assertEqual(
            self.sample_copy.read_bytes(), before,
            "{}：输入文件在执行后发生变化".format(label),
        )
        return result


class TestRetargetUsageErrors(RetargetArgsTestCase):
    """retarget-option 参数格式错误：一律只输出单行用法，退出码 2。"""

    def test_missing_file_path(self):
        """缺少文件路径：只有 retarget-option 本身。"""
        self.assert_usage_error([])

    def test_only_file_path(self):
        """只有文件路径、没有三对参数。"""
        self.assert_usage_error([self.sample_copy], input_path=self.sample_copy)

    def test_missing_choice_and_to(self):
        """只有 --node，缺 --choice 与 --to。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start"], input_path=self.sample_copy
        )

    def test_missing_to_option(self):
        """有 --node 与 --choice，缺 --to。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--choice", "1"],
            input_path=self.sample_copy,
        )

    def test_missing_to_value(self):
        """--to 之后缺少目标编号。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--choice", "1", "--to"],
            input_path=self.sample_copy,
        )

    def test_missing_choice_value(self):
        """--choice 之后缺少选项编号（--to 被当作编号值时整体仍不匹配）。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--choice", "--to", "river"],
            input_path=self.sample_copy,
        )

    def test_missing_node_value(self):
        """--node 之后缺少来源编号（--choice 被当作编号值时整体仍不匹配）。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "--choice", "1", "--to", "river"],
            input_path=self.sample_copy,
        )

    def test_duplicate_node_option(self):
        """--node 出现两次：重复参数被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--node", "forest",
             "--choice", "1", "--to", "river"],
            input_path=self.sample_copy,
        )

    def test_duplicate_choice_option(self):
        """--choice 出现两次：重复参数被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--choice", "1",
             "--choice", "2", "--to", "river"],
            input_path=self.sample_copy,
        )

    def test_duplicate_to_option(self):
        """--to 出现两次：重复参数被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--choice", "1",
             "--to", "river", "--to", "forest"],
            input_path=self.sample_copy,
        )

    def test_unknown_option_rejected(self):
        """未知选项 --verbose 被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--choice", "1",
             "--to", "river", "--verbose"],
            input_path=self.sample_copy,
        )

    def test_extra_positional_argument(self):
        """合法参数之后出现额外位置参数。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--choice", "1",
             "--to", "river", "extra"],
            input_path=self.sample_copy,
        )

    def test_equals_form_node_rejected(self):
        """--node=start 连写形式被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node=start", "--choice", "1", "--to", "river"],
            input_path=self.sample_copy,
        )

    def test_equals_form_choice_rejected(self):
        """--choice=1 连写形式被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--choice=1", "--to", "river"],
            input_path=self.sample_copy,
        )

    def test_equals_form_to_rejected(self):
        """--to=river 连写形式被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--choice", "1",
             "--to=river"],
            input_path=self.sample_copy,
        )

    def test_choice_before_node_rejected(self):
        """--choice 在 --node 之前不符合固定顺序，在读文件前拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--choice", "1", "--node", "start",
             "--to", "river"],
            input_path=self.sample_copy,
        )

    def test_to_before_choice_rejected(self):
        """--to 在 --choice 之前不符合固定顺序，在读文件前拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--to", "river",
             "--choice", "1"],
            input_path=self.sample_copy,
        )

    def test_options_before_path_rejected(self):
        """三对参数出现在路径之前不符合固定顺序，也在读文件前拒绝。"""
        self.assert_usage_error(
            ["--node", "start", "--choice", "1", "--to", "river",
             self.sample_copy],
            input_path=self.sample_copy,
        )

    def test_option_like_path_rejected(self):
        """路径位置是形似选项的记号：不得把它当路径读取。"""
        result = self.assert_usage_error(
            ["--node", "start", "--choice", "1", "--to", "river",
             "--unknown"])
        self.assertNotIn(
            "无法读取文件", result.stderr.decode("utf-8"),
            "形似选项的记号不应触发文件读取",
        )

    def test_bare_dash_not_treated_as_path(self):
        """孤立的“-”也属于形似选项记号，按用法错误拒绝，不读取文件。"""
        self.assert_usage_error(
            ["-", "--node", "start", "--choice", "1", "--to", "river"]
        )

    def test_missing_value_with_nonexistent_path_still_usage_error(self):
        """缺少目标值 + 不存在的路径：参数格式检查先于文件读取，
        仍只报同一用法错误，不变成无法读取文件，也不创建该路径。"""
        missing = self.tmp_dir / "never_created.json"
        self.assertFalse(missing.exists(), "前置条件：路径尚不存在")
        result = self.assert_usage_error(
            [missing, "--node", "start", "--choice", "1", "--to"]
        )
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
        result = self.assert_usage_error(
            [broken, "--node", "start", "--choice", "1", "--to", "river",
             "extra"],
            input_path=broken,
        )
        self.assertNotIn(
            "JSON 语法错误", result.stderr.decode("utf-8"),
            "参数格式错误应先于文件读取，不应出现 JSON 语法错误",
        )
        self.assertEqual(
            broken.read_bytes(), before, "语法错误文件在执行后发生变化"
        )


class TestRetargetSuccessControl(RetargetArgsTestCase):
    """成功对照：固定顺序的合法参数正常输出重定向结果。"""

    def test_valid_args_start_choice_1_to_river(self):
        """对 sample.json 临时副本把起点第 1 个选项改指 river：正常输出。"""
        self.assert_success(
            [self.sample_copy, "--node", "start", "--choice", "1",
             "--to", "river"],
            EXPECTED_BOTH_RIVER,
        )

    def test_option_like_source_value_accepted(self):
        """来源编号形似选项（如 -x）照收为编号，按节点不存在处理而非用法错误。"""
        result = self.run_retarget(
            [self.sample_copy, "--node", "-x", "--choice", "1", "--to", "river"]
        )
        self.assertEqual(result.returncode, 2, "节点不存在时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assertNotEqual(
            stderr, RETARGET_USAGE_TEXT,
            "形似选项的来源编号应照收为编号，不应报用法错误",
        )
        self.assertIn("文件中不存在编号为 '-x' 的节点", stderr)

    def test_option_like_target_value_accepted(self):
        """目标编号形似选项（如 -y）照收为编号，按节点不存在处理。"""
        result = self.run_retarget(
            [self.sample_copy, "--node", "start", "--choice", "1", "--to", "-y"]
        )
        self.assertEqual(result.returncode, 2, "节点不存在时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assertNotEqual(
            stderr, RETARGET_USAGE_TEXT,
            "形似选项的目标编号应照收为编号，不应报用法错误",
        )
        self.assertIn("文件中不存在编号为 '-y' 的节点", stderr)

    def test_option_like_choice_value_accepted(self):
        """选项编号位置形似选项（如 -n）照收为编号原值，按整数解析失败
        处理，而非参数用法错误。"""
        result = self.run_retarget(
            [self.sample_copy, "--node", "start", "--choice", "-n",
             "--to", "river"]
        )
        self.assertEqual(result.returncode, 2, "解析失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assertNotEqual(
            stderr, RETARGET_USAGE_TEXT,
            "形似选项的选项编号值应照收，不应报用法错误",
        )
        self.assertIn("无法解析为整数", stderr)


if __name__ == "__main__":
    unittest.main()
