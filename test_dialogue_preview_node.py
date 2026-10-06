# -*- coding: utf-8 -*-
"""dialogue.py 指定出发节点（preview --node）单步预览命令行回归测试。

以 sample.json 为基础派生临时副本：在末尾追加编号为 side、文字为
"旁路入口" 的合法节点（原有节点均不指向它），覆盖从指定节点出发的
成功路径、参数顺序互换、显式指定 start、不可达节点自引用循环，
以及节点不存在、结尾节点无选项、编号越界、非整数编号、
整份校验先于预览的失败边界。

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


def run_preview_args(path, args):
    """以命令行方式执行 preview，args 为文件路径之后的完整参数列表。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "preview", str(path)] + list(args),
        capture_output=True,
    )


def run_preview(path, choice, node=None, node_first=False):
    """组装 --choice/--node 参数对；node_first 时把 --node 一对放在前面。"""
    pairs = [("--choice", str(choice))]
    if node is not None:
        pairs.append(("--node", node))
    if node_first:
        pairs.reverse()
    args = []
    for name, value in pairs:
        args.extend([name, value])
    return run_preview_args(path, args)


class PreviewNodeTestCase(unittest.TestCase):
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

    def make_side_sample(self, options=None, name="case.json"):
        """在 sample.json 末尾追加不可达的 side 节点，返回临时副本路径。"""
        data = self.load_sample_data()
        if options is None:
            options = [
                {"text": "拐进森林", "target": "forest"},
                {"text": "拐向河边", "target": "river"},
            ]
        data["nodes"].append(
            {"id": "side", "text": "旁路入口", "options": options}
        )
        return self.make_sample(data, name)

    def assert_file_unchanged(self, path, before):
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )

    def assert_no_traceback(self, stderr):
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")

    def run_and_assert_ok(self, path, choice, expected_stdout, node=None,
                          node_first=False):
        before = path.read_bytes()
        result = run_preview(path, choice, node=node, node_first=node_first)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"),
            expected_stdout,
            "标准输出应只有目标节点文字和一个结尾换行",
        )
        return result

    def run_and_assert_fail(self, path, choice, expected_parts, node=None,
                            node_first=False):
        before = path.read_bytes()
        result = run_preview(path, choice, node=node, node_first=node_first)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestPreviewNodeSuccess(PreviewNodeTestCase):
    """指定 --node 的成功路径：退出码 0、标准错误为空、输出仅目标文字加换行。"""

    def test_side_choice_2_outputs_river_text(self):
        path = self.make_side_sample()
        self.run_and_assert_ok(path, 2, "你到了河边。\n", node="side")

    def test_side_choice_1_outputs_forest_text(self):
        path = self.make_side_sample()
        self.run_and_assert_ok(path, 1, "你到了森林。\n", node="side")

    def test_node_and_choice_order_is_interchangeable(self):
        """--node 与 --choice 两对参数交换顺序，结果应一致。"""
        path = self.make_side_sample()
        self.run_and_assert_ok(path, 2, "你到了河边。\n",
                               node="side", node_first=True)
        self.run_and_assert_ok(path, 1, "你到了森林。\n",
                               node="side", node_first=True)

    def test_explicit_start_node_matches_omitted_node(self):
        """显式 --node start 的结果应与省略 --node 完全一致。"""
        path = self.make_side_sample()
        for choice, expected in ((1, "你到了森林。\n"), (2, "你到了河边。\n")):
            explicit = self.run_and_assert_ok(path, choice, expected, node="start")
            omitted = self.run_and_assert_ok(path, choice, expected)
            self.assertEqual(explicit.stdout, omitted.stdout)
            self.assertEqual(explicit.stderr, omitted.stderr)
            self.assertEqual(explicit.returncode, omitted.returncode)

    def test_unreachable_self_loop_node_steps_once(self):
        """side 仅有指向自身的一个选项：不可达节点可作出发节点，
        循环引用仍只预览一步，文字只输出一次。"""
        path = self.make_side_sample(
            options=[{"text": "原地停留", "target": "side"}]
        )
        self.run_and_assert_ok(path, 1, "旁路入口\n", node="side")


class TestPreviewNodeFailure(PreviewNodeTestCase):
    """指定 --node 的失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_node_reports_not_found(self):
        path = self.make_side_sample()
        self.run_and_assert_fail(
            path, 1, ["missing", "不存在"], node="missing"
        )

    def test_ending_node_has_no_valid_options(self):
        """从结尾节点 forest 出发选择 1，应说明该出发节点没有有效选项。"""
        path = self.make_side_sample()
        self.run_and_assert_fail(
            path, 1, ["forest", "没有有效选项"], node="forest"
        )

    def test_choice_zero_out_of_range(self):
        path = self.make_side_sample()
        self.run_and_assert_fail(
            path, 0, ["side", "--choice 0", "1 到 2"], node="side"
        )

    def test_choice_three_out_of_range(self):
        path = self.make_side_sample()
        self.run_and_assert_fail(
            path, 3, ["side", "--choice 3", "1 到 2"], node="side"
        )

    def test_choice_not_an_integer(self):
        path = self.make_side_sample()
        self.run_and_assert_fail(
            path, "abc", ["'abc'", "side", "无法解析为整数"], node="side"
        )

    def test_validation_failure_precedes_preview(self):
        """原起点第二个选项 target 改为 missing：即使从 side 出发选择 1，
        也应先报告整份校验失败，不输出任何节点文字。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][1]["target"] = "missing"
        data["nodes"].append(
            {
                "id": "side",
                "text": "旁路入口",
                "options": [
                    {"text": "拐进森林", "target": "forest"},
                    {"text": "拐向河边", "target": "river"},
                ],
            }
        )
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path, 1, ["校验失败", "nodes[0].options[1].target", "missing"],
            node="side",
        )
        self.assertNotIn(
            "森林".encode("utf-8"),
            result.stdout,
            "校验失败时不应输出森林文字",
        )


if __name__ == "__main__":
    unittest.main()
