# -*- coding: utf-8 -*-
"""dialogue.py 单步分支预览（preview）命令行回归测试。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出、标准错误，以及输入文件在执行前后字节不变。
所有临时样例由测试自行创建并清理，用例可重复运行且结果一致。
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


def run_preview(path, choice):
    """以命令行方式执行 preview，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "preview", str(path), "--choice", str(choice)],
        capture_output=True,
    )


class PreviewTestCase(unittest.TestCase):
    """公共断言：文件字节不变、无调用栈、临时样例清理。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def make_sample(self, data):
        """把数据写成临时样例文件，返回路径。"""
        path = self.tmp_dir / "case.json"
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def load_sample_data(self):
        return json.loads(SAMPLE.read_text(encoding="utf-8"))

    def assert_file_unchanged(self, path, before):
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )

    def assert_no_traceback(self, stderr):
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")

    def run_and_assert_ok(self, path, choice, expected_stdout):
        before = path.read_bytes()
        result = run_preview(path, choice)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"),
            expected_stdout,
            "标准输出应只有目标节点文字和一个结尾换行",
        )
        return result

    def run_and_assert_fail(self, path, choice, expected_parts):
        before = path.read_bytes()
        result = run_preview(path, choice)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestPreviewSuccess(PreviewTestCase):
    """成功路径：退出码 0、标准错误为空、输出仅目标文字加换行。"""

    def test_choice_1_outputs_forest_text(self):
        self.run_and_assert_ok(SAMPLE, 1, "你到了森林。\n")

    def test_choice_2_outputs_river_text(self):
        self.run_and_assert_ok(SAMPLE, 2, "你到了河边。\n")

    def test_choice_number_follows_option_array_order(self):
        """交换起点两项 options 后，编号 1 应输出原第二项的河边文字。"""
        data = self.load_sample_data()
        options = data["nodes"][0]["options"]
        options[0], options[1] = options[1], options[0]
        path = self.make_sample(data)
        self.run_and_assert_ok(path, 1, "你到了河边。\n")

    def test_self_loop_option_steps_once(self):
        """起点选项指向自身：允许循环引用，每次仅走一步，文字只输出一次。"""
        data = {
            "start": "loop",
            "nodes": [
                {
                    "id": "loop",
                    "text": "你在原地打转。",
                    "options": [{"text": "再走一步", "target": "loop"}],
                }
            ],
        }
        path = self.make_sample(data)
        self.run_and_assert_ok(path, 1, "你在原地打转。\n")


class TestPreviewFailure(PreviewTestCase):
    """失败路径：退出码 2、标准输出为空、标准错误无调用栈。"""

    def test_choice_zero_out_of_range(self):
        self.run_and_assert_fail(SAMPLE, 0, ["start", "--choice 0", "1 到 2"])

    def test_choice_three_out_of_range(self):
        self.run_and_assert_fail(SAMPLE, 3, ["start", "--choice 3", "1 到 2"])

    def test_choice_not_an_integer(self):
        self.run_and_assert_fail(SAMPLE, "abc", ["'abc'", "start", "无法解析为整数"])

    def test_start_node_with_empty_options(self):
        """起点 options 为空时选择 1，应报告结尾节点没有有效选项。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"] = []
        path = self.make_sample(data)
        self.run_and_assert_fail(path, 1, ["结尾节点", "没有有效选项"])

    def test_unselected_option_with_missing_target_fails_validation(self):
        """未选中的第二个选项 target 改为 missing：选择 1 仍先校验失败。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][1]["target"] = "missing"
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, 1, ["nodes[0].options[1].target", "missing"]
        )


if __name__ == "__main__":
    unittest.main()
