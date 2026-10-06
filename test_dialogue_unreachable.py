# -*- coding: utf-8 -*-
"""dialogue.py 不可达节点报告（unreachable）命令行回归测试。

以 sample.json 为基础派生独立临时副本，覆盖先整份校验后报告的成功路径：
sample.json 全部可达、追加不可达 side 节点（选项分别指向 forest 与 side）、
起点无选项仍算可达、自引用与多个选项指向同一节点正常结束、
多节点循环整体不可达、不可达节点反向指向可达节点不改变结论、
结果按原 nodes 顺序排列且不重复、中文及首尾空白编号原样保留；
以及不可达节点自身结构/引用非法时先报告整份校验失败、
文件读取与 JSON 语法错误沿用既有分类等失败边界。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出（按解析后的 JSON 对象核对，并核对只有
start、unreachable 两个字段及单行结尾换行）、标准错误，以及输入文件
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

# 题目固定的两个成功输出（紧凑 JSON、键顺序 start/unreachable）。
SAMPLE_EXPECTED = {"start": "start", "unreachable": []}
SIDE_EXPECTED = {"start": "start", "unreachable": ["side"]}


def run_unreachable(path):
    """以命令行方式执行 unreachable，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "unreachable", str(path)],
        capture_output=True,
    )


class UnreachableTestCase(unittest.TestCase):
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

    def make_side_sample(self, name="case.json"):
        """在 sample.json 的独立副本末尾追加 side 节点：文字为“旁路”，
        两个选项分别指向 forest 与 side（自引用），该节点整体不可达。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {
                "id": "side",
                "text": "旁路",
                "options": [
                    {"text": "去森林", "target": "forest"},
                    {"text": "留在旁路", "target": "side"},
                ],
            }
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

    def run_and_assert_report(self, path, expected_object):
        """成功：退出码 0、标准错误为空，输出为只含 start、unreachable 的
        单行 JSON 对象加一个结尾换行；对象按解析后内容核对。"""
        before = path.read_bytes()
        result = run_unreachable(path)
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
            {"start", "unreachable"},
            "报告对象应只含 start 与 unreachable 两个字段",
        )
        self.assertEqual(
            actual, expected_object, "解析后的 JSON 对象应与预期完全一致"
        )
        return result

    def run_and_assert_fail(self, path, expected_parts):
        """失败：退出码 2、标准输出为空、标准错误包含各片段且无调用栈。"""
        before = path.read_bytes()
        result = run_unreachable(path)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestUnreachableSuccess(UnreachableTestCase):
    """成功路径：整份结构与引用合法，按 target 正向可达性给出报告。"""

    def test_sample_json_all_reachable(self):
        """直接对仓库自带 sample.json 报告：三个节点都从 start 可达。"""
        result = self.run_and_assert_report(SAMPLE, SAMPLE_EXPECTED)
        # 另逐字节核对题目给出的紧凑输出形态与中文原样保留。
        self.assertEqual(
            result.stdout.decode("utf-8"),
            '{"start":"start","unreachable":[]}\n',
        )

    def test_appended_side_node_is_unreachable(self):
        """独立副本末尾追加合法 side（旁路，选项指向 forest、side）：
        结论与题目给定结果一致，且该副本改动不影响 sample.json。"""
        path = self.make_side_sample()
        self.run_and_assert_report(path, SIDE_EXPECTED)

    def test_start_alone_without_options_is_reachable(self):
        """起点没有选项时本身仍算可达，其余节点列入不可达。"""
        data = {
            "start": "结局",
            "nodes": [
                {"id": "结局", "text": "到此为止。", "options": []},
                {"id": "孤岛", "text": "无人抵达。", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(path, {"start": "结局", "unreachable": ["孤岛"]})

    def test_self_reference_terminates(self):
        """可达节点的自引用不导致重复列项或死循环。"""
        data = {
            "start": "s",
            "nodes": [
                {
                    "id": "s",
                    "text": "原地",
                    "options": [{"text": "再走一步", "target": "s"}],
                },
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(path, {"start": "s", "unreachable": []})

    def test_multiple_options_to_same_node_terminates(self):
        """多个选项指向同一节点只计一次可达，不重复。"""
        data = {
            "start": "s",
            "nodes": [
                {
                    "id": "s",
                    "text": "起点",
                    "options": [
                        {"text": "甲", "target": "t"},
                        {"text": "乙", "target": "t"},
                        {"text": "回", "target": "s"},
                    ],
                },
                {"id": "t", "text": "终点", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(path, {"start": "s", "unreachable": []})

    def test_disconnected_cycle_entirely_unreachable(self):
        """与起点断开的 a<->b 多节点循环整体列入报告，且能正常结束。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点",
                 "options": [{"text": "去 r", "target": "r"}]},
                {"id": "r", "text": "可达结尾", "options": []},
                {"id": "a", "text": "循环甲",
                 "options": [{"text": "去 b", "target": "b"}]},
                {"id": "b", "text": "循环乙",
                 "options": [{"text": "回 a", "target": "a"}]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(
            path, {"start": "s", "unreachable": ["a", "b"]}
        )

    def test_unreachable_pointing_back_does_not_become_reachable(self):
        """不可达节点的选项指向可达节点属于反向边：不把它变成可达。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": []},
                {"id": "u", "text": "回头岸",
                 "options": [{"text": "指向起点", "target": "s"}]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(path, {"start": "s", "unreachable": ["u"]})

    def test_results_follow_nodes_order_without_duplicates(self):
        """不可达编号按原 nodes 顺序排列，每个只出现一次。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "u2", "text": "二", "options": []},
                {"id": "s", "text": "起点",
                 "options": [
                     {"text": "去 r", "target": "r"},
                     {"text": "再去 r", "target": "r"},
                 ]},
                {"id": "u1", "text": "一", "options": []},
                {"id": "r", "text": "可达", "options": []},
                {"id": "u3", "text": "三",
                 "options": [{"text": "看 r", "target": "r"}]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(
            path, {"start": "s", "unreachable": ["u2", "u1", "u3"]}
        )

    def test_ids_matched_exactly_with_surrounding_whitespace(self):
        """编号按原字符串精确匹配、首尾空白保留：' a ' 与 'a' 不同节点。"""
        data = {
            "start": " s ",
            "nodes": [
                {"id": " s ", "text": "起点",
                 "options": [{"text": "去带空格的 a", "target": " a "}]},
                {"id": " a ", "text": "带空格", "options": []},
                {"id": "a", "text": "不带空格",
                 "options": [{"text": "指向带空格的 a", "target": " a "}]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(
            path, {"start": " s ", "unreachable": ["a"]}
        )


class TestUnreachableFailure(UnreachableTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_invalid_structure_in_unreachable_node_fails_validation(self):
        """不可达 side 节点缺少 text：沿用“校验失败：”并定位 nodes[3].text，
        即使问题位于不可达节点也不能输出报告。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "options": [
                {"text": "去森林", "target": "forest"}]}
        )
        path = self.make_sample(data)
        result = self.run_and_assert_fail(path, ["校验失败：", "nodes[3].text"])
        self.assertTrue(
            result.stderr.decode("utf-8").startswith("校验失败："),
            "标准错误应以“校验失败：”开头",
        )

    def test_dangling_target_in_unreachable_node_fails_validation(self):
        """不可达 side 节点选项 target 指向不存在的 ghost：定位到
        nodes[3].options[0].target 并点名 ghost，不输出报告。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路",
             "options": [{"text": "去虚无", "target": "ghost"}]}
        )
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path,
            ["校验失败：", "nodes[3].options[0].target", "ghost"],
        )

    def test_start_points_to_missing_node(self):
        """start 悬空引用：先整份校验失败，不进入可达性计算。"""
        data = self.load_sample_data()
        data["start"] = "missing"
        path = self.make_sample(data)
        self.run_and_assert_fail(path, ["校验失败：", "start", "missing"])

    def test_json_syntax_error_uses_existing_category(self):
        """语法错误文件：沿用既有 JSON 语法错误分类，信息含路径与行列。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{\n  !", encoding="utf-8")
        result = self.run_and_assert_fail(
            broken, ["JSON 语法错误", "第 2 行第 3 列", str(broken)]
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_utf8_decode_error_uses_existing_category(self):
        """UTF-8 解码失败：沿用既有分类且信息含路径。"""
        bad = self.tmp_dir / "bad.json"
        bad.write_bytes(b"\xff")
        self.run_and_assert_fail(bad, ["UTF-8 解码失败", str(bad)])

    def test_unreadable_file_uses_existing_category(self):
        """路径不存在：沿用既有无法读取文件分类，含路径且不创建该文件。"""
        missing = self.tmp_dir / "never_created.json"
        result = run_unreachable(missing)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(missing), stderr)
        self.assertFalse(missing.exists(), "报告不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
