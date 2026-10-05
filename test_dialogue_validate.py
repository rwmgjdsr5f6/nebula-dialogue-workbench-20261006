# -*- coding: utf-8 -*-
"""dialogue.py 整份对话校验（validate）命令行回归测试。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出、标准错误，以及输入文件在执行前后字节不变。
派生样例由测试独立写入临时目录并在结束后清理，sample.json 保持原样，
用例可重复运行且结果一致。
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


def run_validate(path):
    """以命令行方式执行 validate，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "validate", str(path)],
        capture_output=True,
    )


class ValidateTestCase(unittest.TestCase):
    """公共断言：文件字节不变、无调用栈、临时样例清理。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def make_sample(self, data, name="case.json"):
        """把数据写成合法 UTF-8 JSON 的临时样例文件，返回路径。"""
        path = self.tmp_dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def load_sample_data(self):
        return json.loads(SAMPLE.read_text(encoding="utf-8"))

    def add_unreachable_ending(self, data):
        """在 nodes 末尾追加一个从起点不可达的合法结尾节点，返回数据本身。"""
        data["nodes"].append(
            {"id": "cave", "text": "你到了山洞。", "options": []}
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
        before = path.read_bytes()
        result = run_validate(path)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"),
            "校验通过\n",
            "标准输出应只有校验通过和一个结尾换行",
        )
        return result

    def run_and_assert_fail(self, path, expected_parts):
        before = path.read_bytes()
        result = run_validate(path)
        self.assert_file_unchanged(path, before)
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertIn("校验失败", stderr, "标准错误应包含校验失败说明")
        for part in expected_parts:
            self.assertIn(part, stderr, "标准错误应包含 {!r}".format(part))
        return result


class TestValidateSuccess(ValidateTestCase):
    """成功路径：退出码 0、标准错误为空、输出仅“校验通过”加换行。"""

    def test_sample_json_passes(self):
        self.run_and_assert_ok(SAMPLE)

    def test_unreachable_ending_node_passes(self):
        """从起点不可达的合法结尾节点仍应通过整份校验。"""
        data = self.add_unreachable_ending(self.load_sample_data())
        path = self.make_sample(data)
        self.run_and_assert_ok(path)

    def test_single_node_self_loop_passes(self):
        """单节点自引用循环：允许循环引用，应通过校验。"""
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
    """失败路径：每份样例只引入一个问题，退出码 2、标准输出为空、
    标准错误含“校验失败”与对应字段定位，且无调用栈。"""

    def test_duplicate_node_id(self):
        """把 nodes[1].id 改成 nodes[0].id：应报告重复编号及两处位置。"""
        data = self.load_sample_data()
        data["nodes"][1]["id"] = data["nodes"][0]["id"]
        path = self.make_sample(data)
        self.run_and_assert_fail(path, ["nodes[0].id", "nodes[1].id", "重复"])

    def test_start_references_missing_node(self):
        """把 start 改为不存在的 missing：应定位 start 并给出 missing。"""
        data = self.load_sample_data()
        data["start"] = "missing"
        path = self.make_sample(data)
        self.run_and_assert_fail(path, ["start", "missing"])

    def test_unreachable_ending_missing_text(self):
        """不可达结尾节点删除 text 字段：应定位 nodes[3].text。"""
        data = self.add_unreachable_ending(self.load_sample_data())
        del data["nodes"][3]["text"]
        path = self.make_sample(data)
        self.run_and_assert_fail(path, ["nodes[3].text"])

    def test_unreachable_ending_option_target_missing(self):
        """不可达结尾节点的空 options 加入 target 为 missing 的选项：
        应定位 nodes[3].options[0].target 并给出 missing。"""
        data = self.add_unreachable_ending(self.load_sample_data())
        data["nodes"][3]["options"].append(
            {"text": "继续深入", "target": "missing"}
        )
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, ["nodes[3].options[0].target", "missing"]
        )


if __name__ == "__main__":
    unittest.main()
