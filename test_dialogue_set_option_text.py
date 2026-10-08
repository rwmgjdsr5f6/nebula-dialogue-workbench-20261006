# -*- coding: utf-8 -*-
"""dialogue.py 单个选项文字修改（set-option-text）命令行回归测试。

以 sample.json 为基础派生独立临时副本，覆盖先整份校验后替换选项文字的
成功路径：样例中 start 第 1 个选项文字改为「进入森林」的给定结果（仅
nodes[0].options[0].text 变化、其余与原对象一致）、只改选中选项而
start/节点编号与正文/全部 target/其他选项/各层额外字段/节点与选项数组
顺序原样、起点与不可达来源节点的选项均可修改、自引用与合法循环不阻止
命令、新文字与原值相同输出等价 JSON、空字符串/纯空白/中文/引号/反斜杠/
换行按传入字符串原样保存、形似 JSON、路径或参数的文字照收为值、中文
不转义、文字中的换行按 JSON 规则转义、来源编号首尾空白精确匹配；以及
来源节点不存在沿用既有说明、选项编号非整数、结尾节点无选项、编号越界
及来源→整数→结尾→范围的检查顺序、未选分支及不可达节点非法时先报告
整份校验失败、文件读取与 JSON 语法错误沿用既有分类等失败边界。参数
格式错误另有 test_dialogue_set_option_text_args.py。

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

# sample.json 把起点第 1 个选项文字改为「进入森林」的验收结果：仅
# nodes[0].options[0].text 变化，其余内容与原对象完全一致。
EXPECTED_ENTER_FOREST = {
    "start": "start",
    "nodes": [
        {"id": "start", "text": "你来到岔路口。", "options": [
            {"text": "进入森林", "target": "forest"},
            {"text": "向右走", "target": "river"},
        ]},
        {"id": "forest", "text": "你到了森林。", "options": []},
        {"id": "river", "text": "你到了河边。", "options": []},
    ],
}


def run_set_option_text(path, source_id, choice, new_text):
    """以命令行方式执行 set-option-text，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "set-option-text", str(path),
         "--node", source_id, "--choice", str(choice), "--text", new_text],
        capture_output=True,
    )


class SetOptionTextTestCase(unittest.TestCase):
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

    def run_and_assert_set_option_text(self, path, source_id, choice, new_text,
                                       expected_object):
        """成功：退出码 0、标准错误为空，输出为修改后的完整对话对象，
        单行 JSON 加一个结尾换行；对象按解析后内容核对。"""
        before = path.read_bytes()
        result = run_set_option_text(path, source_id, choice, new_text)
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
        return result

    def run_and_assert_fail(self, path, source_id, choice, new_text,
                            expected_parts):
        """失败：退出码 2、标准输出为空、标准错误包含各片段且无调用栈。"""
        before = path.read_bytes()
        result = run_set_option_text(path, source_id, choice, new_text)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestSetOptionTextSuccess(SetOptionTextTestCase):
    """成功路径：整份校验通过后输出修改后的完整对话对象。"""

    def test_sample_start_choice_1_enters_forest(self):
        """验收用例：start 第 1 个选项文字改为「进入森林」，其余与样例等价。"""
        result = self.run_and_assert_set_option_text(
            SAMPLE, "start", 1, "进入森林", EXPECTED_ENTER_FOREST
        )
        # 中文原样输出，不转义。
        self.assertIn("进入森林", result.stdout.decode("utf-8"))
        self.assertNotIn("\\u", result.stdout.decode("utf-8"))

    def test_only_selected_option_text_changes(self):
        """只改选中选项的 text：同节点另一选项、其他节点内容与 start 保持原样。"""
        data = {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去 b", "target": "b"},
                    {"text": "去 c", "target": "c"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "去 c", "target": "c"},
                ]},
                {"id": "c", "text": "丙", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_set_option_text(path, "a", 1, "改走 b 新路", {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "改走 b 新路", "target": "b"},
                    {"text": "去 c", "target": "c"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "去 c", "target": "c"},
                ]},
                {"id": "c", "text": "丙", "options": []},
            ],
        })

    def test_target_of_selected_option_kept(self):
        """替换文字不改分支关系：选中选项的 target 与其余 target 原样保留。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_set_option_text(
            path, "start", 1, "进入森林", EXPECTED_ENTER_FOREST
        )
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["nodes"][0]["options"][0]["target"], "forest")
        self.assertEqual(parsed["nodes"][0]["options"][1]["target"], "river")

    def test_start_and_node_ids_and_node_text_kept(self):
        """修改选项文字不改动 start、节点编号与任何节点正文。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_set_option_text(
            path, "start", 1, "进入森林", EXPECTED_ENTER_FOREST
        )
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["start"], "start")
        self.assertEqual([n["id"] for n in parsed["nodes"]],
                         ["start", "forest", "river"])
        self.assertEqual(parsed["nodes"][0]["text"], "你来到岔路口。")

    def test_second_option_editable(self):
        """第 2 个选项同样可改，第 1 个选项保持原样。"""
        self.run_and_assert_set_option_text(
            SAMPLE, "start", 2, "沿河边走", {
                "start": "start",
                "nodes": [
                    {"id": "start", "text": "你来到岔路口。", "options": [
                        {"text": "向左走", "target": "forest"},
                        {"text": "沿河边走", "target": "river"},
                    ]},
                    {"id": "forest", "text": "你到了森林。", "options": []},
                    {"id": "river", "text": "你到了河边。", "options": []},
                ],
            }
        )

    def test_unreachable_source_option_editable(self):
        """不可达来源节点的选项文字仍可修改。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路入口", "options": [
                {"text": "自环", "target": "side"}]}
        )
        path = self.make_sample(data)
        self.run_and_assert_set_option_text(path, "side", 1, "留在旁路", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
                {"id": "side", "text": "旁路入口", "options": [
                    {"text": "留在旁路", "target": "side"}]},
            ],
        })

    def test_self_reference_and_cycle_unaffected(self):
        """自引用与合法循环中的选项可改文字，target 不变，命令正常结束。"""
        data = {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "自环", "target": "a"},
                    {"text": "去 b", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "回 a", "target": "a"},
                ]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_set_option_text(path, "b", 1, "返回甲", {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "自环", "target": "a"},
                    {"text": "去 b", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "返回甲", "target": "a"},
                ]},
            ],
        })

    def test_same_text_outputs_equivalent_object(self):
        """新文字与原值完全相同时成功，输出与原对象等价的 JSON。"""
        original = json.loads(SAMPLE.read_text(encoding="utf-8"))
        result = self.run_and_assert_set_option_text(
            SAMPLE, "start", 1, "向左走", original
        )
        self.assertEqual(json.loads(result.stdout[:-1]), original)

    def test_empty_text_saved_verbatim(self):
        """空字符串文字按原样保存。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_set_option_text(path, "start", 1, "", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["nodes"][0]["options"][0]["text"], "")

    def test_whitespace_only_text_saved_verbatim(self):
        """纯空白文字按原样保存，不裁剪。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_set_option_text(path, "start", 2, "  \t ", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "  \t ", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["nodes"][0]["options"][1]["text"], "  \t ")

    def test_quotes_backslash_and_newline_saved_verbatim(self):
        """引号、反斜杠与换行按传入字符串原样保存；换行按 JSON 规则转义。"""
        new_text = '他说："看\\这里"\n第二行'
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_set_option_text(
            path, "start", 1, new_text, {
                "start": "start",
                "nodes": [
                    {"id": "start", "text": "你来到岔路口。", "options": [
                        {"text": new_text, "target": "forest"},
                        {"text": "向右走", "target": "river"},
                    ]},
                    {"id": "forest", "text": "你到了森林。", "options": []},
                    {"id": "river", "text": "你到了河边。", "options": []},
                ],
            }
        )
        stdout = result.stdout.decode("utf-8")
        # 文字中的换行在单行 JSON 里以 \\n 转义形式出现，输出本身只有一行。
        self.assertIn("\\n", stdout)
        parsed = json.loads(stdout[:-1])
        self.assertEqual(parsed["nodes"][0]["options"][0]["text"], new_text)

    def test_json_like_text_not_interpreted(self):
        """形似 JSON 的文字按字符串原样保存，不被解析。"""
        new_text = '{"text": "x", "target": "y"}'
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_set_option_text(
            path, "start", 1, new_text, {
                "start": "start",
                "nodes": [
                    {"id": "start", "text": "你来到岔路口。", "options": [
                        {"text": new_text, "target": "forest"},
                        {"text": "向右走", "target": "river"},
                    ]},
                    {"id": "forest", "text": "你到了森林。", "options": []},
                    {"id": "river", "text": "你到了河边。", "options": []},
                ],
            }
        )
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["nodes"][0]["options"][0]["text"], new_text)

    def test_path_like_text_not_interpreted(self):
        """形似文件路径的文字按字符串原样保存，不触发任何文件操作。"""
        new_text = "./some/path.json"
        data = self.load_sample_data()
        path = self.make_sample(data)
        self.run_and_assert_set_option_text(
            path, "start", 1, new_text, {
                "start": "start",
                "nodes": [
                    {"id": "start", "text": "你来到岔路口。", "options": [
                        {"text": "./some/path.json", "target": "forest"},
                        {"text": "向右走", "target": "river"},
                    ]},
                    {"id": "forest", "text": "你到了森林。", "options": []},
                    {"id": "river", "text": "你到了河边。", "options": []},
                ],
            }
        )

    def test_option_like_text_value_accepted(self):
        """形似参数的文字（如 --node）照收为值，原样保存为选项文字。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        self.run_and_assert_set_option_text(path, "start", 1, "--choice", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "--choice", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })

    def test_extra_fields_and_array_order_kept(self):
        """顶层、节点、选项上的额外字段及节点与选项数组顺序全部原样保留。"""
        data = {
            "start": "s",
            "note": "顶层备注",
            "nodes": [
                {"id": "s", "text": "旧文", "options": [
                    {"text": "旧选项", "target": "b", "tag": "选项标记"},
                    {"text": "保留项", "target": "b", "keep": 1},
                ], "marker": "节点标记"},
                {"id": "b", "text": "乙", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_set_option_text(path, "s", 1, "新选项", {
            "start": "s",
            "note": "顶层备注",
            "nodes": [
                {"id": "s", "text": "旧文", "options": [
                    {"text": "新选项", "target": "b", "tag": "选项标记"},
                    {"text": "保留项", "target": "b", "keep": 1},
                ], "marker": "节点标记"},
                {"id": "b", "text": "乙", "options": []},
            ],
        })

    def test_source_id_matched_exactly_with_whitespace(self):
        """来源编号按原字符串精确匹配、首尾空白保留。"""
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
        self.run_and_assert_set_option_text(path, " a ", 1, "改选文字", {
            "start": " a ",
            "nodes": [
                {"id": " a ", "text": "带空格", "options": [
                    {"text": "改选文字", "target": "a"},
                ]},
                {"id": "a", "text": "不带空格", "options": []},
            ],
        })

    def test_choice_integer_parsing_follows_preview(self):
        """编号整数解析沿用 preview：01 与带首尾空白的 1 都等同于 1。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        expected = EXPECTED_ENTER_FOREST
        self.run_and_assert_set_option_text(path, "start", "01", "进入森林",
                                            expected)
        data2 = self.load_sample_data()
        path2 = self.make_sample(data2, name="case2.json")
        self.run_and_assert_set_option_text(path2, "start", " 1 ", "进入森林",
                                            expected)

    def test_no_result_file_created(self):
        """成功修改不在输入文件旁创建任何结果文件。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        before_entries = set(p.name for p in self.tmp_dir.iterdir())
        result = run_set_option_text(path, "start", 1, "进入森林")
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        after_entries = set(p.name for p in self.tmp_dir.iterdir())
        self.assertEqual(before_entries, after_entries, "不应创建结果文件")


class TestSetOptionTextFailure(SetOptionTextTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_forest_choice_1_reports_ending_no_options(self):
        """验收用例：对结尾 forest 选择 1 报结尾无有效选项，不输出 JSON。"""
        result = self.run_and_assert_fail(
            SAMPLE, "forest", 1, "新文字",
            ["--choice 1", "forest", "没有有效选项"],
        )
        self.assertNotIn(
            "岔路口".encode("utf-8"), result.stdout, "结尾报错时不应输出 JSON"
        )

    def test_missing_source_node_uses_existing_message(self):
        """来源节点不存在：沿用既有说明，含编号原值。"""
        result = self.run_and_assert_fail(
            SAMPLE, "ghost", 1, "新文字",
            ["文件中不存在编号为 'ghost' 的节点"],
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_missing_source_keeps_surrounding_whitespace(self):
        """来源编号首尾空白不裁剪，错误说明中按原值引用。"""
        self.run_and_assert_fail(
            SAMPLE, " start ", 1, "新文字",
            ["文件中不存在编号为 ' start ' 的节点"],
        )

    def test_choice_not_an_integer_uses_preview_message(self):
        """非整数编号：沿用显式 --node 的 preview 解析失败说明。"""
        result = self.run_and_assert_fail(
            SAMPLE, "start", "abc", "新文字",
            ["'abc'", "无法解析为整数", "出发节点编号为 'start'"],
        )
        stderr = result.stderr.decode("utf-8")
        self.assertEqual(
            stderr,
            "--choice 的值 'abc' 无法解析为整数（出发节点编号为 'start'）\n",
        )

    def test_choice_zero_out_of_range_uses_preview_message(self):
        """编号越界：沿用显式 --node 的 preview 范围说明。"""
        result = self.run_and_assert_fail(
            SAMPLE, "start", 0, "新文字",
            ["--choice 0", "start", "1 到 2"],
        )
        self.assertEqual(
            result.stderr.decode("utf-8"),
            "--choice 0 不在出发节点 'start' 的有效选项编号范围 1 到 2 内\n",
        )

    def test_choice_three_out_of_range_uses_preview_message(self):
        result = self.run_and_assert_fail(
            SAMPLE, "start", 3, "新文字",
            ["--choice 3", "1 到 2"],
        )

    def test_source_missing_reported_before_integer_parse(self):
        """来源节点不存在先于整数解析报告。"""
        self.run_and_assert_fail(
            SAMPLE, "ghost", "abc", "新文字",
            ["文件中不存在编号为 'ghost' 的节点"],
        )

    def test_integer_parse_reported_before_ending(self):
        """结尾节点上给非整数：整数解析失败先于结尾无选项报告。"""
        self.run_and_assert_fail(
            SAMPLE, "forest", "abc", "新文字",
            ["无法解析为整数", "forest"],
        )

    def test_ending_reported_before_range(self):
        """结尾节点上给越界整数：仍报结尾无有效选项，而非范围越界。"""
        result = self.run_and_assert_fail(
            SAMPLE, "forest", 3, "新文字",
            ["forest", "没有有效选项"],
        )
        self.assertNotIn("有效选项编号范围", result.stderr.decode("utf-8"))

    def test_dangling_target_on_selected_option_fails_validation(self):
        """待改选项自身的 target 悬空：仍先报整份校验失败，不替换文字。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0]["target"] = "ghost"
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path, "start", 1, "新文字",
            ["校验失败：", "nodes[0].options[0].target", "ghost"],
        )
        self.assertTrue(
            result.stderr.decode("utf-8").startswith("校验失败："),
            "标准错误应以“校验失败：”开头",
        )

    def test_dangling_target_on_unchosen_branch_fails_validation(self):
        """未选中分支的悬空引用同样先报整份校验失败。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][1]["target"] = "ghost"
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "start", 1, "新文字",
            ["校验失败：", "nodes[0].options[1].target", "ghost"],
        )

    def test_invalid_unreachable_node_fails_validation(self):
        """不可达节点选项 target 悬空：先于文字替换报出整份校验失败。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路",
             "options": [{"text": "去虚无", "target": "ghost"}]}
        )
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "start", 1, "新文字",
            ["校验失败：", "nodes[3].options[0].target", "ghost"],
        )

    def test_missing_field_fails_validation_before_edit(self):
        """来源节点缺少 options 字段：属于整份校验失败，先于来源检查。"""
        data = self.load_sample_data()
        del data["nodes"][1]["options"]
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "forest", 1, "新文字",
            ["校验失败：", "nodes[1].options"],
        )

    def test_json_syntax_error_uses_existing_category(self):
        """语法错误文件：沿用既有 JSON 语法错误分类，信息含路径与行列。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{\n  !", encoding="utf-8")
        self.run_and_assert_fail(
            broken, "start", 1, "新文字",
            ["JSON 语法错误", "第 2 行第 3 列", str(broken)],
        )

    def test_utf8_decode_error_uses_existing_category(self):
        """UTF-8 解码失败：沿用既有分类且信息含路径。"""
        bad = self.tmp_dir / "bad.json"
        bad.write_bytes(b"\xff")
        self.run_and_assert_fail(bad, "start", 1, "新文字",
                                 ["UTF-8 解码失败", str(bad)])

    def test_unreadable_file_uses_existing_category(self):
        """路径不存在：沿用既有无法读取文件分类，含路径且不创建该文件。"""
        missing = self.tmp_dir / "never_created.json"
        result = run_set_option_text(missing, "start", 1, "新文字")
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(missing), stderr)
        self.assertFalse(missing.exists(), "替换文字不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
