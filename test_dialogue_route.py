# -*- coding: utf-8 -*-
"""dialogue.py 路线查询（route）命令行回归测试。

以 sample.json 为基础派生独立临时副本，覆盖先整份校验后查询的成功路径：
sample.json 查询 forest 的给定结果、目标即起点时 path 为 []、目标不可达时
path 为 null 仍成功、两条等长路线汇合时 [1,2] 优先于 [2,1]、更短路线优先
于字典序更小者、自引用与多节点循环及重复指向均有限结束、中文及首尾空白
编号原样精确匹配；以及目标不存在、不可达节点结构/引用非法时先报告整份
校验失败、文件读取与 JSON 语法错误沿用既有分类等失败边界。

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

# 题目固定的成功输出（紧凑 JSON、键顺序 start/target/path）。
SAMPLE_FOREST_EXPECTED = {
    "start": "start",
    "target": "forest",
    "path": [{"source": "start", "choice": 1, "target": "forest"}],
}


def run_route(path, node):
    """以命令行方式执行 route，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "route", str(path), "--node", node],
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
        result = run_route(path, node)
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
        result = run_route(path, node)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestRouteSuccess(RouteTestCase):
    """成功路径：整份结构与引用合法，给出从 start 出发的最优路线。"""

    def test_sample_json_route_to_forest(self):
        """直接对仓库自带 sample.json 查询 forest：结果与题目给定一致。"""
        result = self.run_and_assert_route(SAMPLE, "forest", SAMPLE_FOREST_EXPECTED)
        # 逐字节核对题目给出的紧凑输出形态与中文原样保留。
        self.assertEqual(
            result.stdout.decode("utf-8"),
            '{"start":"start","target":"forest",'
            '"path":[{"source":"start","choice":1,"target":"forest"}]}\n',
        )

    def test_target_is_start_gives_empty_path(self):
        """目标就是起点时 path 为 []，仍成功。"""
        self.run_and_assert_route(
            SAMPLE, "start", {"start": "start", "target": "start", "path": []}
        )

    def test_unreachable_target_gives_null_path(self):
        """目标存在但不可达时 path 为 null，退出码仍为 0。"""
        data = self.load_sample_data()
        data["nodes"].append({"id": "side", "text": "旁路", "options": []})
        path = self.make_sample(data)
        result = self.run_and_assert_route(
            path, "side", {"start": "start", "target": "side", "path": None}
        )
        self.assertEqual(
            result.stdout.decode("utf-8"),
            '{"start":"start","target":"side","path":null}\n',
        )

    def test_equal_length_routes_prefer_smaller_choice_sequence(self):
        """两条等长路线在 t 汇合：[1,2] 优先于 [2,1]，与 nodes 顺序无关。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "t", "text": "汇合点", "options": []},
                {"id": "y", "text": "乙", "options": [
                    {"text": "乙一", "target": "t"},
                    {"text": "乙二", "target": "z"},
                ]},
                {"id": "s", "text": "起点", "options": [
                    {"text": "去甲", "target": "x"},
                    {"text": "去乙", "target": "y"},
                ]},
                {"id": "x", "text": "甲", "options": [
                    {"text": "甲一", "target": "z"},
                    {"text": "甲二", "target": "t"},
                ]},
                {"id": "z", "text": "旁支", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_route(path, "t", {
            "start": "s",
            "target": "t",
            "path": [
                {"source": "s", "choice": 1, "target": "x"},
                {"source": "x", "choice": 2, "target": "t"},
            ],
        })

    def test_shorter_route_beats_longer_lexicographically_smaller_one(self):
        """更短路线优先：[2] 胜过字典序更小的 [1,1]。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "绕路", "target": "m"},
                    {"text": "直达", "target": "t"},
                ]},
                {"id": "m", "text": "中途", "options": [
                    {"text": "继续", "target": "t"},
                ]},
                {"id": "t", "text": "终点", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_route(path, "t", {
            "start": "s",
            "target": "t",
            "path": [{"source": "s", "choice": 2, "target": "t"}],
        })

    def test_self_loop_and_cycle_terminate(self):
        """起点自引用与途中 a<->b 多节点循环不导致死循环，路线仍最优。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "原地", "target": "s"},
                    {"text": "去 a", "target": "a"},
                ]},
                {"id": "a", "text": "甲", "options": [
                    {"text": "去 b", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "回 a", "target": "a"},
                    {"text": "去 t", "target": "t"},
                ]},
                {"id": "t", "text": "终点", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_route(path, "t", {
            "start": "s",
            "target": "t",
            "path": [
                {"source": "s", "choice": 2, "target": "a"},
                {"source": "a", "choice": 1, "target": "b"},
                {"source": "b", "choice": 2, "target": "t"},
            ],
        })

    def test_repeated_pointers_to_same_node_terminate(self):
        """多个选项指向同一节点只展开一次，路线正常给出。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "甲", "target": "m"},
                    {"text": "乙", "target": "m"},
                ]},
                {"id": "m", "text": "中途", "options": [
                    {"text": "去 t", "target": "t"},
                    {"text": "也去 t", "target": "t"},
                ]},
                {"id": "t", "text": "终点", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_route(path, "t", {
            "start": "s",
            "target": "t",
            "path": [
                {"source": "s", "choice": 1, "target": "m"},
                {"source": "m", "choice": 1, "target": "t"},
            ],
        })

    def test_ids_matched_exactly_with_surrounding_whitespace(self):
        """编号按原字符串精确匹配、首尾空白保留：' a ' 与 'a' 是不同节点。"""
        data = {
            "start": " s ",
            "nodes": [
                {"id": " s ", "text": "起点", "options": [
                    {"text": "去带空格的 a", "target": " a "},
                ]},
                {"id": " a ", "text": "带空格", "options": []},
                {"id": "a", "text": "不带空格", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_route(path, " a ", {
            "start": " s ",
            "target": " a ",
            "path": [{"source": " s ", "choice": 1, "target": " a "}],
        })

    def test_chinese_target_id_displayed_verbatim(self):
        """中文编号在结果中原样显示，不转义。"""
        data = {
            "start": "起点",
            "nodes": [
                {"id": "起点", "text": "出发", "options": [
                    {"text": "进山", "target": "森林"},
                ]},
                {"id": "森林", "text": "到了", "options": []},
            ],
        }
        path = self.make_sample(data)
        result = self.run_and_assert_route(path, "森林", {
            "start": "起点",
            "target": "森林",
            "path": [{"source": "起点", "choice": 1, "target": "森林"}],
        })
        self.assertIn("森林", result.stdout.decode("utf-8"))
        self.assertNotIn("\\u", result.stdout.decode("utf-8"))


class TestRouteFailure(RouteTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_target_uses_existing_message(self):
        """合法文件中目标不存在：沿用节点不存在说明，含编号原值。"""
        result = self.run_and_assert_fail(
            SAMPLE, "ghost", ["文件中不存在编号为 'ghost' 的节点"]
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_missing_target_id_keeps_surrounding_whitespace(self):
        """目标编号首尾空白不裁剪，错误说明中按原值引用。"""
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
        result = run_route(missing, "forest")
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(missing), stderr)
        self.assertFalse(missing.exists(), "查询不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
