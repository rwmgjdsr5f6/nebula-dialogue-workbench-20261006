# -*- coding: utf-8 -*-
"""dialogue.py 单个选项追加（add-option）命令行回归测试。

以 sample.json 为基础派生独立临时副本，覆盖先整份校验后追加的成功路径：
样例中 start 末尾追加文字「再去森林」、目标 forest 的给定结果（起点有
三个选项，新增项排在末尾，其余与原对象一致），并把输出作为 preview 的
对话输入验证选择 3 输出「你到了森林。」；空 options（结尾节点）也能
追加、原结尾随之成为分支节点；重复文字或目标不去重、每次只新增一项、
已有选项编号不变、新编号为追加后的数组长度；只追加一项而 start/节点
编号与正文/已有选项/额外字段/数组顺序原样；不可达来源与不可达目标
可用、自引用与合法循环；空字符串/纯空白/中文/引号/反斜杠/换行按传入
字符串原样保存，形似 JSON、文件路径或选项的文字不另作解释；中文不
转义、文字换行按 JSON 规则转义；来源与目标编号首尾空白精确匹配；
不创建结果文件。以及来源或目标节点不存在（目标 missing 时失败且不
输出对话）、未选分支及不可达节点非法时先报告整份校验失败、文件读取
与 JSON 语法错误沿用既有分类等失败边界。参数格式错误另有
test_dialogue_add_option_args.py。

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

# sample.json 在起点末尾追加「再去森林」→ forest 的验收结果：起点有三个
# 选项，新增项排在末尾，其余内容与原对象完全一致。
EXPECTED_THREE_OPTIONS = {
    "start": "start",
    "nodes": [
        {"id": "start", "text": "你来到岔路口。", "options": [
            {"text": "向左走", "target": "forest"},
            {"text": "向右走", "target": "river"},
            {"text": "再去森林", "target": "forest"},
        ]},
        {"id": "forest", "text": "你到了森林。", "options": []},
        {"id": "river", "text": "你到了河边。", "options": []},
    ],
}


def run_add_option(path, source_id, text, target_id):
    """以命令行方式执行 add-option，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "add-option", str(path),
         "--node", source_id, "--text", text, "--to", target_id],
        capture_output=True,
    )


class AddOptionTestCase(unittest.TestCase):
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

    def run_and_assert_add(self, path, source_id, text, target_id,
                           expected_object):
        """成功：退出码 0、标准错误为空，输出为修改后的完整对话对象，
        单行 JSON 加一个结尾换行；对象按解析后内容核对。"""
        before = path.read_bytes()
        result = run_add_option(path, source_id, text, target_id)
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

    def run_and_assert_fail(self, path, source_id, text, target_id,
                            expected_parts):
        """失败：退出码 2、标准输出为空、标准错误包含各片段且无调用栈。"""
        before = path.read_bytes()
        result = run_add_option(path, source_id, text, target_id)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestAddOptionSuccess(AddOptionTestCase):
    """成功路径：整份校验通过后输出修改后的完整对话对象。"""

    def test_sample_start_add_forest_option(self):
        """验收用例：起点末尾追加「再去森林」→ forest，共三个选项。"""
        result = self.run_and_assert_add(
            SAMPLE, "start", "再去森林", "forest", EXPECTED_THREE_OPTIONS
        )
        # 中文原样输出，不转义。
        self.assertIn("再去森林", result.stdout.decode("utf-8"))
        self.assertNotIn("\\u", result.stdout.decode("utf-8"))

    def test_output_is_preview_input_choice_3(self):
        """验收用例：输出作为 preview 的对话输入，选择 3 到达森林。"""
        added = subprocess.run(
            [sys.executable, str(DIALOGUE), "add-option", str(SAMPLE),
             "--node", "start", "--text", "再去森林", "--to", "forest"],
            capture_output=True,
        )
        self.assertEqual(added.returncode, 0)
        derived = self.tmp_dir / "derived.json"
        derived.write_bytes(added.stdout)
        preview = subprocess.run(
            [sys.executable, str(DIALOGUE), "preview", str(derived),
             "--choice", "3"],
            capture_output=True,
        )
        self.assertEqual(preview.returncode, 0, "stderr: {!r}".format(
            preview.stderr))
        self.assertEqual(preview.stderr, b"")
        self.assertEqual(preview.stdout.decode("utf-8"), "你到了森林。\n")

    def test_new_option_appended_at_end_with_only_text_and_target(self):
        """新增项排在 options 末尾，且只含 text 与 target 两个键。"""
        result = run_add_option(SAMPLE, "start", "再去森林", "forest")
        self.assertEqual(result.returncode, 0)
        parsed = json.loads(result.stdout[:-1])
        new_option = parsed["nodes"][0]["options"][2]
        self.assertEqual(new_option, {"text": "再去森林", "target": "forest"})
        self.assertEqual(
            list(new_option.keys()), ["text", "target"],
            "新选项应只含 text 与 target，且顺序为 text 在前",
        )

    def test_empty_options_becomes_branch_node(self):
        """空 options（结尾节点）也能追加，原结尾随之成为分支节点。"""
        self.run_and_assert_add(SAMPLE, "forest", "回望路口", "start", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": [
                    {"text": "回望路口", "target": "start"}]},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })

    def test_duplicate_text_and_target_not_deduped(self):
        """文字与目标都与已有选项重复时不去重，每次只新增一项。"""
        first = self.run_and_assert_add(SAMPLE, "start", "向左走", "forest", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                    {"text": "向左走", "target": "forest"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        # 第二次以第一次的输出为输入再追加同样一项，仍只新增一项。
        derived = self.tmp_dir / "derived.json"
        derived.write_bytes(first.stdout)
        result = run_add_option(derived, "start", "向左走", "forest")
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        parsed = json.loads(result.stdout[:-1])
        options = parsed["nodes"][0]["options"]
        self.assertEqual(len(options), 4)
        self.assertEqual(options[2], {"text": "向左走", "target": "forest"})
        self.assertEqual(options[3], {"text": "向左走", "target": "forest"})
        # 新编号即追加后的数组长度。
        self.assertEqual(len(options), 4)

    def test_existing_option_numbers_keep_position(self):
        """已有选项编号（数组位置）与内容保持不变。"""
        result = run_add_option(SAMPLE, "start", "新路线", "river")
        parsed = json.loads(result.stdout[:-1])
        options = parsed["nodes"][0]["options"]
        self.assertEqual(options[0], {"text": "向左走", "target": "forest"})
        self.assertEqual(options[1], {"text": "向右走", "target": "river"})
        self.assertEqual(options[2], {"text": "新路线", "target": "river"})

    def test_start_ids_texts_and_other_nodes_kept(self):
        """追加不改动 start、节点编号、节点正文与其他节点的选项。"""
        result = self.run_and_assert_add(
            SAMPLE, "start", "再去森林", "forest", EXPECTED_THREE_OPTIONS
        )
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["start"], "start")
        self.assertEqual([n["id"] for n in parsed["nodes"]],
                         ["start", "forest", "river"])
        self.assertEqual([n["text"] for n in parsed["nodes"]],
                         ["你来到岔路口。", "你到了森林。", "你到了河边。"])
        # forest 与 river 仍是空 options。
        self.assertEqual(parsed["nodes"][1]["options"], [])
        self.assertEqual(parsed["nodes"][2]["options"], [])

    def test_extra_fields_and_array_order_kept(self):
        """顶层、节点、已有选项上的额外字段及数组顺序全部原样保留。"""
        data = {
            "start": "s",
            "note": "顶层备注",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "去 b", "target": "b", "tag": "旧选项标记"},
                ], "marker": "节点标记"},
                {"id": "b", "text": "乙", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_add(path, "s", "再去 b", "b", {
            "start": "s",
            "note": "顶层备注",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "去 b", "target": "b", "tag": "旧选项标记"},
                    {"text": "再去 b", "target": "b"},
                ], "marker": "节点标记"},
                {"id": "b", "text": "乙", "options": []},
            ],
        })

    def test_unreachable_source_usable(self):
        """不可达来源节点仍可追加选项（含给其空 options 的首次追加）。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路入口", "options": []}
        )
        path = self.make_sample(data)
        result = self.run_and_assert_add(path, "side", "回主路", "start", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
                {"id": "side", "text": "旁路入口", "options": [
                    {"text": "回主路", "target": "start"}]},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        # 从 start 做可达性展开：追加后 side 仍不可达。
        by_id = {n["id"]: n for n in parsed["nodes"]}
        seen = {parsed["start"]}
        pending = [parsed["start"]]
        while pending:
            for option in by_id[pending.pop()]["options"]:
                if option["target"] not in seen:
                    seen.add(option["target"])
                    pending.append(option["target"])
        self.assertNotIn("side", seen)

    def test_unreachable_target_usable(self):
        """目标当前不可达同样成功；追加前后该目标都不可达。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路目标", "options": []}
        )
        path = self.make_sample(data)
        result = self.run_and_assert_add(path, "start", "走旁路", "side", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                    {"text": "走旁路", "target": "side"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
                {"id": "side", "text": "旁路目标", "options": []},
            ],
        })
        # 该用例追加后 side 已可达；再构造一个指向不可达目标的独立用例。
        data2 = self.load_sample_data()
        data2["nodes"].append(
            {"id": "origin", "text": "旁路来源", "options": []}
        )
        data2["nodes"].append(
            {"id": "far", "text": "远方目标", "options": []}
        )
        path2 = self.make_sample(data2, name="case2.json")
        result2 = self.run_and_assert_add(path2, "origin", "去远方", "far", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
                {"id": "origin", "text": "旁路来源", "options": [
                    {"text": "去远方", "target": "far"}]},
                {"id": "far", "text": "远方目标", "options": []},
            ],
        })
        parsed = json.loads(result2.stdout[:-1])
        by_id = {n["id"]: n for n in parsed["nodes"]}
        seen = {parsed["start"]}
        pending = [parsed["start"]]
        while pending:
            for option in by_id[pending.pop()]["options"]:
                if option["target"] not in seen:
                    seen.add(option["target"])
                    pending.append(option["target"])
        self.assertNotIn("origin", seen)
        self.assertNotIn("far", seen)

    def test_self_reference_allowed(self):
        """给结尾节点追加指向自身的选项：自引用合法，正常输出。"""
        self.run_and_assert_add(SAMPLE, "forest", "留在森林", "forest", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": [
                    {"text": "留在森林", "target": "forest"}]},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })

    def test_legal_cycle_allowed(self):
        """追加后形成 a→b、b→a 循环：合法循环不阻止命令。"""
        data = {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去 b", "target": "b"}]},
                {"id": "b", "text": "乙", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_add(path, "b", "回 a", "a", {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去 b", "target": "b"}]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "回 a", "target": "a"}]},
            ],
        })

    def test_empty_text_saved_verbatim(self):
        """空字符串文字：新项 text 为空，target 正常。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        self.run_and_assert_add(path, "start", "", "river", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                    {"text": "", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })

    def test_whitespace_only_text_saved_verbatim(self):
        """纯空白文字按原样保存，不裁剪。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_add(path, "start", "  \t ", "river", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                    {"text": "  \t ", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["nodes"][0]["options"][2]["text"], "  \t ")

    def test_quotes_backslash_and_newline_saved_verbatim(self):
        """引号、反斜杠与换行原样保存；换行按 JSON 规则转义，输出仍单行。"""
        new_text = '他说："看\\这里"\n第二行'
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_add(path, "start", new_text, "forest", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                    {"text": new_text, "target": "forest"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        stdout = result.stdout.decode("utf-8")
        # 文字中的换行在单行 JSON 里以 \n 转义形式出现，输出本身只有一行。
        self.assertIn("\\n", stdout)
        self.assertNotIn("\n", stdout[:-1])
        parsed = json.loads(stdout[:-1])
        self.assertEqual(parsed["nodes"][0]["options"][2]["text"], new_text)

    def test_json_like_text_not_interpreted(self):
        """形似 JSON 的文字按字符串原样保存，不被解析。"""
        new_text = '{"text": "x", "target": "y"}'
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = self.run_and_assert_add(path, "start", new_text, "forest", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                    {"text": new_text, "target": "forest"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["nodes"][0]["options"][2]["text"], new_text)

    def test_path_like_text_not_interpreted(self):
        """形似文件路径的文字按字符串原样保存，不读取任何路径。"""
        new_text = "./forest/enter.json"
        data = self.load_sample_data()
        path = self.make_sample(data)
        self.run_and_assert_add(path, "start", new_text, "forest", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                    {"text": new_text, "target": "forest"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })

    def test_option_like_text_value_accepted_as_value(self):
        """形似参数的文字照收为值：如 --node、--to 都原样保存。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        self.run_and_assert_add(path, "start", "--to", "forest", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                    {"text": "--to", "target": "forest"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })

    def test_source_and_target_matched_exactly_with_whitespace(self):
        """来源与目标编号按原字符串精确匹配、首尾空白保留。"""
        data = {
            "start": " a ",
            "nodes": [
                {"id": " a ", "text": "带空格", "options": []},
                {"id": "a", "text": "不带空格", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_add(path, " a ", "去自身", " a ", {
            "start": " a ",
            "nodes": [
                {"id": " a ", "text": "带空格", "options": [
                    {"text": "去自身", "target": " a "},
                ]},
                {"id": "a", "text": "不带空格", "options": []},
            ],
        })

    def test_chinese_not_escaped(self):
        """中文编号与中文文字在结果中原样显示，不转义。"""
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
        result = self.run_and_assert_add(path, "起点", "再进山", "森林", {
            "start": "起点",
            "nodes": [
                {"id": "起点", "text": "出发", "options": [
                    {"text": "进山", "target": "森林"},
                    {"text": "再进山", "target": "森林"},
                ]},
                {"id": "森林", "text": "到了", "options": []},
            ],
        })
        self.assertIn("再进山", result.stdout.decode("utf-8"))
        self.assertNotIn("\\u", result.stdout.decode("utf-8"))

    def test_no_result_file_created(self):
        """成功追加不在输入文件旁创建任何结果文件。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        before_entries = set(p.name for p in self.tmp_dir.iterdir())
        result = run_add_option(path, "start", "再去森林", "forest")
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        after_entries = set(p.name for p in self.tmp_dir.iterdir())
        self.assertEqual(before_entries, after_entries, "不应创建结果文件")


class TestAddOptionFailure(AddOptionTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_target_fails_and_outputs_no_dialogue(self):
        """验收用例：目标 missing 不存在时失败，且不输出对话。"""
        result = self.run_and_assert_fail(
            SAMPLE, "start", "再去森林", "missing",
            ["文件中不存在编号为 'missing' 的节点"],
        )
        self.assertNotIn(
            "岔路口".encode("utf-8"), result.stdout, "目标不存在时不应输出对话"
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_missing_source_node_uses_existing_message(self):
        """来源节点不存在：沿用节点不存在说明，含编号原值。"""
        result = self.run_and_assert_fail(
            SAMPLE, "ghost", "x", "forest",
            ["文件中不存在编号为 'ghost' 的节点"],
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_missing_source_keeps_surrounding_whitespace(self):
        """来源编号首尾空白不裁剪，错误说明中按原值引用。"""
        self.run_and_assert_fail(
            SAMPLE, " start ", "x", "forest",
            ["文件中不存在编号为 ' start ' 的节点"],
        )

    def test_missing_target_keeps_surrounding_whitespace(self):
        """目标编号首尾空白不裁剪，错误说明中按原值引用。"""
        self.run_and_assert_fail(
            SAMPLE, "start", "x", " forest ",
            ["文件中不存在编号为 ' forest ' 的节点"],
        )

    def test_source_checked_before_target(self):
        """来源与目标都不存在时先报告来源节点不存在。"""
        self.run_and_assert_fail(
            SAMPLE, "ghost1", "x", "ghost2",
            ["文件中不存在编号为 'ghost1' 的节点"],
        )

    def test_dangling_target_on_unchosen_branch_fails_validation(self):
        """未选中分支的悬空引用先报整份校验失败，不做追加。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][1]["target"] = "ghost"
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "forest", "x", "forest",
            ["校验失败：", "nodes[0].options[1].target", "ghost"],
        )

    def test_invalid_unreachable_node_fails_validation(self):
        """不可达节点选项 target 悬空：定位其 target，先于追加报出。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路",
             "options": [{"text": "去虚无", "target": "ghost"}]}
        )
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "start", "x", "forest",
            ["校验失败：", "nodes[3].options[0].target", "ghost"],
        )

    def test_missing_field_fails_validation_before_add(self):
        """目标节点缺少 options 字段：属于整份校验失败，先于追加。"""
        data = self.load_sample_data()
        del data["nodes"][1]["options"]
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "start", "x", "forest",
            ["校验失败：", "nodes[1].options"],
        )

    def test_json_syntax_error_uses_existing_category(self):
        """语法错误文件：沿用既有 JSON 语法错误分类，信息含路径与行列。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{\n  !", encoding="utf-8")
        self.run_and_assert_fail(
            broken, "start", "x", "forest",
            ["JSON 语法错误", "第 2 行第 3 列", str(broken)],
        )

    def test_utf8_decode_error_uses_existing_category(self):
        """UTF-8 解码失败：沿用既有分类且信息含路径。"""
        bad = self.tmp_dir / "bad.json"
        bad.write_bytes(b"\xff")
        self.run_and_assert_fail(bad, "start", "x", "forest",
                                 ["UTF-8 解码失败", str(bad)])

    def test_unreadable_file_uses_existing_category(self):
        """路径不存在：沿用既有无法读取文件分类，含路径且不创建该文件。"""
        missing = self.tmp_dir / "never_created.json"
        result = run_add_option(missing, "start", "x", "forest")
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(missing), stderr)
        self.assertFalse(missing.exists(), "追加不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
