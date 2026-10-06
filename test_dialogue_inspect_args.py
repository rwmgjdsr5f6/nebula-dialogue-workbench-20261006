# -*- coding: utf-8 -*-
"""dialogue.py inspect 命令参数格式回归测试。

固定 inspect 既有的参数拒绝规则：缺文件路径、--node 缺值、参数名位置
出现 --choice、额外位置参数、--node=start 连写形式、--node 重复出现等，
均应在读取文件前以退出码 2 拒绝，标准输出为空，标准错误仅为 inspect
专用完整用法文字加一个结尾换行。另含省略/显式 --node 的两个成功对照，
防止把所有调用都误判成拒绝。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

所有合法对话均使用 sample.json 的临时字节副本，样例原件与业务源码
保持原样；每次调用前后核对输入文件字节不变，临时数据结束后清理。
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

# 既有的 inspect 专用完整用法文字（fail() 会在末尾补一个换行）。在此硬编码
# 以固定现有文案：validate、preview、inspect 三条命令的文字都按当前文案
# 核对，源码若改动其中任何一条，本回归测试应失败。
INSPECT_USAGE_TEXT = (
    "用法：\n"
    "  python dialogue.py validate <文件路径>\n"
    "  python dialogue.py preview <文件路径> --choice <选项编号> "
    "[--node <节点编号>]\n"
    "  python dialogue.py inspect <文件路径> [--node <节点编号>]\n"
)

# sample.json 起点 start 的既有查看结果（按解析后的 JSON 核对）。
EXPECTED_START = {
    "id": "start",
    "text": "你来到岔路口。",
    "options": [
        {"choice": 1, "text": "向左走", "target": "forest"},
        {"choice": 2, "text": "向右走", "target": "river"},
    ],
}


class InspectArgsTestCase(unittest.TestCase):
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

    def run_inspect(self, rest):
        """执行 inspect，rest 为文件路径位置开始的完整参数列表（不抛异常）。"""
        argv = [sys.executable, str(DIALOGUE), "inspect"] + [str(a) for a in rest]
        return subprocess.run(argv, capture_output=True)

    def describe(self, rest):
        return " ".join(str(a) for a in rest)

    def assert_usage_error(self, rest, input_path=None):
        """格式错误：退出码 2、stdout 为空、stderr 仅为用法文字加换行。"""
        if input_path is not None:
            before = input_path.read_bytes()
        result = self.run_inspect(rest)
        label = "参数：inspect {}".format(self.describe(rest))
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
            stderr, INSPECT_USAGE_TEXT,
            "{}：标准错误应仅为完整用法文字加末尾换行，实际 {!r}".format(
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

    def assert_success_start(self, rest):
        """成功对照：退出码 0、stderr 为空、stdout 为 start 节点 JSON 加换行。

        对象内容按解析后的 JSON 核对，不依赖键顺序或空格排版；
        结尾换行单独核对。
        """
        before = self.sample_copy.read_bytes()
        result = self.run_inspect(rest)
        label = "参数：inspect {}".format(self.describe(rest))
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
            json.loads(stdout[:-1]), EXPECTED_START,
            "{}：解析后的 JSON 对象应与 start 节点预期完全一致".format(label),
        )
        self.assertNotIn(
            "用法：", stdout,
            "{}：成功输出不应混入用法提示".format(label),
        )
        self.assertEqual(
            self.sample_copy.read_bytes(), before,
            "{}：输入文件在执行后发生变化".format(label),
        )
        return result


class TestInspectUsageErrors(InspectArgsTestCase):
    """inspect 参数格式错误：一律只输出用法文字，退出码 2。"""

    def test_missing_file_path(self):
        """缺少文件路径：只有 inspect 本身。"""
        self.assert_usage_error([])

    def test_node_without_value_at_end(self):
        """文件路径之后只有 --node，缺少值。"""
        self.assert_usage_error([self.sample_copy, "--node"],
                                input_path=self.sample_copy)

    def test_choice_in_option_name_position(self):
        """参数名位置出现 --choice 1：inspect 不接受 --choice。"""
        self.assert_usage_error([self.sample_copy, "--choice", "1"],
                                input_path=self.sample_copy)

    def test_extra_positional_argument(self):
        """文件路径之后出现额外位置参数。"""
        self.assert_usage_error([self.sample_copy, "extra"],
                                input_path=self.sample_copy)

    def test_equals_form_node_is_rejected(self):
        """--node=start 这种连写形式不被支持，按用法错误拒绝。"""
        self.assert_usage_error([self.sample_copy, "--node=start"],
                                input_path=self.sample_copy)

    def test_duplicate_node_same_value(self):
        """--node 重复出现，即使两次都指定 start 仍是用法错误。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "start", "--node", "start"],
            input_path=self.sample_copy,
        )

    def test_duplicate_node_with_nonexistent_path_still_usage_error(self):
        """重复 --node + 不存在的文件路径：参数格式检查先于文件读取，
        仍只报同一用法错误，不变成无法读取文件，也不创建该路径。"""
        missing = self.tmp_dir / "never_created.json"
        self.assertFalse(missing.exists(), "前置条件：路径尚不存在")
        result = self.assert_usage_error(
            [missing, "--node", "start", "--node", "start"],
        )
        self.assertNotIn(
            "无法读取文件", result.stderr.decode("utf-8"),
            "参数格式错误应先于文件读取，不应出现无法读取文件",
        )
        self.assertFalse(
            missing.exists(),
            "格式错误直接退出，不应创建传入的不存在路径",
        )

    def test_node_without_value_with_broken_json_still_usage_error(self):
        """缺值 --node + 仅含 { 的语法错误文件：参数格式检查先于文件读取，
        仍只报用法错误，不提前报告 JSON 语法错误。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{", encoding="utf-8")
        before = broken.read_bytes()
        result = self.assert_usage_error([broken, "--node"], input_path=broken)
        stderr = result.stderr.decode("utf-8")
        self.assertNotIn(
            "JSON 语法错误", stderr,
            "参数格式错误应先于文件读取，不应出现 JSON 语法错误",
        )
        self.assertEqual(
            broken.read_bytes(), before,
            "语法错误文件在执行后发生变化",
        )


class TestInspectSuccessControls(InspectArgsTestCase):
    """成功对照：省略/显式 --node 均正常查看 start 节点。"""

    def test_omit_node_inspects_start(self):
        """省略 --node 时查看 start 指定的节点。"""
        self.assert_success_start([self.sample_copy])

    def test_explicit_node_start_inspects_start(self):
        """显式 --node start 与省略 --node 结果相同。"""
        self.assert_success_start([self.sample_copy, "--node", "start"])


if __name__ == "__main__":
    unittest.main()
