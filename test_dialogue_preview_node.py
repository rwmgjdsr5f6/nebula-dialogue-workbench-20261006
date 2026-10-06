# -*- coding: utf-8 -*-
"""dialogue.py 指定出发节点（preview --node）单步预览命令行回归测试。

以仓库 sample.json 为底，在临时副本末尾追加任何节点都不指向的 side
节点，通过公共 preview 命令行入口核对：

- --node side 指定不可达节点出发的成功输出（含 --node/--choice 顺序互换）；
- 显式 --node start 与省略 --node 等价；
- side 只有一个指向自身的选项时，循环引用仍只预览一步；
- 节点不存在、出发节点无有效选项、编号越界、非整数编号等失败边界；
- 整份文件校验失败优先于 --node 预览（即使选中分支与错误无关）。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：真实退出码、标准输出、标准错误，以及输入文件在每次调用
前后字节不变。所有派生样例独立写入临时目录并自动清理，sample.json
始终保持原样，用例可重复运行且结果一致。
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

# 省略 --node 时的哨兵（节点编号本身可能是任意非空字符串，不能用 None 代替）。
_OMITTED = object()

SIDE_TEXT = "旁路入口"


def side_node(options):
    """构造编号为 side、文字为旁路入口的节点，选项由调用方给定。"""
    return {"id": "side", "text": SIDE_TEXT, "options": options}


SIDE_TWO_OPTIONS = side_node(
    [
        {"text": "走向森林", "target": "forest"},
        {"text": "走向河边", "target": "river"},
    ]
)


def run_preview(path, choice, node=_OMITTED, node_first=False):
    """以命令行方式执行 preview，返回 CompletedProcess（不抛异常）。

    node 为 _OMITTED 时省略 --node；node_first 为 True 时把 --node
    键值对放在 --choice 之前，用于核对两对参数顺序可互换。
    """
    cmd = [sys.executable, str(DIALOGUE), "preview", str(path)]
    node_pair = [] if node is _OMITTED else ["--node", str(node)]
    choice_pair = ["--choice", str(choice)]
    cmd += (node_pair + choice_pair) if node_first else (choice_pair + node_pair)
    return subprocess.run(cmd, capture_output=True)


class PreviewNodeTestCase(unittest.TestCase):
    """公共断言：临时样例写入与清理、文件字节不变、无调用栈。"""

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

    def make_side_sample(self, node=SIDE_TWO_OPTIONS):
        """在 sample.json 副本末尾追加 side 节点（默认两选项指向 forest、river）。

        原有节点均不指向 side，因此 side 从起点不可达。
        """
        data = self.load_sample_data()
        data["nodes"].append(json.loads(json.dumps(node)))
        self.assert_unreachable(data, "side")
        return self.make_sample(data)

    def assert_unreachable(self, data, node_id):
        """按 options.target 从 start 遍历，断言 node_id 不可达。"""
        links = {
            n["id"]: [option["target"] for option in n["options"]]
            for n in data["nodes"]
        }
        seen = set()
        pending = [data["start"]]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            pending.extend(links.get(current, []))
        self.assertNotIn(node_id, seen, "构造的样例中 %r 应不可达" % node_id)

    def assert_file_unchanged(self, path, before):
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )

    def assert_no_traceback(self, stderr):
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")

    def run_and_assert_ok(
        self, path, choice, expected_stdout, node=_OMITTED, node_first=False
    ):
        """成功：退出码 0、标准错误为空、标准输出仅为目标文字加一个换行。"""
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

    def run_and_assert_fail(
        self, path, choice, expected_parts, node=_OMITTED, node_first=False
    ):
        """失败：退出码 2、标准输出为空、标准错误含各关键片段且无调用栈。"""
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


class TestPreviewFromNodeSuccess(PreviewNodeTestCase):
    """--node 指定出发节点的成功路径。"""

    def test_side_choice_2_outputs_river_text(self):
        """命令字面对应 preview <副本> --node side --choice 2：只输出河边文字。"""
        path = self.make_side_sample()
        self.run_and_assert_ok(
            path, 2, "你到了河边。\n", node="side", node_first=True
        )

    def test_side_choice_1_outputs_forest_text(self):
        """side 的第一个选项按顺序指向 forest：输出森林文字。"""
        path = self.make_side_sample()
        self.run_and_assert_ok(
            path, 1, "你到了森林。\n", node="side", node_first=True
        )

    def test_node_and_choice_pairs_order_interchangeable(self):
        """交换 --node 与 --choice 两对参数的顺序，结果逐项相同。"""
        path = self.make_side_sample()
        for choice, expected in ((1, "你到了森林。\n"), (2, "你到了河边。\n")):
            before = path.read_bytes()
            node_first = run_preview(
                path, choice, node="side", node_first=True
            )
            self.assert_file_unchanged(path, before)
            before = path.read_bytes()
            choice_first = run_preview(
                path, choice, node="side", node_first=False
            )
            self.assert_file_unchanged(path, before)
            self.assertEqual(choice_first.returncode, 0)
            self.assertEqual(node_first.returncode, choice_first.returncode)
            self.assertEqual(node_first.stdout, choice_first.stdout)
            self.assertEqual(node_first.stderr, choice_first.stderr)
            self.assertEqual(choice_first.stdout.decode("utf-8"), expected)
            self.assertEqual(choice_first.stderr, b"")

    def test_explicit_start_equals_omitted_node(self):
        """显式 --node start 与省略 --node 的退出码及两路输出完全一致。"""
        path = self.make_side_sample()
        for choice in (1, 2):
            before = path.read_bytes()
            omitted = run_preview(path, choice)
            self.assert_file_unchanged(path, before)
            before = path.read_bytes()
            explicit = run_preview(
                path, choice, node="start", node_first=True
            )
            self.assert_file_unchanged(path, before)
            self.assertEqual(explicit.returncode, omitted.returncode)
            self.assertEqual(explicit.stdout, omitted.stdout)
            self.assertEqual(explicit.stderr, omitted.stderr)

    def test_unreachable_self_loop_side_previews_one_step(self):
        """side 仅有一个指向自身的选项：不可达节点可出发，循环只预览一步。"""
        path = self.make_side_sample(
            side_node([{"text": "绕回旁路", "target": "side"}])
        )
        self.run_and_assert_ok(
            path, 1, SIDE_TEXT + "\n", node="side", node_first=True
        )


class TestPreviewFromNodeFailure(PreviewNodeTestCase):
    """--node 指定出发节点的失败边界：退出码 2、无输出、无调用栈。"""

    def test_nonexistent_node_reported(self):
        """指定不存在的 missing：退出码 2，说明该编号节点不存在。"""
        path = self.make_side_sample()
        self.run_and_assert_fail(
            path,
            1,
            ["missing", "不存在", "节点"],
            node="missing",
            node_first=True,
        )

    def test_terminal_origin_node_has_no_valid_options(self):
        """forest 没有选项却选择 1：说明该出发节点没有有效选项。"""
        path = self.make_side_sample()
        self.run_and_assert_fail(
            path,
            1,
            ["forest", "没有有效选项"],
            node="forest",
            node_first=True,
        )

    def test_side_choice_zero_out_of_range(self):
        """side 有两个选项时编号 0：报告 side、所选编号与有效范围 1 到 2。"""
        path = self.make_side_sample()
        self.run_and_assert_fail(
            path,
            0,
            ["side", "--choice 0", "1 到 2"],
            node="side",
            node_first=True,
        )

    def test_side_choice_three_out_of_range(self):
        """side 有两个选项时编号 3：报告 side、所选编号与有效范围 1 到 2。"""
        path = self.make_side_sample()
        self.run_and_assert_fail(
            path,
            3,
            ["side", "--choice 3", "1 到 2"],
            node="side",
            node_first=True,
        )

    def test_non_integer_choice_reports_origin_and_raw_value(self):
        """abc 无法解析为整数：报告原值、出发节点 side 与解析失败说明。"""
        path = self.make_side_sample()
        self.run_and_assert_fail(
            path,
            "abc",
            ["'abc'", "side", "无法解析为整数"],
            node="side",
            node_first=True,
        )

    def test_validation_failure_precedes_node_preview(self):
        """起点第二选项 target 改为 missing：即使从 side 出发也先报校验失败。

        标准输出为空（不输出 side 选项指向的森林文字），错误定位到
        nodes[0].options[1].target 并点名 missing。
        """
        data = self.load_sample_data()
        data["nodes"][0]["options"][1]["target"] = "missing"
        data["nodes"].append(json.loads(json.dumps(SIDE_TWO_OPTIONS)))
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path,
            1,
            ["校验失败", "nodes[0].options[1].target", "missing"],
            node="side",
            node_first=True,
        )
        self.assertNotIn("森林", result.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
