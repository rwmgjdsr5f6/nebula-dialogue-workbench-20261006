# -*- coding: utf-8 -*-
"""dialogue.py 整份对话校验（validate）命令行回归测试。

覆盖结构与引用校验（含从起点不可达的节点）：
成功路径（sample.json、不可达合法结尾节点、单节点自引用循环）与
各只引入一个问题的失败路径（重复编号、start 悬空引用、不可达节点
缺 text、不可达节点选项 target 悬空）。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出、标准错误、字段定位，以及输入文件在
执行前后字节不变。所有派生样例独立写入临时目录并自动清理，
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

OK_MESSAGE = "校验通过\n"


def run_validate(path):
    """以命令行方式执行 validate，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "validate", str(path)],
        capture_output=True,
    )


class ValidateTestCase(unittest.TestCase):
    """公共断言：临时样例写入与清理、文件字节不变、无调用栈。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

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

    def with_unreachable_ending(self, data):
        """在样例末尾追加一个从起点不可达的合法结尾节点（nodes[3]）。"""
        data["nodes"].append(
            {"id": "unused", "text": "无人抵达的角落。", "options": []}
        )
        return data

    def assert_file_unchanged(self, path, before):
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )

    def assert_no_traceback(self, stderr):
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")

    def run_and_assert_ok(self, path):
        """成功：退出码 0，标准输出仅为校验通过加一个结尾换行，标准错误为空。"""
        before = path.read_bytes()
        result = run_validate(path)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"),
            OK_MESSAGE,
            "标准输出应只有校验通过和一个结尾换行",
        )
        return result

    def run_and_assert_fail(self, path, expected_parts):
        """失败：退出码 2，标准输出为空，标准错误含校验失败与原因且无调用栈。"""
        before = path.read_bytes()
        result = run_validate(path)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assertIn("校验失败", stderr, "标准错误应说明校验失败")
        self.assert_no_traceback(stderr)
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestValidateSuccess(ValidateTestCase):
    """成功路径：整份对话结构与引用均合法。"""

    def test_sample_json_passes(self):
        """直接校验仓库自带 sample.json：输出、错误流、退出码与文件字节逐一核对。"""
        self.run_and_assert_ok(SAMPLE)

    def test_unreachable_terminal_node_passes(self):
        """追加一个任何选项都不指向的合法结尾节点：仍应通过（不要求可达）。"""
        data = self.with_unreachable_ending(self.load_sample_data())
        path = self.make_sample(data)
        self.run_and_assert_ok(path)

    def test_single_node_self_loop_passes(self):
        """只有一个节点且其选项指向自身：自引用循环合法，应通过。"""
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
        self.run_and_assert_ok(path)


class TestValidateFailure(ValidateTestCase):
    """失败路径：每份样例只引入一个问题，错误定位到具体 JSON 字段。"""

    def test_duplicate_node_id(self):
        """第二个节点编号改成与第一个相同：报两个定位与编号重复。"""
        data = self.load_sample_data()
        data["nodes"][1]["id"] = data["nodes"][0]["id"]
        path = self.make_sample(data)
        # 实际文案为「节点编号重复：nodes[0].id 与 nodes[1].id 同为 ...」。
        self.run_and_assert_fail(
            path, ["nodes[0].id", "nodes[1].id", "编号重复"]
        )

    def test_start_points_to_missing_node(self):
        """start 改为不存在的编号 missing：错误同时点名 start 与 missing。"""
        data = self.load_sample_data()
        data["start"] = "missing"
        path = self.make_sample(data)
        self.run_and_assert_fail(path, ["start", "missing"])

    def test_unreachable_node_missing_text(self):
        """不可达结尾节点缺少 text：定位到 nodes[3].text。"""
        data = self.with_unreachable_ending(self.load_sample_data())
        del data["nodes"][3]["text"]
        path = self.make_sample(data)
        self.run_and_assert_fail(path, ["nodes[3].text"])

    def test_unreachable_node_option_target_missing(self):
        """不可达结尾节点新增 target 为 missing 的选项：定位到
        nodes[3].options[0].target，并点名 missing。"""
        data = self.with_unreachable_ending(self.load_sample_data())
        data["nodes"][3]["options"] = [
            {"text": "走向未知", "target": "missing"}
        ]
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, ["nodes[3].options[0].target", "missing"]
        )


if __name__ == "__main__":
    unittest.main()
