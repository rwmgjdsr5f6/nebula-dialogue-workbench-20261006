#!/usr/bin/env python3
"""dialogue.py preview 命令的命令行回归测试。

仅使用 Python 3 标准库。在项目目录执行：

    python -m unittest discover -v

即可运行全部用例，无需额外安装依赖或访问网络。
每个用例以退出码、标准输出、标准错误以及输入文件字节是否变化为验收依据；
临时样例在用例结束后自动清理，测试可重复运行且结果一致。
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DIALOGUE_PY = os.path.join(PROJECT_DIR, "dialogue.py")
SAMPLE_JSON = os.path.join(PROJECT_DIR, "sample.json")


def run_preview(path, choice):
    """以独立子进程执行 preview 命令，返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, DIALOGUE_PY, "preview", path, "--choice", str(choice)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    )


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


class PreviewTestCase(unittest.TestCase):
    """公共断言：输入文件字节不变、标准错误无调用栈。"""

    def assert_file_unchanged(self, path, before_bytes):
        self.assertEqual(
            before_bytes,
            read_bytes(path),
            "执行后输入文件字节发生变化：{}".format(path),
        )

    def assert_no_traceback(self, result):
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("Traceback", result.stdout)

    def make_temp_sample(self, data):
        """把修改后的样例写入临时文件，用例结束时自动删除。"""
        fd, path = tempfile.mkstemp(suffix=".json", prefix="dialogue_test_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        self.addCleanup(os.remove, path)
        return path

    def load_sample_data(self):
        with open(SAMPLE_JSON, "r", encoding="utf-8") as f:
            return json.load(f)


class TestPreviewSuccess(PreviewTestCase):
    """正常分支：退出码 0、标准错误为空、标准输出只有目标节点文字。"""

    def test_choice_1_outputs_forest(self):
        before = read_bytes(SAMPLE_JSON)
        result = run_preview(SAMPLE_JSON, 1)
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stderr)
        self.assertEqual("你到了森林。\n", result.stdout)
        self.assert_file_unchanged(SAMPLE_JSON, before)

    def test_choice_2_outputs_river(self):
        before = read_bytes(SAMPLE_JSON)
        result = run_preview(SAMPLE_JSON, 2)
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stderr)
        self.assertEqual("你到了河边。\n", result.stdout)
        self.assert_file_unchanged(SAMPLE_JSON, before)

    def test_swapped_options_choice_1_outputs_river(self):
        """交换起点两项 options 后，编号 1 应输出河边：编号由数组顺序决定。"""
        data = self.load_sample_data()
        options = data["nodes"][0]["options"]
        options[0], options[1] = options[1], options[0]
        path = self.make_temp_sample(data)

        before = read_bytes(path)
        result = run_preview(path, 1)
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stderr)
        self.assertEqual("你到了河边。\n", result.stdout)
        self.assert_file_unchanged(path, before)

    def test_self_loop_choice_1_outputs_text_once(self):
        """起点选项指向自身：允许循环引用，每次预览只走一步。"""
        data = {
            "start": "loop",
            "nodes": [
                {
                    "id": "loop",
                    "text": "你在原地打转。",
                    "options": [{"text": "继续", "target": "loop"}],
                }
            ],
        }
        path = self.make_temp_sample(data)

        before = read_bytes(path)
        result = run_preview(path, 1)
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stderr)
        self.assertEqual("你在原地打转。\n", result.stdout)
        self.assert_file_unchanged(path, before)


class TestPreviewFailure(PreviewTestCase):
    """失败分支：退出码 2、标准输出为空、标准错误无调用栈且含定位信息。"""

    def assert_failed(self, result, expected_parts):
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assert_no_traceback(result)
        for part in expected_parts:
            self.assertIn(part, result.stderr)

    def test_choice_0_out_of_range(self):
        before = read_bytes(SAMPLE_JSON)
        result = run_preview(SAMPLE_JSON, 0)
        self.assert_failed(result, ["start", "0", "1 到 2"])
        self.assert_file_unchanged(SAMPLE_JSON, before)

    def test_choice_3_out_of_range(self):
        before = read_bytes(SAMPLE_JSON)
        result = run_preview(SAMPLE_JSON, 3)
        self.assert_failed(result, ["start", "3", "1 到 2"])
        self.assert_file_unchanged(SAMPLE_JSON, before)

    def test_choice_abc_not_an_integer(self):
        before = read_bytes(SAMPLE_JSON)
        result = run_preview(SAMPLE_JSON, "abc")
        self.assert_failed(result, ["abc", "start", "无法解析为整数"])
        self.assert_file_unchanged(SAMPLE_JSON, before)

    def test_empty_options_at_start(self):
        """起点 options 为空时选择 1：报告结尾节点没有有效选项。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"] = []
        path = self.make_temp_sample(data)

        before = read_bytes(path)
        result = run_preview(path, 1)
        self.assert_failed(result, ["结尾节点", "没有有效选项"])
        self.assert_file_unchanged(path, before)

    def test_unselected_option_target_missing(self):
        """未选中的第二个选项 target 指向 missing：选择 1 仍先校验失败。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][1]["target"] = "missing"
        path = self.make_temp_sample(data)

        before = read_bytes(path)
        result = run_preview(path, 1)
        self.assert_failed(result, ["nodes[0].options[1].target", "missing"])
        self.assert_file_unchanged(path, before)


if __name__ == "__main__":
    unittest.main()
