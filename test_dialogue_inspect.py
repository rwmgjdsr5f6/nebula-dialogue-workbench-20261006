# -*- coding: utf-8 -*-
"""dialogue.py 只读节点查看（inspect）命令行回归测试。

以 sample.json 为基础派生临时副本，覆盖省略 --node 查看起点、
显式 --node start 结果一致、选项顺序与编号、交换选项后的对应关系、
结尾节点空选项、不可达自引用节点只返回一次，
以及节点不存在、整份校验先于查看的失败边界。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出（按解析后的 JSON 对象核对，另核对结尾换行）、
标准错误，以及输入文件在执行前后字节不变。所有派生样例由测试独立写入
临时目录并自动清理，sample.json 保持原样，用例可重复运行且结果一致。
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
    """以命令行方式执行 inspect；node 为 None 时省略 --node 参数。"""
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

    def make_plain_sample(self, name="case.json"):
        """sample.json 的原样临时副本。"""
        return self.make_sample(self.load_sample_data(), name)

    def make_side_sample(self, name="case.json"):
        """在 sample.json 末尾追加不可达的 side 节点（自引用），返回临时副本路径。"""
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
        """在 sample.json 末尾追加缺少 text 的不可达 unused 节点。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "unused", "options": [{"text": "回到起点", "target": "start"}]}
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

    def run_and_assert_ok(self, path, expected_object, node=None):
        """成功路径：退出码 0、标准错误为空、输出为 JSON 对象加一个结尾换行。

        对象内容按解析后的 JSON 核对，不依赖键顺序或空格排版；
        结尾换行单独核对。
        """
        before = path.read_bytes()
        result = run_inspect(path, node=node)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        stdout = result.stdout.decode("utf-8")
        self.assertTrue(
            stdout.endswith("\n"), "标准输出应以一个结尾换行结束：{!r}".format(stdout)
        )
        self.assertNotIn(
            "\n", stdout[:-1], "结尾换行之前不应再有换行：{!r}".format(stdout)
        )
        actual = json.loads(stdout[:-1])
        self.assertEqual(
            actual,
            expected_object,
            "解析后的 JSON 对象应与预期完全一致",
        )
        return result

    def run_and_assert_fail(self, path, expected_parts, node=None):
        """失败路径：退出码 2、标准输出为空、标准错误包含各片段且无调用栈。"""
        before = path.read_bytes()
        result = run_inspect(path, node=node)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestInspectSuccess(InspectTestCase):
    """成功路径：省略 --node 查看起点，显式 --node 查看指定节点。"""

    def test_omitted_node_inspects_start(self):
        """省略 --node 时返回起点：id、text、options 完整且按输入顺序编号。"""
        path = self.make_plain_sample()
        self.run_and_assert_ok(
            path,
            {
                "id": "start",
                "text": "你来到岔路口。",
                "options": [
                    {"choice": 1, "text": "向左走", "target": "forest"},
                    {"choice": 2, "text": "向右走", "target": "river"},
                ],
            },
        )

    def test_explicit_start_matches_omitted_node(self):
        """显式 --node start 的结果应与省略 --node 完全一致。"""
        path = self.make_plain_sample()
        expected = {
            "id": "start",
            "text": "你来到岔路口。",
            "options": [
                {"choice": 1, "text": "向左走", "target": "forest"},
                {"choice": 2, "text": "向右走", "target": "river"},
            ],
        }
        explicit = self.run_and_assert_ok(path, expected, node="start")
        omitted = self.run_and_assert_ok(path, expected)
        self.assertEqual(explicit.stdout, omitted.stdout)
        self.assertEqual(explicit.stderr, omitted.stderr)
        self.assertEqual(explicit.returncode, omitted.returncode)

    def test_swapped_options_renumber_choices(self):
        """交换起点两个选项后，choice 1 应对应 river，编号仍从 1 连续。"""
        data = self.load_sample_data()
        options = data["nodes"][0]["options"]
        data["nodes"][0]["options"] = [options[1], options[0]]
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
        """查看 forest：文字为"你到了森林。"，options 为空数组。"""
        path = self.make_plain_sample()
        self.run_and_assert_ok(
            path,
            {"id": "forest", "text": "你到了森林。", "options": []},
            node="forest",
        )

    def test_unreachable_self_loop_node_inspected_once(self):
        """不可达的 side 节点（唯一选项指向自身）：只返回该节点一次，
        choice 为 1，target 为 side。"""
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
        self.assertEqual(
            stdout.count("岔路旁"), 1, "side 节点的文字应只出现一次"
        )


class TestInspectFailure(InspectTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_node_reports_not_found(self):
        """合法副本指定 --node missing：报告节点不存在。"""
        path = self.make_plain_sample()
        self.run_and_assert_fail(path, ["missing", "不存在"], node="missing")

    def test_validation_failure_precedes_inspect_start(self):
        """末尾追加缺少 text 的不可达 unused 节点：查看 start 也应
        先报告整份校验失败，不出现节点不存在提示。"""
        path = self.make_unused_sample()
        result = self.run_and_assert_fail(path, ["nodes[3].text"])
        stderr = result.stderr.decode("utf-8")
        self.assertTrue(
            stderr.startswith("校验失败："),
            "标准错误应以“校验失败：”开头：{!r}".format(stderr),
        )
        self.assertNotIn("不存在", stderr, "校验失败时不应出现节点不存在提示")

    def test_validation_failure_precedes_inspect_missing(self):
        """同一份缺 text 的副本：查看 missing 同样先报告整份校验失败，
        不进入节点查找。"""
        path = self.make_unused_sample()
        result = self.run_and_assert_fail(
            path, ["nodes[3].text"], node="missing"
        )
        stderr = result.stderr.decode("utf-8")
        self.assertTrue(
            stderr.startswith("校验失败："),
            "标准错误应以“校验失败：”开头：{!r}".format(stderr),
        )
        self.assertNotIn("不存在", stderr, "校验失败时不应出现节点不存在提示")


if __name__ == "__main__":
    unittest.main()
