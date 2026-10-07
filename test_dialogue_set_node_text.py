# -*- coding: utf-8 -*-
"""dialogue.py 节点正文修改（set-node-text）命令行回归测试。

以 sample.json 为基础派生独立临时副本，覆盖先整份校验后改正文的成功路径：
样例中 forest 正文改为“林间很安静。”的给定结果、起点/结尾/不可达节点均可
修改、自引用与合法循环不影响命令结束、空字符串/纯空白/中文/引号/反斜杠/
换行按传入字符串原样保存（换行在单行 JSON 中按 JSON 规则转义）、形似参数
的编号与正文作为值处理、新正文与原值相同时输出等价对象、start/编号/全部
选项/其他节点文字/各层额外字段的 JSON 值与数组顺序原样保留、中文不转义、
编号首尾空白精确匹配、不创建结果文件；以及节点不存在沿用既有说明、
不可达节点结构/引用非法时先报告整份校验失败、文件读取与 JSON 语法错误
沿用既有分类等失败边界。参数格式错误另有
test_dialogue_set_node_text_args.py。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出（成功时按解析后的 JSON 对象核对，且为单行
加一个结尾换行）、标准错误，以及输入文件在执行前后字节不变、不创建
结果文件。所有派生样例独立写入临时目录并自动清理，sample.json 保持
原样，用例可重复运行且结果一致。
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


def run_set_text(path, node_id, new_text):
    """以命令行方式执行 set-node-text，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "set-node-text", str(path),
         "--node", node_id, "--text", new_text],
        capture_output=True,
    )


class SetNodeTextTestCase(unittest.TestCase):
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

    def run_and_assert_set_text(self, path, node_id, new_text, expected_object):
        """成功：退出码 0、标准错误为空，输出为修改后的完整对话对象，
        单行 JSON 加一个结尾换行；对象按解析后内容核对。返回
        (result, stdout_text)。"""
        before = path.read_bytes()
        result = run_set_text(path, node_id, new_text)
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
            actual, expected_object, "解析后的 JSON 对象应与预期完全一致"
        )
        return result, stdout

    def run_and_assert_fail(self, path, node_id, new_text, expected_parts):
        """失败：退出码 2、标准输出为空、标准错误包含各片段且无调用栈。"""
        before = path.read_bytes()
        result = run_set_text(path, node_id, new_text)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestSetNodeTextSuccess(SetNodeTextTestCase):
    """成功路径：整份校验通过后输出修改后的完整对话对象。"""

    def test_sample_set_forest_text(self):
        """验收用例：forest 正文改为“林间很安静。”，只有该节点 text 改变。"""
        expected = {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "林间很安静。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        }
        result, stdout = self.run_and_assert_set_text(
            SAMPLE, "forest", "林间很安静。", expected
        )
        # 中文原样输出，不转义；其他节点文字仍在。
        self.assertIn("林间很安静。", stdout)
        self.assertIn("你来到岔路口。", stdout)
        self.assertIn("你到了河边。", stdout)
        self.assertNotIn("你到了森林。", stdout)
        self.assertNotIn("\\u", stdout)

    def test_start_node_text_can_change(self):
        """起点节点的正文可以修改，start 与选项保持原样。"""
        self.run_and_assert_set_text(SAMPLE, "start", "新的起点。", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "新的起点。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })

    def test_ending_node_text_can_change(self):
        """结尾节点（options 为空数组）的正文可以修改。"""
        self.run_and_assert_set_text(SAMPLE, "river", "河水潺潺。", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "河水潺潺。", "options": []},
            ],
        })

    def test_unreachable_node_text_can_change(self):
        """不可达节点的正文也可以修改，可达性不影响命令。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路", "options": []}
        )
        path = self.make_sample(data)
        self.run_and_assert_set_text(path, "side", "另一条路。", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
                {"id": "side", "text": "另一条路。", "options": []},
            ],
        })

    def test_self_reference_and_cycle_do_not_matter(self):
        """自引用与合法循环中的节点都可修改正文，命令正常结束。"""
        data = {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "原地", "target": "a"},
                    {"text": "去乙", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "回甲", "target": "a"},
                ]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_set_text(path, "a", "新甲", {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "新甲", "options": [
                    {"text": "原地", "target": "a"},
                    {"text": "去乙", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "回甲", "target": "a"},
                ]},
            ],
        })
        self.run_and_assert_set_text(path, "b", "新乙", {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "原地", "target": "a"},
                    {"text": "去乙", "target": "b"},
                ]},
                {"id": "b", "text": "新乙", "options": [
                    {"text": "回甲", "target": "a"},
                ]},
            ],
        })

    def test_empty_string_text_saved_as_is(self):
        """空字符串原样保存为 ""。"""
        _, stdout = self.run_and_assert_set_text(
            SAMPLE, "forest", "",
            {**self.load_sample_data(),
             "nodes": [
                 {"id": "start", "text": "你来到岔路口。", "options": [
                     {"text": "向左走", "target": "forest"},
                     {"text": "向右走", "target": "river"},
                 ]},
                 {"id": "forest", "text": "", "options": []},
                 {"id": "river", "text": "你到了河边。", "options": []},
             ]},
        )
        self.assertIn('"text": ""', stdout)

    def test_whitespace_only_text_saved_as_is(self):
        """纯空白正文原样保存，不裁剪。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        self.run_and_assert_set_text(path, "forest", "  \t ", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "  \t ", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })

    def test_quotes_and_backslashes_saved_as_is(self):
        """引号与反斜杠按传入字符串保存，按 JSON 规则转义而非再解释。"""
        text = '他说："走"\n路径是 C:\\林区\\深处'
        result, stdout = self.run_and_assert_set_text(
            SAMPLE, "forest", text,
            {
                "start": "start",
                "nodes": [
                    {"id": "start", "text": "你来到岔路口。", "options": [
                        {"text": "向左走", "target": "forest"},
                        {"text": "向右走", "target": "river"},
                    ]},
                    {"id": "forest", "text": text, "options": []},
                    {"id": "river", "text": "你到了河边。", "options": []},
                ],
            },
        )
        # 单行 JSON 中换行被转义为 \n，反斜杠转义为 \\，引号转义为 \"。
        self.assertIn('他说：\\"走\\"\\n路径是 C:\\\\林区\\\\深处', stdout)

    def test_multiline_text_newline_escaped_on_single_line(self):
        """正文中的换行按 JSON 规则转义；整个输出仍只有结尾一个换行。"""
        text = "第一行\n第二行\n第三行"
        result, stdout = self.run_and_assert_set_text(
            SAMPLE, "forest", text,
            {
                "start": "start",
                "nodes": [
                    {"id": "start", "text": "你来到岔路口。", "options": [
                        {"text": "向左走", "target": "forest"},
                        {"text": "向右走", "target": "river"},
                    ]},
                    {"id": "forest", "text": text, "options": []},
                    {"id": "river", "text": "你到了河边。", "options": []},
                ],
            },
        )
        self.assertEqual(stdout.count("\\n"), 2)

    def test_text_not_interpreted_as_json_or_path_or_instruction(self):
        """形似 JSON、文件路径或指令的正文都只是字符串。"""
        cases = ['{"a": 1}', "../secret.json", "--node", "null", "123",
                 "rm -rf /", "true"]
        for text in cases:
            data = self.load_sample_data()
            path = self.make_sample(data, name="case_{}.json".format(
                cases.index(text)))
            expected = self.load_sample_data()
            expected["nodes"][1]["text"] = text
            self.run_and_assert_set_text(path, "forest", text, expected)

    def test_same_text_outputs_equivalent_object(self):
        """新正文与原值完全相同时成功，输出与原对象等价的 JSON。"""
        original = self.load_sample_data()
        result, _ = self.run_and_assert_set_text(
            SAMPLE, "forest", "你到了森林。", original
        )
        self.assertEqual(json.loads(result.stdout[:-1]), original)

    def test_extra_fields_and_order_preserved(self):
        """顶层、节点与选项上的额外字段原样保留，数组顺序不变；
        其他节点文字与全部选项不动。"""
        data = {
            "start": "s",
            "title": "番外",
            "nodes": [
                {"id": "s", "text": "起点", "style": "bold", "options": [
                    {"text": "去 a", "target": "a", "tone": "quiet"},
                ]},
                {"id": "a", "text": "甲", "options": [], "note": ["x", 1]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_set_text(path, "a", "新甲", {
            "start": "s",
            "title": "番外",
            "nodes": [
                {"id": "s", "text": "起点", "style": "bold", "options": [
                    {"text": "去 a", "target": "a", "tone": "quiet"},
                ]},
                {"id": "a", "text": "新甲", "options": [], "note": ["x", 1]},
            ],
        })

    def test_only_target_node_text_changes(self):
        """同时存在多个节点时，只改选中节点的 text，其余文字不变。"""
        data = {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "选项甲", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "选项乙", "target": "c"},
                ]},
                {"id": "c", "text": "丙", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_set_text(path, "b", "乙改", {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "选项甲", "target": "b"},
                ]},
                {"id": "b", "text": "乙改", "options": [
                    {"text": "选项乙", "target": "c"},
                ]},
                {"id": "c", "text": "丙", "options": []},
            ],
        })

    def test_node_id_matched_exactly_with_surrounding_whitespace(self):
        """编号按原字符串精确匹配、首尾空白不裁剪：' a ' 与 'a' 互不干扰。"""
        data = {
            "start": " a ",
            "nodes": [
                {"id": " a ", "text": "带空格", "options": [
                    {"text": "去不带空格", "target": "a"},
                ]},
                {"id": "a", "text": "不带空格", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_set_text(path, " a ", "新的带空格", {
            "start": " a ",
            "nodes": [
                {"id": " a ", "text": "新的带空格", "options": [
                    {"text": "去不带空格", "target": "a"},
                ]},
                {"id": "a", "text": "不带空格", "options": []},
            ],
        })

    def test_option_like_node_id_accepted_as_value(self):
        """形似选项的节点编号（如 -x）照收为值，按节点不存在处理。"""
        result = self.run_and_assert_fail(
            SAMPLE, "-x", "正文", ["文件中不存在编号为 '-x' 的节点"]
        )
        self.assertNotIn("用法", result.stderr.decode("utf-8"))

    def test_option_like_text_accepted_as_value(self):
        """形似选项的正文（如 --text、-y）原样保存为新正文。"""
        self.run_and_assert_set_text(SAMPLE, "forest", "--text", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "--text", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        self.run_and_assert_set_text(SAMPLE, "forest", "-y", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "-y", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })

    def test_no_result_file_created(self):
        """成功修改正文不在输入文件旁创建任何结果文件。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        before_entries = set(p.name for p in self.tmp_dir.iterdir())
        result = run_set_text(path, "forest", "林间很安静。")
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        after_entries = set(p.name for p in self.tmp_dir.iterdir())
        self.assertEqual(before_entries, after_entries, "不应创建结果文件")


class TestSetNodeTextFailure(SetNodeTextTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_node_uses_existing_message(self):
        """节点不存在：沿用节点不存在说明，含编号原值。"""
        result = self.run_and_assert_fail(
            SAMPLE, "ghost", "林间很安静。",
            ["文件中不存在编号为 'ghost' 的节点"],
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_missing_node_id_keeps_surrounding_whitespace(self):
        """编号首尾空白不裁剪，错误说明中按原值引用。"""
        self.run_and_assert_fail(
            SAMPLE, " forest ", "正文",
            ["文件中不存在编号为 ' forest ' 的节点"],
        )

    def test_invalid_structure_in_unreachable_node_fails_validation(self):
        """不可达 side 节点缺少 text：沿用“校验失败：”并定位 nodes[3].text，
        即使问题位于不可达节点也先于正文修改报出。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "options": [
                {"text": "去森林", "target": "forest"}]}
        )
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path, "forest", "林间很安静。",
            ["校验失败：", "nodes[3].text"],
        )
        self.assertTrue(
            result.stderr.decode("utf-8").startswith("校验失败："),
            "标准错误应以“校验失败：”开头",
        )

    def test_dangling_target_in_unreachable_node_fails_validation(self):
        """不可达 side 节点选项 target 指向不存在的 ghost：定位到
        nodes[3].options[0].target 并点名 ghost，不输出修改结果。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路",
             "options": [{"text": "去虚无", "target": "ghost"}]}
        )
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path, "forest", "林间很安静。",
            ["校验失败：", "nodes[3].options[0].target", "ghost"],
        )
        self.assertEqual(result.stdout, b"")

    def test_validation_runs_before_node_lookup(self):
        """整份校验失败先于节点查找：文件非法时即使节点也不存在，
        仍只报校验失败，不能借替换正文绕过原文件校验。"""
        data = self.load_sample_data()
        data["start"] = "missing"
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path, "ghost", "正文", ["校验失败：", "start", "missing"]
        )
        self.assertNotIn("文件中不存在编号", result.stderr.decode("utf-8"))

    def test_json_syntax_error_uses_existing_category(self):
        """语法错误文件：沿用既有 JSON 语法错误分类，信息含路径与行列。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{\n  !", encoding="utf-8")
        result = self.run_and_assert_fail(
            broken, "forest", "正文",
            ["JSON 语法错误", "第 2 行第 3 列", str(broken)],
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_utf8_decode_error_uses_existing_category(self):
        """UTF-8 解码失败：沿用既有分类且信息含路径。"""
        bad = self.tmp_dir / "bad.json"
        bad.write_bytes(b"\xff")
        self.run_and_assert_fail(bad, "forest", "正文",
                                 ["UTF-8 解码失败", str(bad)])

    def test_unreadable_file_uses_existing_category(self):
        """路径不存在：沿用既有无法读取文件分类，含路径且不创建该文件。"""
        missing = self.tmp_dir / "never_created.json"
        result = run_set_text(missing, "forest", "正文")
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(missing), stderr)
        self.assertFalse(missing.exists(), "改正文不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
