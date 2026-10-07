# -*- coding: utf-8 -*-
"""dialogue.py 单个选项目标重定向（retarget-option）命令行回归测试。

以 sample.json 为基础派生独立临时副本，覆盖先整份校验后重定向的成功
路径：样例中起点选项 1 改指 river 的验收结果（两个选项 target 同为
river）、不可达来源与不可达目标、自引用与合法循环、目标与原 target
相同输出等价对象、除选中项 target 外的全部内容（start、节点编号、
文字、其他引用、额外字段与数组顺序）原样保留、中文不转义、来源与
目标编号首尾空白精确匹配；以及来源节点不存在、选项无法解析为整数、
来源是结尾节点、选项越界、目标节点不存在的错误文案与检查顺序、
不可达节点/未选中分支结构或引用非法及待改悬空 target 先报告整份校验
失败、文件读取与 JSON 语法错误沿用既有分类等失败边界。参数格式错误
另有 test_dialogue_retarget_option_args.py。

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


def run_retarget(path, source_id, choice, target_id):
    """以命令行方式执行 retarget-option，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "retarget-option", str(path),
         "--node", source_id, "--choice", str(choice), "--to", target_id],
        capture_output=True,
    )


class RetargetTestCase(unittest.TestCase):
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

    def run_and_assert_retarget(self, path, source_id, choice, target_id,
                                expected_object):
        """成功：退出码 0、标准错误为空，输出为修改后的完整对话对象，
        单行 JSON 加一个结尾换行；对象按解析后内容核对。"""
        before = path.read_bytes()
        result = run_retarget(path, source_id, choice, target_id)
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

    def run_and_assert_fail(self, path, source_id, choice, target_id,
                            expected_parts):
        """失败：退出码 2、标准输出为空、标准错误包含各片段且无调用栈。"""
        before = path.read_bytes()
        result = run_retarget(path, source_id, choice, target_id)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestRetargetSuccess(RetargetTestCase):
    """成功路径：整份校验通过后输出修改后的完整对话对象。"""

    def test_sample_start_choice_1_to_river(self):
        """验收用例：起点选项 1 改指 river，两个选项 target 均为 river，
        其余内容与原对象一致。"""
        expected = {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "river"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        }
        result = self.run_and_assert_retarget(
            SAMPLE, "start", 1, "river", expected
        )
        # 中文原样输出，不转义。
        self.assertIn("你来到岔路口。", result.stdout.decode("utf-8"))
        self.assertNotIn("\\u", result.stdout.decode("utf-8"))

    def test_choice_2_retargeted_choice_1_untouched(self):
        """只改选中项：选项 2 改指 forest 时，选项 1 的 target 保持不变。"""
        self.run_and_assert_retarget(SAMPLE, "start", 2, "forest", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "forest"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })

    def test_unreachable_source_and_target(self):
        """不可达来源节点的选项可以改指不可达目标，命令正常成功。"""
        data = {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "s", "options": [
                    {"text": "去a", "target": "a"},
                ]},
                {"id": "a", "text": "甲", "options": []},
                {"id": "side", "text": "旁路", "options": [
                    {"text": "o1", "target": "a"},
                    {"text": "o2", "target": "a"},
                ]},
                {"id": "far", "text": "远处", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_retarget(path, "side", 2, "far", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "s", "options": [
                    {"text": "去a", "target": "a"},
                ]},
                {"id": "a", "text": "甲", "options": []},
                {"id": "side", "text": "旁路", "options": [
                    {"text": "o1", "target": "a"},
                    {"text": "o2", "target": "far"},
                ]},
                {"id": "far", "text": "远处", "options": []},
            ],
        })

    def test_self_reference_allowed(self):
        """自引用允许：选项改指来源节点自身。"""
        data = {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去乙", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_retarget(path, "a", 1, "a", {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去乙", "target": "a"},
                ]},
                {"id": "b", "text": "乙", "options": []},
            ],
        })

    def test_legal_cycle_allowed(self):
        """合法循环允许：把原本指向结尾的选项改成回到上游节点。"""
        data = {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去乙", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "去结尾", "target": "end"},
                ]},
                {"id": "end", "text": "结尾", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_retarget(path, "b", 1, "a", {
            "start": "a",
            "nodes": [
                {"id": "a", "text": "甲", "options": [
                    {"text": "去乙", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "去结尾", "target": "a"},
                ]},
                {"id": "end", "text": "结尾", "options": []},
            ],
        })

    def test_same_target_outputs_equivalent_object(self):
        """目标与原 target 相同时成功，输出与原对象等价的 JSON。"""
        original = json.loads(SAMPLE.read_text(encoding="utf-8"))
        result = self.run_and_assert_retarget(
            SAMPLE, "start", 1, "forest", original
        )
        self.assertEqual(json.loads(result.stdout[:-1]), original)

    def test_extra_fields_and_order_preserved(self):
        """除选中项 target 外：顶层额外字段、节点/选项额外字段、键与数组
        顺序以及碰巧形似编号的文字值全部原样保留。"""
        data = {
            "version": 3,
            "start": "s",
            "note": "a",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "去 a", "target": "a", "tag": "a"},
                    {"text": "留 a", "target": "a", "tag": "keep"},
                ], "extra": "a"},
                {"id": "a", "text": "a", "options": []},
            ],
        }
        path = self.make_sample(data)
        result = self.run_and_assert_retarget(path, "s", 1, "s", {
            "version": 3,
            "start": "s",
            "note": "a",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "去 a", "target": "s", "tag": "a"},
                    {"text": "留 a", "target": "a", "tag": "keep"},
                ], "extra": "a"},
                {"id": "a", "text": "a", "options": []},
            ],
        })
        # 键顺序按首次出现保留：version 在 start 之前。
        stdout = result.stdout.decode("utf-8")
        self.assertLess(stdout.index('"version"'), stdout.index('"start"'))

    def test_ids_matched_exactly_with_surrounding_whitespace(self):
        """来源与目标编号按原字符串精确匹配、首尾空白保留。"""
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
        self.run_and_assert_retarget(path, " a ", 1, " a ", {
            "start": " a ",
            "nodes": [
                {"id": " a ", "text": "带空格", "options": [
                    {"text": "去不带空格", "target": " a "},
                ]},
                {"id": "a", "text": "不带空格", "options": []},
            ],
        })

    def test_chinese_ids_not_escaped(self):
        """中文编号与文字在结果中原样显示，不转义。"""
        data = {
            "start": "起点",
            "nodes": [
                {"id": "起点", "text": "出发", "options": [
                    {"text": "进森林", "target": "森林"},
                ]},
                {"id": "森林", "text": "到了", "options": []},
                {"id": "林场", "text": "林场", "options": []},
            ],
        }
        path = self.make_sample(data)
        result = self.run_and_assert_retarget(path, "起点", 1, "林场", {
            "start": "起点",
            "nodes": [
                {"id": "起点", "text": "出发", "options": [
                    {"text": "进森林", "target": "林场"},
                ]},
                {"id": "森林", "text": "到了", "options": []},
                {"id": "林场", "text": "林场", "options": []},
            ],
        })
        self.assertIn("林场", result.stdout.decode("utf-8"))
        self.assertNotIn("\\u", result.stdout.decode("utf-8"))

    def test_choice_int_parsing_matches_preview(self):
        """选项编号整数解析与 preview 相同：带空白及正负号的十进制值照收。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        result = run_retarget(path, "start", " 1 ", "forest")
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        # “ 1 ” 解析为 1；目标与原 target 相同，对象等价。
        self.assertEqual(
            json.loads(result.stdout[:-1]), self.load_sample_data()
        )

    def test_no_result_file_created(self):
        """成功重定向不在输入文件旁创建任何结果文件。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        before_entries = set(p.name for p in self.tmp_dir.iterdir())
        result = run_retarget(path, "start", 1, "river")
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        after_entries = set(p.name for p in self.tmp_dir.iterdir())
        self.assertEqual(before_entries, after_entries, "不应创建结果文件")


class TestRetargetFailure(RetargetTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_source_node_uses_existing_message(self):
        """来源节点不存在：沿用节点不存在说明，含编号原值。"""
        result = self.run_and_assert_fail(
            SAMPLE, "ghost", 1, "river",
            ["文件中不存在编号为 'ghost' 的节点"],
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_missing_source_id_keeps_surrounding_whitespace(self):
        """来源编号首尾空白不裁剪，错误说明中按原值引用。"""
        self.run_and_assert_fail(
            SAMPLE, " start ", 1, "river",
            ["文件中不存在编号为 ' start ' 的节点"],
        )

    def test_bad_choice_integer_uses_preview_message(self):
        """选项无法解析为整数：沿用显式 --node 的 preview 文案。"""
        result = self.run_and_assert_fail(
            SAMPLE, "start", "abc", "river",
            ["--choice 的值 'abc' 无法解析为整数（出发节点编号为 'start'）"],
        )
        stderr = result.stderr.decode("utf-8")
        self.assertEqual(
            stderr,
            "--choice 的值 'abc' 无法解析为整数（出发节点编号为 'start'）\n",
        )

    def test_ending_node_choice_uses_preview_message(self):
        """验收用例：forest 是结尾节点，choice 1 报结尾无有效选项。"""
        result = self.run_and_assert_fail(
            SAMPLE, "forest", 1, "river",
            ["--choice 1 无效：出发节点 'forest' 是结尾节点，没有有效选项"],
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_choice_out_of_range_uses_preview_message(self):
        """选项越界：沿用显式 --node 的 preview 范围文案。"""
        result = self.run_and_assert_fail(
            SAMPLE, "start", 3, "river",
            ["--choice 3 不在出发节点 'start' 的有效选项编号范围 1 到 2 内"],
        )
        self.assertEqual(
            result.stderr.decode("utf-8"),
            "--choice 3 不在出发节点 'start' 的有效选项编号范围 1 到 2 内\n",
        )

    def test_choice_zero_out_of_range(self):
        """编号 0 同样越界。"""
        self.run_and_assert_fail(
            SAMPLE, "start", 0, "river",
            ["--choice 0 不在出发节点 'start' 的有效选项编号范围 1 到 2 内"],
        )

    def test_missing_target_node_uses_existing_message(self):
        """目标节点不存在：沿用节点不存在说明，含编号原值。"""
        result = self.run_and_assert_fail(
            SAMPLE, "start", 1, "ghost",
            ["文件中不存在编号为 'ghost' 的节点"],
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_missing_target_id_keeps_surrounding_whitespace(self):
        """目标编号首尾空白不裁剪，错误说明中按原值引用。"""
        self.run_and_assert_fail(
            SAMPLE, "start", 1, " river ",
            ["文件中不存在编号为 ' river ' 的节点"],
        )

    def test_source_check_before_choice_and_target(self):
        """来源节点不存在先于整数解析、结尾、范围与目标检查报告。"""
        result = self.run_and_assert_fail(
            SAMPLE, "ghost", "xyz", "nope",
            ["文件中不存在编号为 'ghost' 的节点"],
        )
        stderr = result.stderr.decode("utf-8")
        self.assertNotIn("无法解析为整数", stderr)
        self.assertNotIn("nope", stderr)

    def test_integer_parse_before_ending_check(self):
        """整数解析失败先于结尾无选项报告。"""
        self.run_and_assert_fail(
            SAMPLE, "forest", "xyz", "river",
            ["--choice 的值 'xyz' 无法解析为整数（出发节点编号为 'forest'）"],
        )

    def test_ending_check_before_range_check(self):
        """结尾节点先报无有效选项，即使编号也越界。"""
        result = self.run_and_assert_fail(
            SAMPLE, "forest", 5, "river",
            ["没有有效选项"],
        )
        self.assertNotIn("范围", result.stderr.decode("utf-8"))

    def test_range_check_before_target_check(self):
        """选项越界先于目标节点不存在报告。"""
        result = self.run_and_assert_fail(
            SAMPLE, "start", 9, "ghost",
            ["有效选项编号范围 1 到 2"],
        )
        self.assertNotIn("文件中不存在", result.stderr.decode("utf-8"))

    def test_dangling_target_to_be_changed_fails_validation(self):
        """待改选项当前悬空的 target：先报整份校验失败，不做重定向。"""
        data = {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "s", "options": [
                    {"text": "去虚无", "target": "ghost"},
                ]},
                {"id": "a", "text": "甲", "options": []},
            ],
        }
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path, "start", 1, "a",
            ["校验失败：", "nodes[0].options[0].target", "ghost"],
        )
        self.assertTrue(
            result.stderr.decode("utf-8").startswith("校验失败："),
            "标准错误应以“校验失败：”开头",
        )

    def test_invalid_structure_in_unchosen_branch_fails_validation(self):
        """未选中分支（另一选项）指向结构非法节点：仍先报整份校验失败。"""
        data = {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "s", "options": [
                    {"text": "分支一", "target": "bad"},
                    {"text": "分支二", "target": "a"},
                ]},
                {"id": "bad", "options": []},
                {"id": "a", "text": "甲", "options": []},
            ],
        }
        path = self.make_sample(data)
        # 改选项 2；选项 1 所在分支未被选中，其目标节点缺 text 仍报校验失败。
        result = self.run_and_assert_fail(
            path, "start", 2, "a",
            ["校验失败：", "nodes[1].text"],
        )
        self.assertTrue(
            result.stderr.decode("utf-8").startswith("校验失败："),
            "标准错误应以“校验失败：”开头",
        )

    def test_invalid_structure_in_unreachable_node_fails_validation(self):
        """不可达 side 节点缺少 text：先于重定向报整份校验失败。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "options": [
                {"text": "去森林", "target": "forest"}]}
        )
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path, "start", 1, "river", ["校验失败：", "nodes[3].text"]
        )
        self.assertTrue(
            result.stderr.decode("utf-8").startswith("校验失败："),
            "标准错误应以“校验失败：”开头",
        )

    def test_json_syntax_error_uses_existing_category(self):
        """语法错误文件：沿用既有 JSON 语法错误分类，信息含路径与行列。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{\n  !", encoding="utf-8")
        result = self.run_and_assert_fail(
            broken, "start", 1, "river",
            ["JSON 语法错误", "第 2 行第 3 列", str(broken)],
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_utf8_decode_error_uses_existing_category(self):
        """UTF-8 解码失败：沿用既有分类且信息含路径。"""
        bad = self.tmp_dir / "bad.json"
        bad.write_bytes(b"\xff")
        self.run_and_assert_fail(bad, "start", 1, "river",
                                 ["UTF-8 解码失败", str(bad)])

    def test_unreadable_file_uses_existing_category(self):
        """路径不存在：沿用既有无法读取文件分类，含路径且不创建该文件。"""
        missing = self.tmp_dir / "never_created.json"
        result = run_retarget(missing, "start", 1, "river")
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(missing), stderr)
        self.assertFalse(missing.exists(), "重定向不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
