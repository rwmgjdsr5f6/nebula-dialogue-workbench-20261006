# -*- coding: utf-8 -*-
"""dialogue.py 入向引用查询（references）命令行回归测试。

以 sample.json 为基础派生临时副本，覆盖省略 --node 查询起点、
显式 --node 结果一致、结尾节点单条引用、不可达来源的多个选项逐项保留、
自引用计入、循环关系不展开间接引用、start 字段本身不算引用，
以及节点不存在、整份校验先于查询的失败边界。

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


def run_references(path, node=None):
    """以命令行方式执行 references；node 为 None 时省略 --node 参数。"""
    args = [sys.executable, str(DIALOGUE), "references", str(path)]
    if node is not None:
        args.extend(["--node", node])
    return subprocess.run(args, capture_output=True)


class ReferencesTestCase(unittest.TestCase):
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
        """在 sample.json 末尾追加不可达的 side 节点（甲、乙两个选项
        都指向 forest），返回临时副本路径。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {
                "id": "side",
                "text": "岔路旁",
                "options": [
                    {"text": "甲", "target": "forest"},
                    {"text": "乙", "target": "forest"},
                ],
            }
        )
        return self.make_sample(data, name)

    def make_cycle_sample(self, name="case.json"):
        """构造 a、b 互相指向的循环对话，返回临时样例路径。"""
        data = {
            "start": "a",
            "nodes": [
                {
                    "id": "a",
                    "text": "甲地",
                    "options": [{"text": "去乙地", "target": "b"}],
                },
                {
                    "id": "b",
                    "text": "乙地",
                    "options": [{"text": "回甲地", "target": "a"}],
                },
            ],
        }
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
        result = run_references(path, node=node)
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
        result = run_references(path, node=node)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestReferencesSuccess(ReferencesTestCase):
    """成功路径：省略 --node 查询起点，显式 --node 查询指定节点。"""

    def test_omitted_node_queries_start_with_empty_references(self):
        """省略 --node 时查询 start：start 字段本身不算选项引用，
        且 sample.json 中没有选项指向 start，结果为空数组。"""
        path = self.make_plain_sample()
        self.run_and_assert_ok(path, {"id": "start", "references": []})

    def test_explicit_start_matches_omitted_node(self):
        """显式 --node start 的结果应与省略 --node 完全一致。"""
        path = self.make_plain_sample()
        expected = {"id": "start", "references": []}
        explicit = self.run_and_assert_ok(path, expected, node="start")
        omitted = self.run_and_assert_ok(path, expected)
        self.assertEqual(explicit.stdout, omitted.stdout)
        self.assertEqual(explicit.stderr, omitted.stderr)
        self.assertEqual(explicit.returncode, omitted.returncode)

    def test_forest_has_single_reference_from_start(self):
        """查询结尾节点 forest：仅 start 的选项 1 指向它，文字为“向左走”。"""
        path = self.make_plain_sample()
        self.run_and_assert_ok(
            path,
            {
                "id": "forest",
                "references": [
                    {"source": "start", "choice": 1, "text": "向左走"},
                ],
            },
            node="forest",
        )

    def test_river_reference_uses_second_choice(self):
        """查询 river：start 的选项 2 指向它，choice 按来源 options 顺序编号。"""
        path = self.make_plain_sample()
        self.run_and_assert_ok(
            path,
            {
                "id": "river",
                "references": [
                    {"source": "start", "choice": 2, "text": "向右走"},
                ],
            },
            node="river",
        )

    def test_unreachable_source_options_kept_in_order(self):
        """追加不可达的 side 节点（甲、乙均指向 forest）：查询 forest 依次
        保留 start 的选项 1、side 的选项 1 和 2，文字与原选项一致。"""
        path = self.make_side_sample()
        self.run_and_assert_ok(
            path,
            {
                "id": "forest",
                "references": [
                    {"source": "start", "choice": 1, "text": "向左走"},
                    {"source": "side", "choice": 1, "text": "甲"},
                    {"source": "side", "choice": 2, "text": "乙"},
                ],
            },
            node="forest",
        )

    def test_self_reference_counts(self):
        """side 的唯一选项指向自身：查询 side 时该自引用正常计入。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {
                "id": "side",
                "text": "岔路旁",
                "options": [{"text": "原地停留", "target": "side"}],
            }
        )
        path = self.make_sample(data)
        self.run_and_assert_ok(
            path,
            {
                "id": "side",
                "references": [
                    {"source": "side", "choice": 1, "text": "原地停留"},
                ],
            },
            node="side",
        )

    def test_cycle_lists_only_direct_references(self):
        """a、b 互相指向：查询 a 只列出 b 的直接选项，不沿循环展开间接引用。"""
        path = self.make_cycle_sample()
        self.run_and_assert_ok(
            path,
            {
                "id": "a",
                "references": [
                    {"source": "b", "choice": 1, "text": "回甲地"},
                ],
            },
            node="a",
        )
        self.run_and_assert_ok(
            path,
            {
                "id": "b",
                "references": [
                    {"source": "a", "choice": 1, "text": "去乙地"},
                ],
            },
            node="b",
        )


class TestReferencesFailure(ReferencesTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_node_reports_not_found(self):
        """合法副本指定 --node missing：报告节点不存在。"""
        path = self.make_plain_sample()
        self.run_and_assert_fail(path, ["missing", "不存在"], node="missing")

    def test_validation_failure_precedes_query_start(self):
        """末尾追加缺少 text 的不可达 unused 节点：查询 start 也应
        先报告整份校验失败，不出现节点不存在提示。"""
        path = self.make_unused_sample()
        result = self.run_and_assert_fail(path, ["nodes[3].text"])
        stderr = result.stderr.decode("utf-8")
        self.assertTrue(
            stderr.startswith("校验失败："),
            "标准错误应以“校验失败：”开头：{!r}".format(stderr),
        )
        self.assertNotIn("不存在", stderr, "校验失败时不应出现节点不存在提示")

    def test_validation_failure_precedes_query_missing(self):
        """同一份缺 text 的副本：查询 missing 同样先报告整份校验失败，
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

    def test_json_syntax_error_uses_existing_category(self):
        """语法错误文件：沿用既有 JSON 语法错误分类与定位。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{", encoding="utf-8")
        self.run_and_assert_fail(broken, ["JSON 语法错误"])

    def test_unreadable_file_uses_existing_category(self):
        """路径不存在：沿用既有无法读取文件分类。"""
        missing = self.tmp_dir / "never_created.json"
        result = run_references(missing)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertFalse(missing.exists(), "查询不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
