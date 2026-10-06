# -*- coding: utf-8 -*-
"""dialogue.py 只读节点查看（inspect）命令行回归测试。

以 sample.json 为基础派生临时副本，覆盖省略 --node 与显式 --node start
的等价路径、起点选项顺序与交换后的编号、结尾节点的空选项、不可达
自引用节点的单次查看，以及节点不存在、整份校验先于查看的失败边界。

成功输出按解析后的 JSON 对象核对完整内容（id、text、options，选项
保持输入数组顺序、choice 从 1 连续编号），并单独核对结尾换行，
不依赖对象键顺序或空格排版。

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


def run_inspect(path, node=None):
    """以命令行方式执行 inspect；node 为 None 时省略 --node。"""
    args = [sys.executable, str(DIALOGUE), "inspect", str(path)]
    if node is not None:
        args.extend(["--node", node])
    return subprocess.run(args, capture_output=True)


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

    def make_side_sample(self, name="case.json"):
        """在 sample.json 末尾追加不可达的 side 节点（文字“岔路旁”，
        唯一选项指向自身），返回临时副本路径。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {
                "id": "side",
                "text": "岔路旁",
                "options": [{"text": "原地停留", "target": "side"}],
            }
        )
        return self.make_sample(data, name)

    def make_unused_sample(self, name="case.json"):
        """在 sample.json 末尾追加缺少 text 的不可达节点 unused，
        使整份校验在 nodes[3].text 处失败，返回临时副本路径。"""
        data = self.load_sample_data()
        data["nodes"].append({"id": "unused", "options": []})
        return self.make_sample(data, name)

    def assert_file_unchanged(self, path, before):
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )

    def assert_no_traceback(self, stderr):
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")

    def run_and_assert_ok(self, path, expected, node=None):
        """成功路径：退出码 0、标准错误为空、标准输出为一个 JSON 对象
        加一个结尾换行；对象内容按解析结果整体核对，不依赖键序或排版。"""
        before = path.read_bytes()
        result = run_inspect(path, node=node)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        stdout = result.stdout.decode("utf-8")
        self.assertTrue(
            stdout.endswith("\n"), "标准输出应以一个换行结尾：{!r}".format(stdout)
        )
        payload = stdout[:-1]
        self.assertNotIn("\n", payload, "标准输出应只有一行 JSON")
        actual = json.loads(payload)
        self.assertEqual(actual, expected, "输出的 JSON 对象内容不符")
        return result

    def run_and_assert_fail(self, path, expected_parts, node=None,
                            unexpected_parts=()):
        """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""
        before = path.read_bytes()
        result = run_inspect(path, node=node)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        for part in unexpected_parts:
            self.assertNotIn(part, stderr, "标准错误不应包含 {!r}".format(part))
        return result


# 起点节点的完整期望输出：选项保持输入数组顺序，choice 从 1 连续编号。
EXPECTED_START = {
    "id": "start",
    "text": "你来到岔路口。",
    "options": [
        {"choice": 1, "text": "向左走", "target": "forest"},
        {"choice": 2, "text": "向右走", "target": "river"},
    ],
}


class TestInspectSuccess(InspectTestCase):
    """成功路径：退出码 0、标准错误为空、输出为 JSON 对象加结尾换行。"""

    def test_omit_node_returns_start_node(self):
        path = self.make_sample(self.load_sample_data())
        self.run_and_assert_ok(path, EXPECTED_START)

    def test_explicit_start_node_matches_omitted_node(self):
        """显式 --node start 的结果应与省略 --node 完全一致。"""
        path = self.make_sample(self.load_sample_data())
        explicit = self.run_and_assert_ok(path, EXPECTED_START, node="start")
        omitted = self.run_and_assert_ok(path, EXPECTED_START)
        self.assertEqual(explicit.stdout, omitted.stdout)
        self.assertEqual(explicit.stderr, omitted.stderr)
        self.assertEqual(explicit.returncode, omitted.returncode)

    def test_swapped_start_options_renumber_choices(self):
        """交换起点两个选项后，choice 1 应对应 river，编号仍从 1 连续。"""
        data = self.load_sample_data()
        options = data["nodes"][0]["options"]
        options[0], options[1] = options[1], options[0]
        path = self.make_sample(data)
        self.run_and_assert_ok(
            path,
            {
                "id": "start",
                "text": "你来到岔路口。",
                "options": [
                    {"choice": 1, "text": "向右走", "target": "river"},
                    {"choice": 2, "text": "向左走", "target": "forest"},
                ],
            },
        )

    def test_ending_node_has_empty_options(self):
        """查看 forest 应返回其文字，options 为空数组。"""
        path = self.make_sample(self.load_sample_data())
        self.run_and_assert_ok(
            path,
            {"id": "forest", "text": "你到了森林。", "options": []},
            node="forest",
        )

    def test_unreachable_self_loop_node_returned_once(self):
        """不可达的 side 节点唯一选项指向自身：显式查看时只返回该节点
        一次，choice 为 1，target 为 side。"""
        path = self.make_side_sample()
        result = self.run_and_assert_ok(
            path,
            {
                "id": "side",
                "text": "岔路旁",
                "options": [{"choice": 1, "text": "原地停留", "target": "side"}],
            },
            node="side",
        )
        stdout = result.stdout.decode("utf-8")
        self.assertEqual(stdout.count("岔路旁"), 1, "节点文字应只出现一次")


class TestInspectFailure(InspectTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_node_reports_not_found(self):
        """合法副本指定 --node missing：报告节点不存在。"""
        path = self.make_sample(self.load_sample_data())
        self.run_and_assert_fail(path, ["missing", "不存在"], node="missing")

    def test_validation_failure_precedes_inspect_start(self):
        """不可达节点 unused 缺少 text：查看 start 也应先报告整份校验
        失败，不出现节点不存在提示。"""
        path = self.make_unused_sample()
        result = self.run_and_assert_fail(
            path, ["nodes[3].text"], unexpected_parts=["不存在"]
        )
        stderr = result.stderr.decode("utf-8")
        self.assertTrue(
            stderr.startswith("校验失败："),
            "标准错误应以“校验失败：”开头：{!r}".format(stderr),
        )

    def test_validation_failure_precedes_inspect_missing(self):
        """同一份坏数据查看 missing：整份校验失败同样先于节点查找。"""
        path = self.make_unused_sample()
        result = self.run_and_assert_fail(
            path, ["nodes[3].text"], node="missing",
            unexpected_parts=["不存在"],
        )
        stderr = result.stderr.decode("utf-8")
        self.assertTrue(
            stderr.startswith("校验失败："),
            "标准错误应以“校验失败：”开头：{!r}".format(stderr),
        )


if __name__ == "__main__":
    unittest.main()
