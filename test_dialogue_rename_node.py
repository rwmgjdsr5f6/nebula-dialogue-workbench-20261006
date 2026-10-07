# -*- coding: utf-8 -*-
"""dialogue.py 节点重命名（rename-node）命令行回归测试。

以 sample.json 为基础派生独立临时副本，覆盖先整份校验后重命名的成功路径：
样例中 forest 改为 grove 的给定结果、start 等于旧编号时同步更新、不可达
来源与多个选项重复引用及自引用、循环中的引用全部更新、节点与选项数组
顺序及全部文字和额外字段原样保留（即使碰巧等于旧编号也不替换）、新旧
编号完全相同时输出与原对象等价的 JSON、中文不转义、编号首尾空白精确
匹配；以及旧节点不存在、新编号为空白、新编号与其他节点冲突、不可达
节点结构/引用非法时先报告整份校验失败、文件读取与 JSON 语法错误沿用
既有分类等失败边界。参数格式错误另有 test_dialogue_rename_node_args.py。

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


def run_rename(path, old_id, new_id):
    """以命令行方式执行 rename-node，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "rename-node", str(path),
         "--node", old_id, "--to", new_id],
        capture_output=True,
    )


class RenameTestCase(unittest.TestCase):
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

    def run_and_assert_rename(self, path, old_id, new_id, expected_object):
        """成功：退出码 0、标准错误为空，输出为修改后的完整对话对象，
        单行 JSON 加一个结尾换行；对象按解析后内容核对。"""
        before = path.read_bytes()
        result = run_rename(path, old_id, new_id)
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

    def run_and_assert_fail(self, path, old_id, new_id, expected_parts):
        """失败：退出码 2、标准输出为空、标准错误包含各片段且无调用栈。"""
        before = path.read_bytes()
        result = run_rename(path, old_id, new_id)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestRenameSuccess(RenameTestCase):
    """成功路径：整份校验通过后输出修改后的完整对话对象。"""

    def test_sample_rename_forest_to_grove(self):
        """验收用例：forest 改为 grove，起点第一项 target 同步更新。"""
        expected = {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "grove"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "grove", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        }
        result = self.run_and_assert_rename(SAMPLE, "forest", "grove", expected)
        # 中文原样输出，不转义。
        self.assertIn("你到了森林。", result.stdout.decode("utf-8"))
        self.assertNotIn("\\u", result.stdout.decode("utf-8"))

    def test_start_updated_when_equal_to_old_id(self):
        """start 等于旧编号时同步更新；其余字段不变。"""
        data = self.load_sample_data()
        data["start"] = "forest"
        path = self.make_sample(data)
        result = self.run_and_assert_rename(path, "forest", "grove", {
            "start": "grove",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "grove"},
                    {"text": "向右走", "target": "river"},
                ]},
                {"id": "grove", "text": "你到了森林。", "options": []},
                {"id": "river", "text": "你到了河边。", "options": []},
            ],
        })
        self.assertEqual(json.loads(result.stdout[:-1])["start"], "grove")

    def test_start_not_equal_to_old_id_kept(self):
        """start 不等于旧编号时保持原样。"""
        result = self.run_and_assert_rename(SAMPLE, "river", "bank", {
            "start": "start",
            "nodes": [
                {"id": "start", "text": "你来到岔路口。", "options": [
                    {"text": "向左走", "target": "forest"},
                    {"text": "向右走", "target": "bank"},
                ]},
                {"id": "forest", "text": "你到了森林。", "options": []},
                {"id": "bank", "text": "你到了河边。", "options": []},
            ],
        })
        self.assertEqual(json.loads(result.stdout[:-1])["start"], "start")

    def test_unreachable_and_repeated_and_self_and_cycle_references(self):
        """不可达来源、同一来源的多个选项、自引用与循环中的引用全部更新，
        命令正常结束；数组顺序与文字保持原样。"""
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
                {"id": "side", "text": "旁路", "options": [
                    {"text": "也去甲", "target": "a"},
                    {"text": "还去甲", "target": "a"},
                ]},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_rename(path, "a", "n1", {
            "start": "n1",
            "nodes": [
                {"id": "n1", "text": "甲", "options": [
                    {"text": "原地", "target": "n1"},
                    {"text": "去乙", "target": "b"},
                ]},
                {"id": "b", "text": "乙", "options": [
                    {"text": "回甲", "target": "n1"},
                ]},
                {"id": "side", "text": "旁路", "options": [
                    {"text": "也去甲", "target": "n1"},
                    {"text": "还去甲", "target": "n1"},
                ]},
            ],
        })

    def test_values_equal_to_old_id_elsewhere_not_replaced(self):
        """文字与额外字段的 JSON 值碰巧等于旧编号时不替换；顶层额外字段
        与节点、选项上的额外字段原样保留。"""
        data = {
            "start": "s",
            "note": "a",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "去 a", "target": "a", "tag": "a"},
                ], "extra": "a"},
                {"id": "a", "text": "a", "options": []},
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_rename(path, "a", "b", {
            "start": "s",
            "note": "a",
            "nodes": [
                {"id": "s", "text": "起点", "options": [
                    {"text": "去 a", "target": "b", "tag": "a"},
                ], "extra": "a"},
                {"id": "b", "text": "a", "options": []},
            ],
        })

    def test_same_old_and_new_id_outputs_equivalent_object(self):
        """新旧编号完全相同时成功，输出与原对象等价的 JSON。"""
        original = json.loads(SAMPLE.read_text(encoding="utf-8"))
        result = self.run_and_assert_rename(SAMPLE, "forest", "forest", original)
        self.assertEqual(json.loads(result.stdout[:-1]), original)

    def test_ids_matched_exactly_with_surrounding_whitespace(self):
        """编号按原字符串精确匹配、首尾空白保留：' a ' 与 'a' 互不干扰。"""
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
        self.run_and_assert_rename(path, " a ", " b ", {
            "start": " b ",
            "nodes": [
                {"id": " b ", "text": "带空格", "options": [
                    {"text": "去不带空格", "target": "a"},
                ]},
                {"id": "a", "text": "不带空格", "options": []},
            ],
        })

    def test_chinese_ids_not_escaped(self):
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
        result = self.run_and_assert_rename(path, "森林", "林场", {
            "start": "起点",
            "nodes": [
                {"id": "起点", "text": "出发", "options": [
                    {"text": "进山", "target": "林场"},
                ]},
                {"id": "林场", "text": "到了", "options": []},
            ],
        })
        self.assertIn("林场", result.stdout.decode("utf-8"))
        self.assertNotIn("\\u", result.stdout.decode("utf-8"))

    def test_no_result_file_created(self):
        """成功重命名不在输入文件旁创建任何结果文件。"""
        data = self.load_sample_data()
        path = self.make_sample(data)
        before_entries = set(p.name for p in self.tmp_dir.iterdir())
        result = run_rename(path, "forest", "grove")
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        after_entries = set(p.name for p in self.tmp_dir.iterdir())
        self.assertEqual(before_entries, after_entries, "不应创建结果文件")


class TestRenameFailure(RenameTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_missing_old_node_uses_existing_message(self):
        """旧节点不存在：沿用节点不存在说明，含编号原值。"""
        result = self.run_and_assert_fail(
            SAMPLE, "ghost", "grove", ["文件中不存在编号为 'ghost' 的节点"]
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_missing_old_node_id_keeps_surrounding_whitespace(self):
        """旧编号首尾空白不裁剪，错误说明中按原值引用。"""
        self.run_and_assert_fail(
            SAMPLE, " forest ", "grove",
            ["文件中不存在编号为 ' forest ' 的节点"],
        )

    def test_blank_new_id_rejected(self):
        """新编号全为空白：只报新编号必须包含非空白字符。"""
        result = self.run_and_assert_fail(
            SAMPLE, "forest", "  ", ["新编号必须包含非空白字符"]
        )
        stderr = result.stderr.decode("utf-8")
        self.assertEqual(stderr, "新编号必须包含非空白字符\n")

    def test_empty_new_id_rejected(self):
        """新编号为空字符串同样按空白拒绝。"""
        self.run_and_assert_fail(
            SAMPLE, "forest", "", ["新编号必须包含非空白字符"]
        )

    def test_conflicting_new_id_rejected(self):
        """验收用例：新编号 river 已被其他节点使用，只报编号冲突。"""
        result = self.run_and_assert_fail(
            SAMPLE, "forest", "river", ["新编号已被其他节点使用"]
        )
        stderr = result.stderr.decode("utf-8")
        self.assertEqual(stderr, "新编号已被其他节点使用\n")

    def test_conflict_check_follows_blank_check(self):
        """旧节点存在时，新编号空白先于编号冲突报告。"""
        result = self.run_and_assert_fail(
            SAMPLE, "forest", " ", ["新编号必须包含非空白字符"]
        )
        self.assertNotIn("已被其他节点使用", result.stderr.decode("utf-8"))

    def test_missing_old_node_reported_before_blank_new_id(self):
        """旧节点不存在先于新编号空白报告。"""
        result = self.run_and_assert_fail(
            SAMPLE, "ghost", " ", ["文件中不存在编号为 'ghost' 的节点"]
        )
        self.assertNotIn("非空白字符", result.stderr.decode("utf-8"))

    def test_invalid_structure_in_unreachable_node_fails_validation(self):
        """不可达 side 节点缺少 text：沿用“校验失败：”并定位 nodes[3].text，
        即使问题位于不可达节点也先于重命名报出。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "options": [
                {"text": "去森林", "target": "forest"}]}
        )
        path = self.make_sample(data)
        result = self.run_and_assert_fail(
            path, "forest", "grove", ["校验失败：", "nodes[3].text"]
        )
        self.assertTrue(
            result.stderr.decode("utf-8").startswith("校验失败："),
            "标准错误应以“校验失败：”开头",
        )

    def test_dangling_target_in_unreachable_node_fails_validation(self):
        """不可达 side 节点选项 target 指向不存在的 ghost：定位到
        nodes[3].options[0].target 并点名 ghost，不输出重命名结果。"""
        data = self.load_sample_data()
        data["nodes"].append(
            {"id": "side", "text": "旁路",
             "options": [{"text": "去虚无", "target": "ghost"}]}
        )
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "forest", "grove",
            ["校验失败：", "nodes[3].options[0].target", "ghost"],
        )

    def test_json_syntax_error_uses_existing_category(self):
        """语法错误文件：沿用既有 JSON 语法错误分类，信息含路径与行列。"""
        broken = self.tmp_dir / "broken.json"
        broken.write_text("{\n  !", encoding="utf-8")
        result = self.run_and_assert_fail(
            broken, "forest", "grove",
            ["JSON 语法错误", "第 2 行第 3 列", str(broken)],
        )
        self.assertNotIn("校验失败", result.stderr.decode("utf-8"))

    def test_utf8_decode_error_uses_existing_category(self):
        """UTF-8 解码失败：沿用既有分类且信息含路径。"""
        bad = self.tmp_dir / "bad.json"
        bad.write_bytes(b"\xff")
        self.run_and_assert_fail(bad, "forest", "grove",
                                 ["UTF-8 解码失败", str(bad)])

    def test_unreadable_file_uses_existing_category(self):
        """路径不存在：沿用既有无法读取文件分类，含路径且不创建该文件。"""
        missing = self.tmp_dir / "never_created.json"
        result = run_rename(missing, "forest", "grove")
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("无法读取文件", stderr)
        self.assertIn(str(missing), stderr)
        self.assertFalse(missing.exists(), "重命名不应创建传入的不存在路径")


if __name__ == "__main__":
    unittest.main()
