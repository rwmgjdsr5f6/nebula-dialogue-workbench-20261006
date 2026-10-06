# -*- coding: utf-8 -*-
"""dialogue.py 只读节点查看（inspect [--node]）命令行回归测试。

以 sample.json 为基础派生临时副本：在末尾追加编号为 side、文字为
"旁路入口" 的不可达合法节点，覆盖默认查看 start、显式查看任意节点
（含不可达节点与结尾节点）、选项编号从 1 连续编号、额外字段不进入结果、
中文/空字符串/换行/前后空格经 JSON 解析后保持原值、循环引用不递归展开，
以及节点不存在、整份校验先于查看、文件读取错误与用法错误边界。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出、标准错误，以及输入文件在执行前后字节不变。
所有派生样例由测试独立写入临时目录并自动清理，sample.json 保持原样，
用例可重复运行且结果一致。
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


def run_inspect(path, args):
    """以命令行方式执行 inspect，args 为文件路径之后的完整参数列表。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "inspect", str(path)] + list(args),
        capture_output=True,
    )


class InspectTestCase(unittest.TestCase):
    """公共断言：派生样例、文件字节不变、无调用栈、临时目录清理。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def load_sample_data(self):
        """深拷贝样例数据，派生用例之间互不影响。"""
        return json.loads(SAMPLE.read_text(encoding="utf-8"))

    def make_sample(self, data, name="case.json"):
        """把数据写成独立的临时 UTF-8 JSON 样例文件，返回路径。"""
        path = self.tmp_dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def make_side_sample(self, node=None, name="case.json"):
        """在 sample.json 末尾追加不可达节点（默认 side），返回临时副本路径。"""
        data = self.load_sample_data()
        if node is None:
            node = {
                "id": "side",
                "text": "旁路入口",
                "options": [{"text": "拐进森林", "target": "forest"}],
            }
        data["nodes"].append(node)
        return self.make_sample(data, name)

    def assert_file_unchanged(self, path, before):
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )

    def assert_no_traceback(self, stderr):
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")

    def run_and_assert_ok(self, path, args=()):
        """成功路径公共断言，返回解析后的 JSON 对象。"""
        before = path.read_bytes()
        result = run_inspect(path, args)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        stdout = result.stdout.decode("utf-8")
        self.assertTrue(stdout.endswith("\n"), "标准输出应以一个换行结尾")
        self.assertNotIn("\n", stdout[:-1], "标准输出应只有一行 JSON")
        return json.loads(stdout)

    def run_and_assert_fail(self, path, args, expected_parts):
        """失败路径公共断言：退出码 2、标准输出为空、标准错误无调用栈。"""
        before = path.read_bytes()
        result = run_inspect(path, args)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestInspectSuccess(InspectTestCase):
    """查看成功：退出码 0、标准错误为空、输出仅一个单行 JSON 对象加换行。"""

    def test_default_inspects_start_node(self):
        """省略 --node 时查看 start 指定的岔路口节点，选项从 1 连续编号。"""
        path = self.make_sample(self.load_sample_data())
        obj = self.run_and_assert_ok(path)
        self.assertEqual(
            obj,
            {
                "id": "start",
                "text": "你来到岔路口。",
                "options": [
                    {"choice": 1, "text": "向左走", "target": "forest"},
                    {"choice": 2, "text": "向右走", "target": "river"},
                ],
            },
        )

    def test_ending_node_has_empty_options(self):
        """--node forest 查看结尾节点：成功且 options 为空数组。"""
        path = self.make_sample(self.load_sample_data())
        obj = self.run_and_assert_ok(path, ["--node", "forest"])
        self.assertEqual(
            obj, {"id": "forest", "text": "你到了森林。", "options": []}
        )

    def test_unreachable_node_is_inspectable(self):
        """不可达的合法节点 side 也能查看，结果只含该节点自身信息。"""
        path = self.make_side_sample()
        obj = self.run_and_assert_ok(path, ["--node", "side"])
        self.assertEqual(
            obj,
            {
                "id": "side",
                "text": "旁路入口",
                "options": [{"choice": 1, "text": "拐进森林", "target": "forest"}],
            },
        )

    def test_explicit_start_matches_omitted_node(self):
        """显式 --node start 的结果应与省略 --node 完全一致。"""
        path = self.make_side_sample()
        before = path.read_bytes()
        explicit = run_inspect(path, ["--node", "start"])
        omitted = run_inspect(path, [])
        self.assert_file_unchanged(path, before)
        self.assertEqual(explicit.returncode, 0)
        self.assertEqual(explicit.stdout, omitted.stdout)
        self.assertEqual(explicit.stderr, omitted.stderr)

    def test_extra_fields_not_in_result(self):
        """输入中的额外字段被允许，但不加入查看结果。"""
        data = self.load_sample_data()
        data["title"] = "额外标题"
        data["nodes"][0]["note"] = "节点备注"
        data["nodes"][0]["options"][0]["weight"] = 3
        path = self.make_sample(data)
        obj = self.run_and_assert_ok(path)
        self.assertEqual(set(obj), {"id", "text", "options"})
        for option in obj["options"]:
            self.assertEqual(set(option), {"choice", "text", "target"})

    def test_text_values_preserved_through_json(self):
        """中文、空字符串、换行与前后空格经 JSON 解析后保持原值。"""
        node = {
            "id": "side",
            "text": "  第一行\n第二行  ",
            "options": [
                {"text": "", "target": "forest"},
                {"text": " 带空格 ", "target": "river"},
            ],
        }
        path = self.make_side_sample(node=node)
        obj = self.run_and_assert_ok(path, ["--node", "side"])
        self.assertEqual(obj["text"], "  第一行\n第二行  ")
        self.assertEqual(
            obj["options"],
            [
                {"choice": 1, "text": "", "target": "forest"},
                {"choice": 2, "text": " 带空格 ", "target": "river"},
            ],
        )

    def test_self_loop_not_expanded(self):
        """循环引用仍合法：自引用节点只输出自身信息，不递归展开。"""
        node = {
            "id": "side",
            "text": "旁路入口",
            "options": [{"text": "原地停留", "target": "side"}],
        }
        path = self.make_side_sample(node=node)
        obj = self.run_and_assert_ok(path, ["--node", "side"])
        self.assertEqual(
            obj,
            {
                "id": "side",
                "text": "旁路入口",
                "options": [{"choice": 1, "text": "原地停留", "target": "side"}],
            },
        )


class TestInspectFailure(InspectTestCase):
    """查看失败：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_node_reports_not_found(self):
        """文件合法但节点不存在：标准错误说明节点不存在并包含请求编号。"""
        path = self.make_side_sample()
        self.run_and_assert_fail(path, ["--node", "missing"], ["missing", "不存在"])

    def test_node_id_matches_exactly(self):
        """节点编号按完整字符串精确匹配，不裁剪空白、不忽略大小写。"""
        path = self.make_side_sample()
        self.run_and_assert_fail(path, ["--node", "Forest"], ["Forest", "不存在"])
        self.run_and_assert_fail(path, ["--node", " forest"], ["forest", "不存在"])

    def test_validation_failure_precedes_inspect(self):
        """不可达节点缺字段时先报告校验失败，不输出局部查看结果。"""
        data = self.load_sample_data()
        node = {"id": "side", "options": []}
        data["nodes"].append(node)
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, ["--node", "side"], ["校验失败", "nodes[3].text"]
        )

    def test_dangling_reference_precedes_inspect(self):
        """不可达节点选项悬空引用时先报告校验失败，即使所查节点本身合法。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {
                "id": "side",
                "text": "旁路入口",
                "options": [{"text": "去", "target": "ghost"}],
            }
        )
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path, [], ["校验失败", "nodes[3].options[0].target", "ghost"]
        )
        self.assertNotIn(
            "岔路口".encode("utf-8"),
            result.stdout,
            "校验失败时不应输出任何节点信息",
        )

    def test_unknown_node_still_reports_file_error_first(self):
        """同时存在未知查看编号与文件结构错误时，仍先报告文件错误。"""
        data = self.load_sample_data()
        data["start"] = "ghost"
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, ["--node", "missing"], ["校验失败", "start", "ghost"]
        )

    def test_unreadable_path(self):
        """路径不可读沿用既有文件错误类别；执行后不创建该文件。"""
        path = self.tmp_dir / "no_such_file.json"
        result = run_inspect(path, [])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(path), stderr)
        self.assertFalse(path.exists(), "失败后不应创建该文件")

    def test_utf8_decode_failure(self):
        """UTF-8 解码失败沿用既有文件错误类别。"""
        path = self.tmp_dir / "bad_bytes.json"
        path.write_bytes(b"\xff")
        before = path.read_bytes()
        result = run_inspect(path, [])
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("UTF-8 解码失败", stderr)

    def test_json_syntax_error(self):
        """JSON 语法错误沿用既有错误类别与行列定位。"""
        path = self.tmp_dir / "bad_syntax.json"
        path.write_text("{\n!\n}\n", encoding="utf-8")
        before = path.read_bytes()
        result = run_inspect(path, [])
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("JSON 语法错误", stderr)
        self.assertIn("第 2 行第 1 列", stderr)


class TestInspectUsage(InspectTestCase):
    """用法错误：退出码 2、标准输出为空、标准错误含 inspect 用法说明，
    且在读取文件前结束（用不存在的路径佐证不进入文件读取阶段）。"""

    def run_usage_fail(self, argv):
        missing = self.tmp_dir / "no_such_file.json"
        args = [arg if arg != "{path}" else str(missing) for arg in argv]
        result = subprocess.run(
            [sys.executable, str(DIALOGUE), "inspect"] + args,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2, "用法错误时退出码应为 2")
        self.assertEqual(result.stdout, b"", "用法错误时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("inspect", stderr, "用法说明应包含 inspect")
        self.assertNotIn("无法读取文件", stderr, "用法错误应先于文件读取")
        self.assertFalse(missing.exists(), "失败后不应创建该文件")

    def test_missing_path(self):
        self.run_usage_fail([])

    def test_node_missing_value(self):
        self.run_usage_fail(["{path}", "--node"])

    def test_duplicate_node(self):
        self.run_usage_fail(["{path}", "--node", "a", "--node", "b"])

    def test_extra_argument(self):
        self.run_usage_fail(["{path}", "extra"])

    def test_unknown_option(self):
        self.run_usage_fail(["{path}", "--choice", "1"])


if __name__ == "__main__":
    unittest.main()
