# -*- coding: utf-8 -*-
"""dialogue.py 路线查询（route）命令行回归测试。

以 sample.json 为基础派生独立临时副本，覆盖先整份校验后查询的成功路径：
sample.json 查询 forest 的给定结果、目标即起点时 path 为 []、目标存在但
不可达时 path 为 null、两条等长路线汇合时选项编号序列 [1, 2] 优先于
[2, 1]、更短路线优先于字典序更小的长路线、自引用与多节点循环及重复指向
有限结束、中文及首尾空白编号原样精确匹配；以及参数错误（缺路径、缺目标
值、重复 --node、未知或额外参数、--node=编号 连写）在读取文件前以单行
用法说明拒绝、目标不存在沿用既有说明、不可达节点结构/引用非法先报整份
校验失败、文件读取与 UTF-8 解码及 JSON 语法错误沿用既有分类等失败边界。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出（按解析后的 JSON 对象核对，并核对只有
start、target、path 三个字段及单行结尾换行）、标准错误，以及输入文件
在执行前后字节不变。所有派生样例独立写入临时目录并自动清理，
sample.json 保持原样，用例可重复运行且结果一致。
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

# 参数错误专用的单行用法说明（标准错误应恰好是它加一个换行）。
ROUTE_USAGE = "python dialogue.py route <文件路径> --node <目标编号>"

# 题目固定的 sample.json 查询 forest 成功输出（紧凑 JSON）。
SAMPLE_FOREST_EXPECTED = {
    "start": "start",
    "target": "forest",
    "path": [{"source": "start", "choice": 1, "target": "forest"}],
}


def run_route(*args):
    """以命令行方式执行 route，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "route", *[str(a) for a in args]],
        capture_output=True,
    )


class RouteTestCase(unittest.TestCase):
    """公共断言：派生样例、文件字节不变、无调用栈、临时目录清理。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)
        self._sample_original_bytes = SAMPLE.read_bytes()

    def tearDown(self):
        # 仓库自带样例在任何用例后都必须字节不变。
        self.assertEqual(
            SAMPLE.read_bytes(),
            self._sample_original_bytes,
            "sample.json 在测试过程中被修改",
        )

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

    def assert_file_unchanged(self, path, before):
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )

    def assert_no_traceback(self, stderr):
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")

    def run_and_assert_route(self, path, node, expected_object):
        """成功：退出码 0、标准错误为空，输出为只含 start、target、path 的
        单行 JSON 对象加一个结尾换行；对象按解析后内容核对。"""
        before = path.read_bytes()
        result = run_route(path, "--node", node)
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
            set(actual.keys()),
            {"start", "target", "path"},
            "结果对象应只含 start、target、path 三个字段",
        )
        self.assertEqual(
            actual, expected_object, "解析后的 JSON 对象应与预期完全一致"
        )
        return result

    def run_and_assert_fail(self, path, node, expected_parts):
        """失败：退出码 2、标准输出为空、标准错误包含各片段且无调用栈。"""
        before = path.read_bytes()
        result = run_route(path, "--node", node)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result

    def run_and_assert_usage_error(self, args):
        """参数错误：退出码 2、标准输出为空、标准错误恰好为单行用法说明。"""
        result = run_route(*args)
        self.assertEqual(result.returncode, 2, "参数错误时退出码应为 2")
        self.assertEqual(result.stdout, b"", "参数错误时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertEqual(
            stderr,
            ROUTE_USAGE + "\n",
            "参数错误时标准错误应恰好为单行用法说明加换行",
        )
        return result


class TestRouteSuccess(RouteTestCase):
    """成功路径：整份结构与引用合法，给出最短路及字典序破平局的路线。"""

    def test_sample_json_route_to_forest(self):
        """直接对仓库自带 sample.json 查询 forest：与题目给定结果一致。"""
        result = self.run_and_assert_route(
            SAMPLE, "forest", SAMPLE_FOREST_EXPECTED
        )
        # 逐字节核对题目给出的紧凑输出形态与中文原样保留。
        self.assertEqual(
            result.stdout.decode("utf-8"),
            '{"start":"start","target":"forest",'
            '"path":[{"source":"start","choice":1,"target":"forest"}]}\n',
        )

    def test_sample_json_route_to_river_uses_second_option(self):
        """sample.json 查询 river：选项编号沿用 options 数组顺序从 1 开始。"""
        self.run_and_assert_route(
            SAMPLE,
            "river",
            {"start": "start", "target": "river",
             "path": [{"source": "start", "choice": 2, "target": "river"}]},
        )

    def test_target_is_start_gives_empty_path(self):
        """目标就是起点时 path 为 []，仍成功。"""
        self.run_and_assert_route(
            SAMPLE, "start", {"start": "start", "target": "start", "path": []}
        )

    def test_unreachable_target_gives_null_path(self):
        """目标存在但从 start 不可达时 path 为 null，仍成功。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路",
             "options": [{"text": "留在旁路", "target": "side"}]}
        )
        path = self.make_sample(data)
        result = self.run_and_assert_route(
            path, "side",
            {"start": "start", "target": "side", "path": None},
        )
        self.assertEqual(
            result.stdout.decode("utf-8"),
            '{"start":"start","target":"side","path":null}\n',
        )

    def make_converging_sample(self, direct=False):
        """两条等长路线汇合的小样例：s 经 a 或 b 各两步到 g，
        选项序列分别为 [1, 2] 与 [2, 1]；direct=True 时 s 另有
        第三选项一步直达 g，用于验证更短路线优先。"""
        start_options = [
            {"text": "去 a", "target": "a"},
            {"text": "去 b", "target": "b"},
        ]
        if direct:
            start_options.append({"text": "直达", "target": "g"})
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": start_options},
                {"id": "a", "text": "甲", "options": [
                    {"text": "绕路", "target": "z"},
                    {"text": "去终点", "target": "g"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "去终点", "target": "g"},
                    {"text": "绕路", "target": "z"},
                ]},
                {"id": "z", "text": "绕", "options": []},
                {"id": "g", "text": "终点", "options": []},
            ],
        }
        return self.make_sample(data)

    def test_equal_length_routes_prefer_lexicographically_smaller_choices(self):
        """等长路线 [1, 2] 与 [2, 1] 汇合于 g：取数值字典序最小的 [1, 2]。"""
        path = self.make_converging_sample()
        self.run_and_assert_route(
            path,
            "g",
            {"start": "s", "target": "g", "path": [
                {"source": "s", "choice": 1, "target": "a"},
                {"source": "a", "choice": 2, "target": "g"},
            ]},
        )

    def test_shorter_route_beats_lexicographically_smaller_longer_route(self):
        """更短路线 [3] 优先于字典序更小的长路线 [1, 2]。"""
        path = self.make_converging_sample(direct=True)
        self.run_and_assert_route(
            path,
            "g",
            {"start": "s", "target": "g",
             "path": [{"source": "s", "choice": 3, "target": "g"}]},
        )

    def test_self_reference_and_cycle_terminate(self):
        """自引用与多节点循环不导致死循环，路线仍取最短。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "原地打转", "target": "s"},
                    {"text": "去 a", "target": "a"},
                ]},
                {"id": "a", "text": "甲", "options": [
                    {"text": "去 b", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "回 a", "target": "a"},
                    {"text": "去终点", "target": "g"},
                    {"text": "也去终点", "target": "g"},
                ]},
                {"id": "g", "text": "终点", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_route(
            path,
            "g",
            {"start": "s", "target": "g", "path": [
                {"source": "s", "choice": 2, "target": "a"},
                {"source": "a", "choice": 1, "target": "b"},
                {"source": "b", "choice": 2, "target": "g"},
            ]},
        )

    def test_route_independent_of_nodes_order(self):
        """同样的图把 nodes 倒序排列，路线结果不变。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "g", "text": "终点", "options": []},
                {"id": "m", "text": "中", "options": [
                    {"text": "去终点", "target": "g"},
                ]},
                {"id": "s", "text": "起点", "options": [
                    {"text": "去中", "target": "m"},
                ]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_route(
            path,
            "g",
            {"start": "s", "target": "g", "path": [
                {"source": "s", "choice": 1, "target": "m"},
                {"source": "m", "choice": 1, "target": "g"},
            ]},
        )

    def test_ids_matched_exactly_with_surrounding_whitespace(self):
        """编号按原字符串精确匹配、首尾空白保留：' g ' 与 'g' 不同节点。"""
        data = {
            "start": " s ",
            "nodes": [
                {"id": " s ", "text": "起点", "options": [
                    {"text": "去带空格的 g", "target": " g "},
                ]},
                {"id": " g ", "text": "带空格终点", "options": []},
                {"id": "g", "text": "不带空格终点", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_route(
            path,
            " g ",
            {"start": " s ", "target": " g ",
             "path": [{"source": " s ", "choice": 1, "target": " g "}]},
        )


class TestRouteArgs(RouteTestCase):
    """参数错误：读取文件前拒绝，标准错误恰好为单行用法说明加换行。"""

    def assert_not_read(self, result_path):
        """参数错误发生在读取前：不存在的路径不会被读取或创建。"""
        self.assertFalse(result_path.exists(), "参数错误不应触及文件")

    def test_missing_path_and_node(self):
        self.run_and_assert_usage_error([])

    def test_missing_node_pair(self):
        missing = self.tmp_dir / "never_read.json"
        result = self.run_and_assert_usage_error([missing])
        self.assert_not_read(missing)

    def test_missing_node_value(self):
        missing = self.tmp_dir / "never_read.json"
        result = self.run_and_assert_usage_error([missing, "--node"])
        self.assert_not_read(missing)

    def test_duplicate_node_option(self):
        missing = self.tmp_dir / "never_read.json"
        result = self.run_and_assert_usage_error(
            [missing, "--node", "a", "--node", "b"]
        )
        self.assert_not_read(missing)

    def test_joined_node_form_rejected(self):
        missing = self.tmp_dir / "never_read.json"
        result = self.run_and_assert_usage_error([missing, "--node=forest"])
        self.assert_not_read(missing)

    def test_unknown_option_rejected(self):
        missing = self.tmp_dir / "never_read.json"
        result = self.run_and_assert_usage_error([missing, "--foo", "forest"])
        self.assert_not_read(missing)

    def test_extra_positional_rejected(self):
        missing = self.tmp_dir / "never_read.json"
        result = self.run_and_assert_usage_error(
            [missing, "--node", "forest", "extra"]
        )
        self.assert_not_read(missing)

    def test_node_before_path_rejected(self):
        missing = self.tmp_dir / "never_read.json"
        result = self.run_and_assert_usage_error(["--node", "forest", missing])
        self.assert_not_read(missing)

    def test_option_like_path_rejected(self):
        self.run_and_assert_usage_error(["--node", "--node", "forest"])


class TestRouteFailure(RouteTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_target_uses_existing_message(self):
        """合法文件中目标不存在：沿用既有节点不存在说明，含编号原值。"""
        result = self.run_and_assert_fail(
            SAMPLE, "ghost", ["文件中不存在编号为 'ghost' 的节点"]
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_missing_target_id_keeps_original_whitespace(self):
        """目标编号首尾空白原样进入不存在说明，不裁剪。"""
        self.run_and_assert_fail(
            SAMPLE, " forest ", ["文件中不存在编号为 ' forest ' 的节点"]
        )

    def test_invalid_structure_in_unreachable_node_fails_validation(self):
        """不可达 side 节点缺少 text：沿用“校验失败：”并定位 nodes[3].text，
        即使问题位于不可达节点也不能输出路线。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "options": [
                {"text": "去森林", "target": "forest"}]}
        )
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path, "forest", ["校验失败：", "nodes[3].text"]
        )
        self.assertTrue(
            result.stderr.decode("utf-8").startswith("校验失败："),
            "标准错误应以“校验失败：”开头",
        )

    def test_dangling_target_in_unreachable_node_fails_validation(self):
        """不可达 side 节点选项 target 指向不存在的 ghost：定位到
        nodes[3].options[0].target 并点名 ghost，不输出路线。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路",
             "options": [{"text": "去虚无", "target": "ghost"}]}
        )
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "forest",
            ["校验失败：", "nodes[3].options[0].target", "ghost"],
        )

    def test_json_syntax_error_uses_existing_category(self):
        """语法错误文件：沿用既有 JSON 语法错误分类，信息含路径与行列。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{\n  !", encoding="utf-8")
        result = self.run_and_assert_fail(
            broken, "forest", ["JSON 语法错误", "第 2 行第 3 列", str(broken)]
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_utf8_decode_error_uses_existing_category(self):
        """UTF-8 解码失败：沿用既有分类且信息含路径。"""
        bad = self.tmp_dir / "bad.json"
        bad.write_bytes(b"\xff")
        self.run_and_assert_fail(bad, "forest", ["UTF-8 解码失败", str(bad)])

    def test_unreadable_file_uses_existing_category(self):
        """路径不存在：沿用既有无法读取文件分类，含路径且不创建该文件。"""
        missing = self.tmp_dir / "never_created.json"
        result = run_route(missing, "--node", "forest")
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(missing), stderr)
        self.assertFalse(missing.exists(), "查询不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
