# -*- coding: utf-8 -*-
"""dialogue.py set-node-text 命令参数格式回归测试。

固定 set-node-text 的参数拒绝规则：只接受「一个文件路径 + 一次分写的
--node <节点编号> + 一次分写的 --text <新正文>」的固定顺序。缺少路径、
编号或正文值、--node/--text 重复、未知或额外参数、--node=编号 或
--text=正文 连写形式、两对参数顺序颠倒、路径位置出现形似选项的记号等，
均应在读取文件前以退出码 2 拒绝，标准输出为空，标准错误仅为
``python dialogue.py set-node-text <文件路径> --node <节点编号> --text <新正文>``
加一个结尾换行。编号与正文位置的值不做形式限制（空字符串、纯空白、
形似选项的记号都作为值照收）。另含合法参数的成功对照，防止把所有调用
都误判成拒绝。

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

# set-node-text 参数错误专用的单行用法文字（fail() 会在末尾补一个换行）。
# 在此硬编码以固定现有文案；与其余命令的用法文字互不影响。
SET_NODE_TEXT_USAGE_TEXT = (
    "python dialogue.py set-node-text <文件路径> --node <节点编号>"
    " --text <新正文>\n"
)

# sample.json 把 forest 正文改为“林间很安静。”的预期结果（按解析后的
# JSON 核对）：只有 forest 的 text 改变，其余内容与样例一致。
EXPECTED_QUIET_FOREST = {
    "start": "start",
    "nodes": [
        {"id": "start", "text": "你来到岔路口。", "options": [
            {"text": "向左走", "target": "forest"},
            {"text": "向右走", "target": "river"},
        ]},
        {"id": "forest", "text": "林间很安静。", "options": []},
        {"id": "river", "text": "你到了河边。", "options": []},
    ],
}


class SetNodeTextArgsTestCase(unittest.TestCase):
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

    def run_set_text(self, rest):
        """执行 set-node-text，rest 为文件路径位置开始的完整参数列表
        （不抛异常）。"""
        argv = [sys.executable, str(DIALOGUE), "set-node-text"] + [
            str(a) for a in rest
        ]
        return subprocess.run(argv, capture_output=True)

    def describe(self, rest):
        return " ".join(str(a) for a in rest)

    def assert_usage_error(self, rest, input_path=None):
        """格式错误：退出码 2、stdout 为空、stderr 仅为单行用法加换行。"""
        if input_path is not None:
            before = input_path.read_bytes()
        result = self.run_set_text(rest)
        label = "参数：set-node-text {}".format(self.describe(rest))
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
            stderr, SET_NODE_TEXT_USAGE_TEXT,
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
        result = self.run_set_text(rest)
        label = "参数：set-node-text {}".format(self.describe(rest))
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


class TestSetNodeTextUsageErrors(SetNodeTextArgsTestCase):
    """set-node-text 参数格式错误：一律只输出单行用法，退出码 2。"""

    def test_missing_file_path(self):
        """缺少文件路径：只有 set-node-text 本身。"""
        self.assert_usage_error([])

    def test_missing_node_option(self):
        """只有文件路径、没有 --node 与 --text。"""
        self.assert_usage_error([self.sample_copy],
                                input_path=self.sample_copy)

    def test_missing_text_option(self):
        """只有 --node 编号、没有 --text。"""
        self.assert_usage_error([self.sample_copy, "--node", "forest"],
                                input_path=self.sample_copy)

    def test_missing_text_value(self):
        """--text 之后缺少新正文。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "forest", "--text"],
            input_path=self.sample_copy,
        )

    def test_missing_node_value(self):
        """--node 之后缺少编号（--text 被当作编号值时整体仍不匹配）。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "--text", "新正文"],
            input_path=self.sample_copy,
        )

    def test_duplicate_node_option(self):
        """--node 出现两次：重复参数被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "forest", "--node", "river",
             "--text", "新正文"],
            input_path=self.sample_copy,
        )

    def test_duplicate_text_option(self):
        """--text 出现两次：重复参数被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "forest", "--text", "甲",
             "--text", "乙"],
            input_path=self.sample_copy,
        )

    def test_unknown_option_rejected(self):
        """未知选项 --verbose 被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "forest", "--text", "甲",
             "--verbose"],
            input_path=self.sample_copy,
        )

    def test_extra_positional_argument(self):
        """合法参数之后出现额外位置参数。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "forest", "--text", "甲", "extra"],
            input_path=self.sample_copy,
        )

    def test_equals_form_node_rejected(self):
        """--node=forest 连写形式被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node=forest", "--text", "甲"],
            input_path=self.sample_copy,
        )

    def test_equals_form_text_rejected(self):
        """--text=甲 连写形式被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "forest", "--text=甲"],
            input_path=self.sample_copy,
        )

    def test_reversed_option_order_rejected(self):
        """--text 在 --node 之前不符合固定顺序，在读文件前拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--text", "甲", "--node", "forest"],
            input_path=self.sample_copy,
        )

    def test_options_before_path_rejected(self):
        """--node/--text 出现在路径之前不符合固定顺序，也在读文件前拒绝。"""
        self.assert_usage_error(
            ["--node", "forest", "--text", "甲", self.sample_copy],
            input_path=self.sample_copy,
        )

    def test_option_like_path_rejected(self):
        """路径位置是形似选项的记号：不得把它当路径读取。"""
        result = self.assert_usage_error(
            ["--node", "forest", "--text", "甲", "--node", "x"])
        self.assertNotIn(
            "无法读取文件", result.stderr.decode("utf-8"),
            "形似选项的记号不应触发文件读取",
        )

    def test_bare_dash_not_treated_as_path(self):
        """孤立的“-”也属于形似选项记号，按用法错误拒绝，不读取文件。"""
        self.assert_usage_error(["-", "--node", "forest", "--text", "甲"])

    def test_path_starting_with_dash_not_read(self):
        """以减号开头的路径按用法错误拒绝，不触发文件读取。"""
        result = self.assert_usage_error(
            ["-sample.json", "--node", "forest", "--text", "甲"])
        self.assertNotIn("无法读取文件", result.stderr.decode("utf-8"))

    def test_missing_value_with_nonexistent_path_still_usage_error(self):
        """缺少正文 + 不存在的路径：参数格式检查先于文件读取，
        仍只报同一用法错误，不变成无法读取文件，也不创建该路径。"""
        missing = self.tmp_dir / "never_created.json"
        self.assertFalse(missing.exists(), "前置条件：路径尚不存在")
        result = self.assert_usage_error(
            [missing, "--node", "forest", "--text"])
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
            [broken, "--node", "forest", "--text", "甲", "extra"],
            input_path=broken,
        )
        self.assertNotIn(
            "JSON 语法错误", result.stderr.decode("utf-8"),
            "参数格式错误应先于文件读取，不应出现 JSON 语法错误",
        )
        self.assertEqual(
            broken.read_bytes(), before, "语法错误文件在执行后发生变化"
        )


class TestSetNodeTextSuccessControl(SetNodeTextArgsTestCase):
    """成功对照：固定顺序的合法参数正常输出修改结果。"""

    def test_valid_args_set_forest_text(self):
        """对 sample.json 临时副本把 forest 正文改为“林间很安静。”。"""
        self.assert_success(
            [self.sample_copy, "--node", "forest", "--text", "林间很安静。"],
            EXPECTED_QUIET_FOREST,
        )

    def test_option_like_node_value_accepted(self):
        """节点编号形似选项（如 -x）照收为编号，按节点不存在处理而非
        用法错误。"""
        result = self.run_set_text(
            [self.sample_copy, "--node", "-x", "--text", "甲"])
        self.assertEqual(result.returncode, 2, "节点不存在时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assertNotEqual(
            stderr, SET_NODE_TEXT_USAGE_TEXT,
            "形似选项的编号应照收为值，不应报用法错误",
        )
        self.assertIn("文件中不存在编号为 '-x' 的节点", stderr)

    def test_option_like_text_value_accepted(self):
        """新正文形似选项（如 --node、-y）照收为正文，正常完成修改。"""
        expected = {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "--node", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        }
        self.assert_success(
            [self.sample_copy, "--node", "forest", "--text", "--node"],
            expected,
        )

    def test_empty_text_value_accepted(self):
        """空字符串是合法正文值，正常保存为空串而非用法错误。"""
        expected = {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        }
        self.assert_success(
            [self.sample_copy, "--node", "forest", "--text", ""],
            expected,
        )

    def test_blank_text_value_accepted(self):
        """纯空白也是合法正文值，原样保存。"""
        expected = {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "   ", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        }
        self.assert_success(
            [self.sample_copy, "--node", "forest", "--text", "   "],
            expected,
        )


if __name__ == "__main__":
    unittest.main()
