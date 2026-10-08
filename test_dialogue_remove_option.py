# -*- coding: utf-8 -*-
"""dialogue.py 单个选项删除（remove-option）命令行回归测试。

以 sample.json 为基础派生独立临时副本，覆盖先整份校验后删除的成功路径：
样例中删除 start 的选项 1 的验收结果（起点仅剩指向 river 的「向右走」，
forest 仍存在），并把输出作为 preview 的对话输入验证选择 1 只输出
「你到了河边。」；剩余选项保持相对顺序、删除位置之后的编号随数组位置
前移，文字或目标相同的其他选项仍保留；删除最后一项后 options 为空
数组、该节点成为结尾；只移除选中项而 start/节点编号与正文/其余选项/
额外字段/节点数组顺序原样；目标节点与其他节点仍保留，不顺带删除失去
引用的内容；不可达来源、自引用与合法循环中的选项可删除；来源编号首尾
空白精确匹配；01、+1 与带首尾空白的数字沿用既有整数语义；中文不转义；
不创建结果文件。以及来源节点不存在、编号非整数、来源为结尾、编号越界
沿用显式 --node 的 preview 对应说明及来源→整数→结尾→范围的检查顺序、
待删选项自身与未选分支及不可达节点非法时先报告整份校验失败、文件读取
与 JSON 语法错误沿用既有分类等失败边界。参数格式错误另有
test_dialogue_remove_option_args.py。

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

# sample.json 删除 start 的选项 1（「向左走」→ forest）后的验收结果：
# 起点仅剩指向 river 的「向右走」，forest 仍作为节点保留。
EXPECTED_FIRST_REMOVED = {
    "start": "start",
    "nodes": [
        {"id": "start", "text": "你来到岔路口。", "options": [
            {"text": "向右走", "target": "river"},
        ]},
        {"id": "forest", "text": "你到了森林。", "options": []},
        {"id": "river", "text": "你到了河边。", "options": []},
    ],
}


def run_remove_option(path, source_id, choice):
    """以命令行方式执行 remove-option，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "remove-option", str(path),
         "--node", source_id, "--choice", str(choice)],
        capture_output=True,
    )


class RemoveOptionTestCase(unittest.TestCase):
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

    def run_and_assert_remove(self, path, source_id, choice, expected_object):
        """成功：退出码 0、标准错误为空，输出为修改后的完整对话对象，
        单行 JSON 加一个结尾换行；对象按解析后内容核对。"""
        before = path.read_bytes()
        result = run_remove_option(path, source_id, choice)
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

    def run_and_assert_fail(self, path, source_id, choice, expected_parts):
        """失败：退出码 2、标准输出为空、标准错误包含各片段且无调用栈。"""
        before = path.read_bytes()
        result = run_remove_option(path, source_id, choice)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestRemoveOptionSuccess(RemoveOptionTestCase):
    """成功路径：整份校验通过后输出修改后的完整对话对象。"""

    def test_sample_start_remove_choice_1(self):
        """验收用例：删除起点选项 1 后只剩「向右走」→ river，forest 仍在。"""
        result = self.run_and_assert_remove(
            SAMPLE, "start", 1, EXPECTED_FIRST_REMOVED
        )
        # 中文原样输出，不转义。
        stdout = result.stdout.decode("utf-8")
        self.assertIn("向右走", stdout)
        self.assertIn("forest", stdout)
        self.assertNotIn("向左走", stdout)
        self.assertNotIn("\\u", stdout)

    def test_output_is_preview_input_choice_1(self):
        """验收用例：输出另存为对话文件后，preview 选择 1 只显示河边文字。"""
        removed = subprocess.run(
            [sys.executable, str(DIALOGUE), "remove-option", str(SAMPLE),
             "--node", "start", "--choice", "1"],
            capture_output=True,
        )
        self.assertEqual(removed.returncode, 0)
        derived = self.tmp_dir / "derived.json"
        derived.write_bytes(removed.stdout)
        preview = subprocess.run(
            [sys.executable, str(DIALOGUE), "preview", str(derived),
             "--choice", "1"],
            capture_output=True,
        )
        self.assertEqual(preview.returncode, 0, "stderr: {!r}".format(
            preview.stderr))
        self.assertEqual(preview.stderr, b"")
        # 只剩「你到了河边。」与一个结尾换行，没有森林文字。
        self.assertEqual(preview.stdout.decode("utf-8"), "你到了河边。\n")

    def test_remove_second_of_three_shifts_later_options(self):
        """删除中间项：剩余选项保持相对顺序，其后编号随数组位置前移。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"].append(
            {"text": "再去森林", "target": "forest"}
        )
        path = self.make_sample(data)
        result = self.run_and_assert_remove(path, "start", 2, {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "再去森林", "target": "forest"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        # 原选项 3 的对象现在排在位置 2（编号随数组前移，内容原样）。
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(
            parsed["nodes"][0]["options"][1],
            {"text": "再去森林", "target": "forest"},
        )

    def test_remove_last_option_makes_empty_ending(self):
        """删除唯一（最后一项）选项后 options 为空数组，节点成为结尾。"""
        data = {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去 b", "target": "b"}]},
                {"id": "b", "text": "乙", "options": []},
            ],
        }
        path = self.make_sample(data)
        result = self.run_and_assert_remove(path, "a", 1, {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": []},
                {"id": "b", "text": "乙", "options": []},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["nodes"][0]["options"], [])

    def test_duplicate_text_and_target_other_option_kept(self):
        """文字与目标都相同的两个选项：删 1 只删第一项，另一项保留。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "同", "target": "s"},
                    {"text": "同", "target": "s"},
                ]},
            ],
        }
        path = self.make_sample(data)
        result = self.run_and_assert_remove(path, "s", 1, {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "同", "target": "s"}]},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(len(parsed["nodes"][0]["options"]), 1)

    def test_duplicate_options_remove_second_keeps_first(self):
        """相同选项删第 2 项：按数组位置删除，保留的是第一项而非任意一项。"""
        data = {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "同", "target": "s", "tag": "第一项"},
                    {"text": "同", "target": "s", "tag": "第二项"},
                ]},
            ],
        }
        path = self.make_sample(data)
        result = self.run_and_assert_remove(path, "s", 2, {
            "start": "s",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "同", "target": "s", "tag": "第一项"}]},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        self.assertEqual(parsed["nodes"][0]["options"][0]["tag"], "第一项")

    def test_other_node_with_same_target_kept(self):
        """只删来源的选中项：其他节点指向同一目标的选项不受影响。"""
        data = {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去 c", "target": "c"},
                    {"text": "去 b", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "也去 c", "target": "c"}]},
                {"id": "c", "text": "丙", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_remove(path, "a", 1, {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去 b", "target": "b"}]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "也去 c", "target": "c"}]},
                {"id": "c", "text": "丙", "options": []},
            ],
        })

    def test_start_ids_texts_and_other_nodes_kept(self):
        """删除不改动 start、节点编号、节点正文与其他节点的选项。"""
        result = self.run_and_assert_remove(
            SAMPLE, "start", 1, EXPECTED_FIRST_REMOVED
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
        """顶层、节点、剩余选项上的额外字段及节点数组顺序全部原样保留。"""
        data = {
            "start": "s",
            "note": "顶层备注",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "去 b", "target": "b", "tag": "被删选项标记"},
                    {"text": "留 c", "target": "c", "keep": "保留项标记"},
                ], "marker": "节点标记"},
                {"id": "b", "text": "乙", "options": []},
                {"id": "c", "text": "丙", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_remove(path, "s", 1, {
            "start": "s",
            "note": "顶层备注",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "留 c", "target": "c", "keep": "保留项标记"},
                ], "marker": "节点标记"},
                {"id": "b", "text": "乙", "options": []},
                {"id": "c", "text": "丙", "options": []},
            ],
        })

    def test_orphaned_target_node_kept_without_cascade_delete(self):
        """删除后目标失去所有引用：目标节点仍保留，不做级联删除。"""
        data = {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "路口", "options": [
                    {"text": "进森林", "target": "forest"},
                    {"text": "去河边", "target": "river"},
                ]},
                {"id": "forest", "text": "森林", "options": []},
                {"id": "river", "text": "河边", "options": []},
            ],
        }
        path = self.make_sample(data)
        result = self.run_and_assert_remove(path, "start", 1, {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "路口", "options": [
                    {"text": "去河边", "target": "river"}]},
                {"id": "forest", "text": "森林", "options": []},
                {"id": "river", "text": "河边", "options": []},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        ids = [n["id"] for n in parsed["nodes"]]
        self.assertIn("forest", ids, "失去引用的 forest 不应被顺带删除")
        # 删后的输出是合法对话（forest 成为不可达节点，不影响再次校验）。
        derived = self.tmp_dir / "derived.json"
        derived.write_text(json.dumps(parsed, ensure_ascii=False),
                           encoding="utf-8")
        validate = subprocess.run(
            [sys.executable, str(DIALOGUE), "validate", str(derived)],
            capture_output=True,
        )
        self.assertEqual(validate.returncode, 0, "stderr: {!r}".format(
            validate.stderr))

    def test_unreachable_source_usable(self):
        """不可达来源节点中的选项仍可删除（含自引用选项）。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路入口", "options": [
                {"text": "留在旁路", "target": "side"}]}
        )
        path = self.make_sample(data)
        result = self.run_and_assert_remove(path, "side", 1, {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
                {"id": "side", "text": "旁路入口", "options": []},
            ],
        })
        parsed = json.loads(result.stdout[:-1])
        # 从 start 做可达性展开：删除后 side 仍不可达。
        by_id = {n["id"]: n for n in parsed["nodes"]}
        seen = {parsed["start"]}
        pending = [parsed["start"]]
        while pending:
            for option in by_id[pending.pop()]["options"]:
                if option["target"] not in seen:
                    seen.add(option["target"])
                    pending.append(option["target"])
        self.assertNotIn("side", seen)

    def test_self_reference_option_removable(self):
        """删除节点指向自身的自引用选项：自引用合法，删除正常。"""
        data = {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "路口", "options": [
                    {"text": "留在原地", "target": "start"},
                    {"text": "去河边", "target": "river"},
                ]},
                {"id": "river", "text": "河边", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_remove(path, "start", 1, {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "路口", "options": [
                    {"text": "去河边", "target": "river"}]},
                {"id": "river", "text": "河边", "options": []},
            ],
        })

    def test_option_in_legal_cycle_removable(self):
        """删除 a→b、b→a 合法循环中 b 的回边：循环断开，b 成为结尾。"""
        data = {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去 b", "target": "b"}]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "回 a", "target": "a"}]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_remove(path, "b", 1, {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去 b", "target": "b"}]},
                {"id": "b", "text": "乙", "options": []},
            ],
        })

    def test_source_matched_exactly_with_whitespace(self):
        """来源编号按原字符串精确匹配，首尾空白保留。"""
        data = {
            "start": " a ",
            "nodes": [
                {"id": " a ", "text": "带空格", "options": [
                    {"text": "去 a", "target": " a "}]},
                {"id": "a", "text": "不带空格", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_remove(path, " a ", 1, {
            "start": " a ",
            "nodes": [
                {"id": " a ", "text": "带空格", "options": []},
                {"id": "a", "text": "不带空格", "options": []},
            ],
        })

    def test_integer_parsing_variants(self):
        """01、+1 与带首尾空白的数字都按既有 int() 语义解析为 1。"""
        for variant in ("01", "+1", " 1 "):
            data = self.load_sample_data()
            path = self.make_sample(
                data, name="case_{}.json".format(abs(hash(variant))))
            result = self.run_and_assert_remove(
                path, "start", variant, EXPECTED_FIRST_REMOVED
            )
            parsed = json.loads(result.stdout[:-1])
            self.assertEqual(
                [o["text"] for o in parsed["nodes"][0]["options"]],
                ["向右走"],
                "编号值 {!r} 应等同于 1".format(variant),
            )

    def test_chinese_not_escaped(self):
        """中文编号与中文文字在结果中原样显示，不转义。"""
        data = {
            "start": "起点",
            "nodes": [
                {"id": "起点", "text": "出发", "options": [
                    {"text": "进山", "target": "森林"},
                    {"text": "停留", "target": "起点"},
                ]},
                {"id": "森林", "text": "到了", "options": []},
            ],
        }
        path = self.make_sample(data)
        result = self.run_and_assert_remove(path, "起点", 1, {
            "start": "起点",
            "nodes": [
                {"id": "起点", "text": "出发", "options": [
                    {"text": "停留", "target": "起点"}]},
                {"id": "森林", "text": "到了", "options": []},
            ],
        })
        stdout = result.stdout.decode("utf-8")
        self.assertIn("停留", stdout)
        self.assertNotIn("\\u", stdout)

    def test_repeated_removals_chain(self):
        """输出可再作为输入连续删除：两次后起点 options 为空。"""
        first = self.run_and_assert_remove(
            SAMPLE, "start", 1, EXPECTED_FIRST_REMOVED
        )
        derived = self.tmp_dir / "derived.json"
        derived.write_bytes(first.stdout)
        second = run_remove_option(derived, "start", 2)
        # 此时只剩一个选项，编号 2 越界，应失败而不是改动文件。
        self.assertEqual(second.returncode, 2)
        second = run_remove_option(derived, "start", 1)
        self.assertEqual(second.returncode, 0, "stderr: {!r}".format(
            second.stderr))
        parsed = json.loads(second.stdout[:-1])
        self.assertEqual(parsed["nodes"][0]["options"], [])

    def test_no_result_file_created(self):
        """成功删除不在输入文件旁创建任何结果文件。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        before_entries = set(p.name for p in self.tmp_dir.iterdir())
        result = run_remove_option(path, "start", 1)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        after_entries = set(p.name for p in self.tmp_dir.iterdir())
        self.assertEqual(before_entries, after_entries, "不应创建结果文件")


class TestRemoveOptionFailure(RemoveOptionTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_source_node_uses_existing_message(self):
        """来源节点不存在：沿用节点不存在说明，含编号原值。"""
        result = self.run_and_assert_fail(
            SAMPLE, "ghost", 1,
            ["文件中不存在编号为 'ghost' 的节点"],
        )
        self.assertNotIn(
            "岔路口".encode("utf-8"), result.stdout, "来源不存在时不应输出对话"
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_missing_source_keeps_surrounding_whitespace(self):
        """来源编号首尾空白不裁剪，错误说明中按原值引用。"""
        self.run_and_assert_fail(
            SAMPLE, " start ", 1,
            ["文件中不存在编号为 ' start ' 的节点"],
        )

    def test_non_integer_choice_uses_preview_message(self):
        """编号无法解析为整数：沿用显式 --node 的 preview 对应说明。"""
        result = self.run_and_assert_fail(
            SAMPLE, "start", "abc",
            ["--choice 的值 'abc' 无法解析为整数", "出发节点", "'start'"],
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_non_integer_checked_before_empty_options(self):
        """非整数判断先于空选项判断：对结尾节点传非整数报整数错误。"""
        self.run_and_assert_fail(
            SAMPLE, "forest", "x",
            ["--choice 的值 'x' 无法解析为整数", "出发节点", "'forest'"],
        )

    def test_ending_node_without_options_uses_preview_message(self):
        """来源是空 options 的结尾节点：沿用 preview 结尾节点说明。"""
        self.run_and_assert_fail(
            SAMPLE, "forest", 1,
            ["--choice 1 无效：出发节点 'forest' 是结尾节点，没有有效选项"],
        )

    def test_choice_out_of_range_uses_preview_message(self):
        """编号超出范围：沿用 preview 范围说明并给出 1 到选项数。"""
        self.run_and_assert_fail(
            SAMPLE, "start", 3,
            ["--choice 3 不在出发节点 'start' 的有效选项编号范围 1 到 2 内"],
        )

    def test_choice_zero_out_of_range(self):
        """编号 0 可解析为整数但不在范围内，报范围错误。"""
        self.run_and_assert_fail(
            SAMPLE, "start", 0,
            ["有效选项编号范围 1 到 2"],
        )

    def test_negative_choice_out_of_range(self):
        """编号 -1 可解析为整数但不在范围内，报范围错误而非用法错误。"""
        result = self.run_and_assert_fail(
            SAMPLE, "start", -1,
            ["有效选项编号范围 1 到 2"],
        )
        self.assertNotIn(
            "用法", result.stderr.decode("utf-8"),
            "负值是合法整数形式，不应按参数用法错误处理",
        )

    def test_check_order_source_before_integer(self):
        """来源不存在与非整数同时成立：先报告来源节点不存在。"""
        self.run_and_assert_fail(
            SAMPLE, "ghost", "x",
            ["文件中不存在编号为 'ghost' 的节点"],
        )

    def test_dangling_target_of_chosen_option_fails_validation(self):
        """待删选项自身的悬空 target 也先报整份校验失败，不能借删除绕过。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0]["target"] = "ghost"
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "start", 1,
            ["校验失败：", "nodes[0].options[0].target", "ghost"],
        )

    def test_dangling_target_on_unchosen_branch_fails_validation(self):
        """未选中分支的悬空引用先报整份校验失败，不做删除。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][1]["target"] = "ghost"
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "start", 1,
            ["校验失败：", "nodes[0].options[1].target", "ghost"],
        )

    def test_invalid_unreachable_node_fails_validation(self):
        """不可达节点选项 target 悬空：先于删除报出。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路",
             "options": [{"text": "去虚无", "target": "ghost"}]}
        )
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "start", 1,
            ["校验失败：", "nodes[3].options[0].target", "ghost"],
        )

    def test_missing_field_fails_validation_before_remove(self):
        """目标节点缺少 options 字段：属于整份校验失败，先于删除。"""
        data = self.load_sample_data()
        del data["nodes"][1]["options"]
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "start", 1,
            ["校验失败：", "nodes[1].options"],
        )

    def test_json_syntax_error_uses_existing_category(self):
        """语法错误文件：沿用既有 JSON 语法错误分类，信息含路径与行列。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{\n  !", encoding="utf-8")
        self.run_and_assert_fail(
            broken, "start", 1,
            ["JSON 语法错误", "第 2 行第 3 列", str(broken)],
        )

    def test_utf8_decode_error_uses_existing_category(self):
        """UTF-8 解码失败：沿用既有分类且信息含路径。"""
        bad = self.tmp_dir / "bad.json"
        bad.write_bytes(b"\xff")
        self.run_and_assert_fail(bad, "start", 1,
                                 ["UTF-8 解码失败", str(bad)])

    def test_unreadable_file_uses_existing_category(self):
        """路径不存在：沿用既有无法读取文件分类，含路径且不创建该文件。"""
        missing = self.tmp_dir / "never_created.json"
        result = run_remove_option(missing, "start", 1)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(missing), stderr)
        self.assertFalse(missing.exists(), "删除不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
