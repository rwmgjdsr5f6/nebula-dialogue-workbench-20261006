# -*- coding: utf-8 -*-
"""dialogue.py 无结尾路径报告（no-ending）命令行回归测试。

以 sample.json 为基础派生独立临时副本，覆盖先整份校验后报告的成功路径：
sample.json 全部可达节点都能走到结尾、追加 a/b/side 三个节点（a->b、b->a、
side 自引用，起点追加指向 a 的选项）后仅报告可达却走不到结尾的 a、b、
起点无选项按零步到达结尾不报告、自引用与多节点循环正常结束、
存在一条到结尾的路径即不报告（即使其他选项进入循环）、整份文件没有
结尾时报告全部可达节点、不可达节点不列入、结果按原 nodes 顺序去重、
中文及首尾空白编号原样保留；以及不可达节点自身结构/引用非法时先报告
整份校验失败、文件读取与 JSON 语法错误沿用既有分类等失败边界。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出（按解析后的 JSON 对象核对，并核对只有
start、no_ending 两个字段及单行结尾换行）、标准错误，以及输入文件
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

# 题目固定的两个成功输出（紧凑 JSON、键顺序 start/no_ending）。
SAMPLE_EXPECTED = {"start": "start", "no_ending": []}
LOOP_EXPECTED = {"start": "start", "no_ending": ["a", "b"]}


def run_no_ending(path):
    """以命令行方式执行 no-ending，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "no-ending", str(path)],
        capture_output=True,
    )


class NoEndingTestCase(unittest.TestCase):
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

    def make_loop_sample(self, name="case.json"):
        """在 sample.json 的独立副本上按题目要求追加：起点末尾追加指向 a
        的选项，nodes 末尾依次追加 a（选项指向 b）、b（选项指向 a）、
        side（选项指向自身）三个节点，新增文字均为字符串。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"].append(
            {"text": "进入循环", "target": "a"}
        )
        data["nodes"].append(
            {"id": "a", "text": "循环甲",
             "options": [{"text": "去 b", "target": "b"}]}
        )
        data["nodes"].append(
            {"id": "b", "text": "循环乙",
             "options": [{"text": "回 a", "target": "a"}]}
        )
        data["nodes"].append(
            {"id": "side", "text": "旁路",
             "options": [{"text": "留在旁路", "target": "side"}]}
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
        """成功：退出码 0、标准错误为空，输出为只含 start、no_ending 的
        单行 JSON 对象加一个结尾换行；对象按解析后内容核对。"""
        before = path.read_bytes()
        result = run_no_ending(path)
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
            {"start", "no_ending"},
            "报告对象应只含 start 与 no_ending 两个字段",
        )
        self.assertEqual(
            actual, expected_object, "解析后的 JSON 对象应与预期完全一致"
        )
        return result

    def run_and_assert_fail(self, path, expected_parts):
        """失败：退出码 2、标准输出为空、标准错误包含各片段且无调用栈。"""
        before = path.read_bytes()
        result = run_no_ending(path)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestNoEndingSuccess(NoEndingTestCase):
    """成功路径：整份结构与引用合法，报告可达却无有限步路径到结尾的节点。"""

    def test_sample_json_all_paths_end(self):
        """直接对仓库自带 sample.json 报告：所有可达节点都能走到结尾。"""
        result = self.run_and_assert_report(SAMPLE, SAMPLE_EXPECTED)
        # 另逐字节核对题目给出的紧凑输出形态与中文原样保留。
        self.assertEqual(
            result.stdout.decode("utf-8"),
            '{"start":"start","no_ending":[]}\n',
        )

    def test_appended_loop_reports_a_and_b_only(self):
        """题目指定的独立副本：追加 a、b、side 与起点指向 a 的选项后，
        仅报告可达且走不到结尾的 a、b；不可达的 side 不列入。"""
        path = self.make_loop_sample()
        self.run_and_assert_report(path, LOOP_EXPECTED)

    def test_start_without_options_is_zero_step_ending(self):
        """起点 options 为空：结尾按零步到达处理，起点不报告。"""
        data = {
            "start": "结局",
            "nodes": [
                {"id": "结局", "text": "到此为止。", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(path, {"start": "结局", "no_ending": []})

    def test_reachable_self_loop_without_ending_is_reported(self):
        """唯一节点自引用且整份文件没有结尾：报告起点自身，且能正常结束。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "原地",
                 "options": [{"text": "再走一步", "target": "s"}]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(path, {"start": "s", "no_ending": ["s"]})

    def test_multi_node_cycle_reachable_is_reported(self):
        """可达的 a<->b 多节点循环且无出路：a、b 都报告，正常结束。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点",
                 "options": [{"text": "去 a", "target": "a"}]},
                {"id": "a", "text": "循环甲",
                 "options": [{"text": "去 b", "target": "b"}]},
                {"id": "b", "text": "循环乙",
                 "options": [{"text": "回 a", "target": "a"}]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(
            path, {"start": "s", "no_ending": ["s", "a", "b"]}
        )

    def test_one_path_to_ending_excludes_node(self):
        """节点只要有一条到结尾的路径就不报告，即使另一个选项进入循环。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "进循环", "target": "a"},
                    {"text": "去结尾", "target": "e"},
                ]},
                {"id": "a", "text": "循环甲",
                 "options": [{"text": "去 b", "target": "b"}]},
                {"id": "b", "text": "循环乙",
                 "options": [{"text": "回 a", "target": "a"}]},
                {"id": "e", "text": "结尾", "options": []},
            ],
        }
        path = self.make_sample(data)
        # s 有选项直达 e，故 s 不报告；a、b 互指且无出路，报告。
        self.run_and_assert_report(
            path, {"start": "s", "no_ending": ["a", "b"]}
        )

    def test_node_on_cycle_with_escape_is_not_reported(self):
        """循环中的节点本身存在一条到结尾的路径（a->e）：a、b 都不报告。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点",
                 "options": [{"text": "去 a", "target": "a"}]},
                {"id": "a", "text": "循环甲", "options": [
                    {"text": "去 b", "target": "b"},
                    {"text": "去结尾", "target": "e"},
                ]},
                {"id": "b", "text": "循环乙",
                 "options": [{"text": "回 a", "target": "a"}]},
                {"id": "e", "text": "结尾", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(path, {"start": "s", "no_ending": []})

    def test_no_ending_anywhere_reports_all_reachable(self):
        """整份文件没有结尾：报告全部可达节点（按 nodes 顺序）。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点",
                 "options": [{"text": "去 a", "target": "a"}]},
                {"id": "a", "text": "甲",
                 "options": [{"text": "去 b", "target": "b"}]},
                {"id": "b", "text": "乙",
                 "options": [{"text": "回 a", "target": "a"}]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(
            path, {"start": "s", "no_ending": ["s", "a", "b"]}
        )

    def test_unreachable_no_ending_node_not_reported(self):
        """不可达节点即使自身走不到结尾也不列入报告。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点",
                 "options": [{"text": "去结尾", "target": "e"}]},
                {"id": "e", "text": "结尾", "options": []},
                {"id": "u", "text": "孤岛自循环",
                 "options": [{"text": "原地", "target": "u"}]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(path, {"start": "s", "no_ending": []})

    def test_unreachable_ending_not_reported(self):
        """不可达的结尾节点同样不列入报告。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点",
                 "options": [{"text": "去结尾", "target": "e"}]},
                {"id": "e", "text": "结尾", "options": []},
                {"id": "u", "text": "孤岛结尾", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(path, {"start": "s", "no_ending": []})

    def test_multiple_options_to_same_node_terminates_and_dedupes(self):
        """多个选项指向同一循环节点只计一次，自引用结构能正常结束。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "甲", "target": "t"},
                    {"text": "乙", "target": "t"},
                ]},
                {"id": "t", "text": "循环",
                 "options": [{"text": "回", "target": "t"}]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(
            path, {"start": "s", "no_ending": ["s", "t"]}
        )

    def test_results_follow_nodes_order_without_duplicates(self):
        """报告编号按原 nodes 顺序排列，每个只出现一次。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "x2", "text": "二",
                 "options": [{"text": "回", "target": "x2"}]},
                {"id": "s", "text": "起点", "options": [
                    {"text": "去 x2", "target": "x2"},
                    {"text": "再去 x2", "target": "x2"},
                    {"text": "去 x1", "target": "x1"},
                ]},
                {"id": "x1", "text": "一",
                 "options": [{"text": "去 x2", "target": "x2"}]},
                {"id": "e", "text": "可达结尾", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(
            path, {"start": "s", "no_ending": ["x2", "s", "x1"]}
        )

    def test_ids_matched_exactly_with_surrounding_whitespace(self):
        """编号首尾空白保留并参与精确匹配：' a ' 是结尾，a 自循环被报告。"""
        data = {
            "start": " s ",
            "nodes": [
                {"id": " s ", "text": "起点", "options": [
                    {"text": "去带空格的 a", "target": " a "},
                    {"text": "去不带空格的 a", "target": "a"},
                ]},
                {"id": " a ", "text": "带空格的结尾", "options": []},
                {"id": "a", "text": "不带空格的自循环",
                 "options": [{"text": "原地", "target": "a"}]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_report(
            path, {"start": " s ", "no_ending": ["a"]}
        )


class TestNoEndingFailure(NoEndingTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_invalid_structure_in_unreachable_node_fails_validation(self):
        """不可达 side 节点缺少 text：沿用“校验失败：”并定位 nodes[3].text，
        即使问题位于不可达节点也不能输出报告。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "options": []}
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
        """start 悬空引用：先整份校验失败，不进入报告计算。"""
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
        result = run_no_ending(missing)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(missing), stderr)
        self.assertFalse(missing.exists(), "报告不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
