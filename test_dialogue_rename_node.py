# -*- coding: utf-8 -*-
"""dialogue.py rename-node 命令回归测试。

固定 rename-node 的行为：只接受
``python dialogue.py rename-node <文件路径> --node <旧编号> --to <新编号>``
这一固定参数顺序；参数缺失、重复、多余、连写、顺序错误或文件路径以减号
开头时，在读取文件前以退出码 2 拒绝，标准错误仅为上述命令形式原文加
一个换行。合法参数下先完成文件读取、UTF-8 解码、JSON 解析与整份结构
和引用校验（不可达节点中的错误也先于重命名报出），随后依次检查旧节点
存在、新编号非空白、编号冲突。成功时退出码 0、标准错误为空、标准输出
仅为修改后完整对话对象的单行 JSON 加一个结尾换行，中文不转义；输入
文件字节保持不变，不创建结果文件。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

合法对话使用 sample.json 的临时字节副本或在临时目录独立写入的派生样例，
样例原件与业务源码保持原样；每次调用前后核对输入文件字节不变，
临时数据结束后清理。
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

# rename-node 参数错误专用的单行用法文字（fail() 会在末尾补一个换行）。
# 在此硬编码以固定现有文案；与其余七条命令的用法文字互不影响。
RENAME_NODE_USAGE_TEXT = (
    "python dialogue.py rename-node <文件路径> --node <旧编号> --to <新编号>\n"
)

# sample.json 把 forest 改名为 grove 后的完整对话对象（按解析后的 JSON 核对）。
EXPECTED_GROVE = {
    "start": "start",
    "nodes": [
        {
            "id": "start",
            "text": "你来到岔路口。",
            "options": [
                {"text": "向左走", "target": "grove"},
                {"text": "向右走", "target": "river"},
            ],
        },
        {"id": "grove", "text": "你到了森林。", "options": []},
        {"id": "river", "text": "你到了河边。", "options": []},
    ],
}


class RenameNodeTestCase(unittest.TestCase):
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

    def write_dialogue(self, name, data):
        """在临时目录写入一份派生对话，返回路径。"""
        path = self.tmp_dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def run_rename(self, rest):
        """执行 rename-node，rest 为文件路径位置开始的完整参数列表。"""
        argv = [sys.executable, str(DIALOGUE), "rename-node"] + [
            str(a) for a in rest
        ]
        return subprocess.run(argv, capture_output=True)

    def describe(self, rest):
        return " ".join(str(a) for a in rest)

    def assert_usage_error(self, rest, input_path=None):
        """格式错误：退出码 2、stdout 为空、stderr 仅为单行用法加换行。"""
        if input_path is not None:
            before = input_path.read_bytes()
        result = self.run_rename(rest)
        label = "参数：rename-node {}".format(self.describe(rest))
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
            stderr, RENAME_NODE_USAGE_TEXT,
            "{}：标准错误应仅为单行用法加末尾换行，实际 {!r}".format(
                label, stderr),
        )
        self.assertNotIn(
            "Traceback", stderr,
            "{}：标准错误不应包含调用栈".format(label),
        )
        if input_path is not None:
            self.assertEqual(
                input_path.read_bytes(), before,
                "{}：输入文件在执行后发生变化".format(label),
            )
        return result

    def assert_failure(self, rest, expected_stderr, input_path):
        """语义失败：退出码 2、stdout 为空、stderr 为指定说明加换行。"""
        before = input_path.read_bytes()
        result = self.run_rename(rest)
        label = "参数：rename-node {}".format(self.describe(rest))
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
        self.assertEqual(
            stderr, expected_stderr + "\n",
            "{}：标准错误应为 {!r}，实际 {!r}".format(
                label, expected_stderr + "\n", stderr),
        )
        self.assertNotIn(
            "Traceback", stderr,
            "{}：标准错误不应包含调用栈".format(label),
        )
        self.assertEqual(
            input_path.read_bytes(), before,
            "{}：输入文件在执行后发生变化".format(label),
        )
        return result

    def assert_success(self, rest, expected_object, input_path):
        """成功：退出码 0、stderr 为空、stdout 为单行 JSON 加换行。"""
        before = input_path.read_bytes()
        result = self.run_rename(rest)
        label = "参数：rename-node {}".format(self.describe(rest))
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
            input_path.read_bytes(), before,
            "{}：输入文件在执行后发生变化".format(label),
        )
        return result


class TestRenameNodeUsageErrors(RenameNodeTestCase):
    """rename-node 参数格式错误：一律只输出单行用法，退出码 2。"""

    def test_missing_file_path(self):
        """缺少文件路径：只有 rename-node 本身。"""
        self.assert_usage_error([])

    def test_missing_node_option(self):
        """只有文件路径、没有 --node 与 --to。"""
        self.assert_usage_error([self.sample_copy],
                                input_path=self.sample_copy)

    def test_missing_to_option(self):
        """有 --node 旧编号、没有 --to。"""
        self.assert_usage_error([self.sample_copy, "--node", "forest"],
                                input_path=self.sample_copy)

    def test_missing_to_value(self):
        """--to 之后缺少新编号。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "forest", "--to"],
            input_path=self.sample_copy,
        )

    def test_duplicate_node_option(self):
        """--node 出现两次：重复参数被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "forest", "--node", "river",
             "--to", "grove"],
            input_path=self.sample_copy,
        )

    def test_duplicate_to_option(self):
        """--to 出现两次：重复参数被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "forest", "--to", "grove",
             "--to", "hill"],
            input_path=self.sample_copy,
        )

    def test_unknown_option_rejected(self):
        """未知选项 --verbose 被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "forest", "--to", "grove",
             "--verbose"],
            input_path=self.sample_copy,
        )

    def test_extra_positional_argument(self):
        """合法参数之后出现额外位置参数。"""
        self.assert_usage_error(
            [self.sample_copy, "--node", "forest", "--to", "grove", "extra"],
            input_path=self.sample_copy,
        )

    def test_equals_form_rejected(self):
        """--node=forest 与 --to=grove 连写形式被拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--node=forest", "--to=grove"],
            input_path=self.sample_copy,
        )

    def test_swapped_option_order_rejected(self):
        """--to 在 --node 之前不符合固定顺序，也在读取文件前拒绝。"""
        self.assert_usage_error(
            [self.sample_copy, "--to", "grove", "--node", "forest"],
            input_path=self.sample_copy,
        )

    def test_options_before_path_rejected(self):
        """--node/--to 出现在路径之前不符合固定顺序。"""
        self.assert_usage_error(
            ["--node", "forest", "--to", "grove", self.sample_copy],
            input_path=self.sample_copy,
        )

    def test_option_like_path_rejected(self):
        """路径位置是形似选项的记号：不得把它当路径读取。"""
        result = self.assert_usage_error(
            ["--node", "forest", "--to", "grove", "--node", "x"]
        )
        self.assertNotIn(
            "无法读取文件", result.stderr.decode("utf-8"),
            "形似选项的记号不应触发文件读取",
        )

    def test_bare_dash_not_treated_as_path(self):
        """孤立的“-”也属于形似选项记号，按用法错误拒绝，不读取文件。"""
        self.assert_usage_error(["-", "--node", "forest", "--to", "grove"])

    def test_missing_value_with_nonexistent_path_still_usage_error(self):
        """缺少新编号 + 不存在的路径：参数格式检查先于文件读取，
        仍只报同一用法错误，不变成无法读取文件，也不创建该路径。"""
        missing = self.tmp_dir / "never_created.json"
        self.assertFalse(missing.exists(), "前置条件：路径尚不存在")
        result = self.assert_usage_error([missing, "--node", "forest", "--to"])
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
            [broken, "--node", "forest", "--to", "grove", "extra"],
            input_path=broken,
        )
        self.assertNotIn(
            "JSON 语法错误", result.stderr.decode("utf-8"),
            "参数格式错误应先于文件读取，不应出现 JSON 语法错误",
        )
        self.assertEqual(
            broken.read_bytes(), before, "语法错误文件在执行后发生变化"
        )


class TestRenameNodeSuccess(RenameNodeTestCase):
    """成功重命名：完整对话对象以单行 JSON 输出，输入文件不变。"""

    def test_sample_rename_forest_to_grove(self):
        """验收用例：forest 改名为 grove，起点第一项 target 同步更新。"""
        result = self.assert_success(
            [self.sample_copy, "--node", "forest", "--to", "grove"],
            EXPECTED_GROVE,
            self.sample_copy,
        )
        stdout = result.stdout.decode("utf-8")
        self.assertIn("你到了森林。", stdout, "中文不应被转义")
        self.assertNotIn("\\u", stdout, "中文不应以 \\u 转义形式输出")

    def test_rename_start_node_updates_start(self):
        """旧编号等于 start 时 start 字段同步更新。"""
        expected = {
            "start": "gate",
            "nodes": [
                {
                    "id": "gate",
                    "text": "你来到岔路口。",
                    "options": [
                        {"text": "向左走", "target": "forest"},
                        {"text": "向右走", "target": "river"},
                    ],
                },
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        }
        self.assert_success(
            [self.sample_copy, "--node", "start", "--to", "gate"],
            expected,
            self.sample_copy,
        )

    def test_same_old_and_new_outputs_equivalent_object(self):
        """新旧编号完全相同：成功输出与原对象等价的 JSON。"""
        self.assert_success(
            [self.sample_copy, "--node", "forest", "--to", "forest"],
            json.loads(SAMPLE.read_text(encoding="utf-8")),
            self.sample_copy,
        )

    def test_option_like_values_accepted(self):
        """编号值形似选项（如 -x）照收为编号，按节点不存在处理而非用法错误。"""
        result = self.run_rename(
            [self.sample_copy, "--node", "-x", "--to", "grove"]
        )
        self.assertEqual(result.returncode, 2, "节点不存在时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assertNotEqual(
            stderr, RENAME_NODE_USAGE_TEXT,
            "形似选项的编号值应照收，不应报用法错误",
        )
        self.assertIn("文件中不存在编号为 '-x' 的节点", stderr)

    def test_whitespace_preserved_in_ids(self):
        """编号按原字符串精确匹配，首尾空白不裁剪。"""
        data = {
            "start": " a",
            "nodes": [
                {"id": " a", "text": "起点", "options": [
                    {"text": "走", "target": "b "},
                ]},
                {"id": "b ", "text": "终点", "options": []},
            ],
        }
        path = self.write_dialogue("whitespace.json", data)
        expected = {
            "start": " a",
            "nodes": [
                {"id": " a", "text": "起点", "options": [
                    {"text": "走", "target": "c"},
                ]},
                {"id": "c", "text": "终点", "options": []},
            ],
        }
        self.assert_success(
            [path, "--node", "b ", "--to", "c"], expected, path
        )

    def test_unreachable_duplicate_self_and_cycle_references_updated(self):
        """不可达来源、多个选项重复引用、自引用与循环中的引用全部更新。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "去 a", "target": "a"},
                    {"text": "结束", "target": "e"},
                ]},
                {"id": "a", "text": "甲", "options": [
                    {"text": "自转", "target": "a"},
                    {"text": "去乙", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "回甲", "target": "a"},
                ]},
                {"id": "e", "text": "结尾", "options": []},
                {"id": "side", "text": "旁路", "options": [
                    {"text": "也去甲", "target": "a"},
                    {"text": "还去甲", "target": "a"},
                ]},
            ],
        }
        path = self.write_dialogue("cycle.json", data)
        expected = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "去 a", "target": "z"},
                    {"text": "结束", "target": "e"},
                ]},
                {"id": "z", "text": "甲", "options": [
                    {"text": "自转", "target": "z"},
                    {"text": "去乙", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "回甲", "target": "z"},
                ]},
                {"id": "e", "text": "结尾", "options": []},
                {"id": "side", "text": "旁路", "options": [
                    {"text": "也去甲", "target": "z"},
                    {"text": "还去甲", "target": "z"},
                ]},
            ],
        }
        self.assert_success(
            [path, "--node", "a", "--to", "z"], expected, path
        )

    def test_other_fields_with_equal_values_not_replaced(self):
        """text 与额外字段的值碰巧等于旧编号时保持原样，不被替换。"""
        data = {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "a", "note": "a", "options": [
                    {"text": "a", "target": "b", "tag": "a"},
                ]},
                {"id": "b", "text": "终点", "options": []},
            ],
            "extra": "a",
        }
        path = self.write_dialogue("extra.json", data)
        expected = {
            "start": "c",
            "nodes": [
                {"id": "c", "text": "a", "note": "a", "options": [
                    {"text": "a", "target": "b", "tag": "a"},
                ]},
                {"id": "b", "text": "终点", "options": []},
            ],
            "extra": "a",
        }
        self.assert_success(
            [path, "--node", "a", "--to", "c"], expected, path
        )


class TestRenameNodeFailures(RenameNodeTestCase):
    """语义失败：旧节点不存在、新编号为空白、新编号冲突及既有错误分类。"""

    def test_old_node_not_found(self):
        """旧编号不存在：沿用现有节点不存在说明。"""
        self.assert_failure(
            [self.sample_copy, "--node", "missing", "--to", "grove"],
            "文件中不存在编号为 'missing' 的节点",
            self.sample_copy,
        )

    def test_new_id_blank_rejected(self):
        """新编号只含空白字符：报新编号必须包含非空白字符。"""
        self.assert_failure(
            [self.sample_copy, "--node", "forest", "--to", "  "],
            "新编号必须包含非空白字符",
            self.sample_copy,
        )

    def test_new_id_empty_rejected(self):
        """新编号为空字符串同样被拒绝。"""
        self.assert_failure(
            [self.sample_copy, "--node", "forest", "--to", ""],
            "新编号必须包含非空白字符",
            self.sample_copy,
        )

    def test_new_id_conflicts_with_other_node(self):
        """验收用例：--to river 与既有节点冲突。"""
        self.assert_failure(
            [self.sample_copy, "--node", "forest", "--to", "river"],
            "新编号已被其他节点使用",
            self.sample_copy,
        )

    def test_old_node_missing_checked_before_blank_new_id(self):
        """旧节点不存在的检查先于新编号非空白检查。"""
        self.assert_failure(
            [self.sample_copy, "--node", "missing", "--to", ""],
            "文件中不存在编号为 'missing' 的节点",
            self.sample_copy,
        )

    def test_blank_new_id_checked_before_conflict(self):
        """新编号非空白的检查先于编号冲突检查。"""
        self.assert_failure(
            [self.sample_copy, "--node", "forest", "--to", " "],
            "新编号必须包含非空白字符",
            self.sample_copy,
        )

    def test_validation_error_in_unreachable_node_reported_first(self):
        """不可达节点缺字段：整份校验先于重命名检查报出。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": []},
                {"id": "side", "options": []},
            ],
        }
        path = self.write_dialogue("invalid.json", data)
        result = self.run_rename([path, "--node", "s", "--to", "grove"])
        self.assertEqual(result.returncode, 2, "校验失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assertTrue(
            stderr.startswith("校验失败："),
            "应先报整份校验失败，实际 {!r}".format(stderr),
        )
        self.assertIn("nodes[1].text", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_missing_file_reports_load_error(self):
        """路径不存在：沿用既有文件读取错误分类。"""
        missing = self.tmp_dir / "absent.json"
        result = self.run_rename([missing, "--node", "a", "--to", "b"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr = result.stderr.decode("utf-8")
        self.assertIn("无法读取文件", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertFalse(missing.exists(), "不应创建传入的不存在路径")

    def test_broken_json_reports_syntax_error(self):
        """JSON 语法错误：沿用既有语法错误分类。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{", encoding="utf-8")
        before = broken.read_bytes()
        result = self.run_rename([broken, "--node", "a", "--to", "b"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr = result.stderr.decode("utf-8")
        self.assertIn("JSON 语法错误", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertEqual(broken.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
