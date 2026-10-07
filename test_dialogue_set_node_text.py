# -*- coding: utf-8 -*-
"""dialogue.py 单个节点正文修改（set-node-text）命令行回归测试。

以 sample.json 为基础派生独立临时副本，覆盖先整份校验后替换正文的成功路径：
样例中 forest 正文改为「林间很安静。」的给定结果（仅该节点 text 变化、
其余与原对象一致）、只改选中节点而 start/节点编号/全部选项/其他节点文字/
各层额外字段/节点与选项数组顺序原样、起点与结尾与不可达节点均可修改、
自引用与合法循环不阻止命令、新正文与原值相同输出等价 JSON、空字符串/
纯空白/中文/引号/反斜杠/换行按传入字符串原样保存、形似参数的编号与正文
照收为值、中文不转义、正文中的换行按 JSON 规则转义、节点编号首尾空白
精确匹配；以及节点不存在沿用既有说明、未选分支及不可达节点非法时先报告
整份校验失败、文件读取与 JSON 语法错误沿用既有分类等失败边界。参数格式
错误另有 test_dialogue_set_node_text_args.py。

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

# sample.json 把 forest 正文改为「林间很安静。」的验收结果：仅该节点的
# text 变化，其余内容与原对象完全一致。
EXPECTED_FOREST_QUIET = {
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
        单行 JSON 加一个结尾换行；对象按解析后内容核对。"""
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
        return result

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

    def test_sample_forest_text_changed(self):
        """验收用例：forest 正文改为「林间很安静。」，其余与样例等价。"""
        result = self.run_and_assert_set_text(
            SAMPLE, "forest", "林间很安静。", EXPECTED_FOREST_QUIET
        )
        # 中文原样输出，不转义。
        self.assertIn("林间很安静。", result.stdout.decode("utf-8"))
        self.assertNotIn("\\u", result.stdout.decode("utf-8"))

    def test_only_selected_node_text_changes(self):
        """只改选中节点的 text：其他节点文字、全部选项与 start 保持原样。"""
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
        self.run_and_assert_set_text(path, "b", "新正文", {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去 b", "target": "b"},
                    {"text": "去 c", "target": "c"},
                ]},
                {"id": "b", "text": "新正文", "options": [
                    {"text": "去 c", "target": "c"},
                ]},
                {"id": "c", "text": "丙", "options": []},
            ],
        })

    def test_start_node_editable(self):
        """起点节点的正文同样可以修改。"""
        result = self.run_and_assert_set_text(
            SAMPLE, "start", "新的起点。", {
                "start": "start",
                "nodes": [
                    {"id": "start", "text": "新的起点。", "options": [
                        {"text": "向左走", "target": "forest"},
                        {"text": "向右走", "target": "river"},
                    ]},
                    {"id": "forest", "text": "你到了森林。", "options": []},
                    {"id": "river", "text": "你到了河边。", "options": []},
                ],
            }
        )
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["start"], "start")

    def test_unreachable_node_editable(self):
        """不可达节点的正文仍可修改。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路入口", "options": [
                {"text": "自环", "target": "side"}]}
        )
        path = self.make_sample(data)
        self.run_and_assert_set_text(path, "side", "旁路新文。", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
                {"id": "side", "text": "旁路新文。", "options": [
                    {"text": "自环", "target": "side"}]},
            ],
        })

    def test_self_reference_and_cycle_unaffected(self):
        """自引用与合法循环中的节点可改正文，命令正常结束。"""
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
        self.run_and_assert_set_text(path, "b", "循环中的新正文", {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "自环", "target": "a"},
                    {"text": "去 b", "target": "b"},
                ]},
                {"id": "b", "text": "循环中的新正文", "options": [
                    {"text": "回 a", "target": "a"},
                ]},
            ],
        })

    def test_same_text_outputs_equivalent_object(self):
        """新正文与原值完全相同时成功，输出与原对象等价的 JSON。"""
        original = json.loads(SAMPLE.read_text(encoding="utf-8"))
        result = self.run_and_assert_set_text(
            SAMPLE, "forest", "你到了森林。", original
        )
        self.assertEqual(json.loads(result.stdout[:-1]), original)

    def test_empty_text_saved_verbatim(self):
        """空字符串正文按原样保存。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_set_text(path, "forest", "", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["nodes"][1]["text"], "")

    def test_whitespace_only_text_saved_verbatim(self):
        """纯空白正文按原样保存，不裁剪。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_set_text(path, "river", "  \t ", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "  \t ", "options": []},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["nodes"][2]["text"], "  \t ")

    def test_quotes_backslash_and_newline_saved_verbatim(self):
        """引号、反斜杠与换行按传入字符串原样保存；换行按 JSON 规则转义。"""
        new_text = '他说："看\\这里"\n第二行'
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_set_text(path, "forest", new_text, {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": new_text, "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        stdout = result.stdout.decode("utf-8")
        # 正文中的换行在单行 JSON 里以 \\n 转义形式出现，输出本身只有一行。
        self.assertIn("\\n", stdout)
        parsed = json.loads(stdout[:-1])
        self.assertEqual(parsed["nodes"][1]["text"], new_text)

    def test_json_like_text_not_interpreted(self):
        """形似 JSON 的正文按字符串原样保存，不被解析。"""
        new_text = '{"id": "x", "options": []}'
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_set_text(path, "forest", new_text, {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": new_text, "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["nodes"][1]["text"], new_text)

    def test_option_like_values_accepted_as_values(self):
        """形似参数的编号与正文照收为值：编号按节点不存在处理，正文原样保存。"""
        # 正文位置形似选项的记号照收为正文。
        data = self.load_sample_data()
        path = self.make_sample(data)
        self.run_and_assert_set_text(path, "forest", "--node", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "--node", "options": []},
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
                    {"text": "去 b", "target": "b", "tag": "选项标记"},
                ], "marker": "节点标记"},
                {"id": "b", "text": "乙", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_set_text(path, "s", "新文", {
            "start": "s",
            "note": "顶层备注",
            "nodes": [
                {"id": "s", "text": "新文", "options": [
                    {"text": "去 b", "target": "b", "tag": "选项标记"},
                ], "marker": "节点标记"},
                {"id": "b", "text": "乙", "options": []},
            ],
        })

    def test_node_id_matched_exactly_with_whitespace(self):
        """节点编号按原字符串精确匹配、首尾空白保留。"""
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
        self.run_and_assert_set_text(path, " a ", "改了带空格", {
            "start": " a ",
            "nodes": [
                {"id": " a ", "text": "改了带空格", "options": [
                    {"text": "去不带空格", "target": "a"},
                ]},
                {"id": "a", "text": "不带空格", "options": []},
            ],
        })

    def test_no_result_file_created(self):
        """成功修改不在输入文件旁创建任何结果文件。"""
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
        """节点不存在：沿用既有说明，含编号原值。"""
        result = self.run_and_assert_fail(
            SAMPLE, "ghost", "新正文",
            ["文件中不存在编号为 'ghost' 的节点"],
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_missing_node_keeps_surrounding_whitespace(self):
        """编号首尾空白不裁剪，错误说明中按原值引用。"""
        self.run_and_assert_fail(
            SAMPLE, " forest ", "新正文",
            ["文件中不存在编号为 ' forest ' 的节点"],
        )

    def test_dangling_target_fails_validation_before_edit(self):
        """任一选项 target 悬空：仍先报整份校验失败，不做正文替换。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0]["target"] = "ghost"
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path, "forest", "新正文",
            ["校验失败：", "nodes[0].options[0].target", "ghost"],
        )
        self.assertTrue(
            result.stderr.decode("utf-8").startswith("校验失败："),
            "标准错误应以“校验失败：”开头",
        )

    def test_invalid_unreachable_node_fails_validation(self):
        """不可达节点结构非法：先于正文替换报出整份校验失败。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路",
             "options": [{"text": "去虚无", "target": "ghost"}]}
        )
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "forest", "新正文",
            ["校验失败：", "nodes[3].options[0].target", "ghost"],
        )

    def test_missing_field_fails_validation_before_edit(self):
        """目标节点缺少 text 字段：属于整份校验失败，先于节点查找。"""
        data = self.load_sample_data()
        del data["nodes"][1]["text"]
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "forest", "新正文",
            ["校验失败：", "nodes[1].text"],
        )

    def test_json_syntax_error_uses_existing_category(self):
        """语法错误文件：沿用既有 JSON 语法错误分类，信息含路径与行列。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{\n  !", encoding="utf-8")
        self.run_and_assert_fail(
            broken, "forest", "新正文",
            ["JSON 语法错误", "第 2 行第 3 列", str(broken)],
        )

    def test_utf8_decode_error_uses_existing_category(self):
        """UTF-8 解码失败：沿用既有分类且信息含路径。"""
        bad = self.tmp_dir / "bad.json"
        bad.write_bytes(b"\xff")
        self.run_and_assert_fail(bad, "forest", "新正文",
                                 ["UTF-8 解码失败", str(bad)])

    def test_unreadable_file_uses_existing_category(self):
        """路径不存在：沿用既有无法读取文件分类，含路径且不创建该文件。"""
        missing = self.tmp_dir / "never_created.json"
        result = run_set_text(missing, "forest", "新正文")
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(missing), stderr)
        self.assertFalse(missing.exists(), "修改正文不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
