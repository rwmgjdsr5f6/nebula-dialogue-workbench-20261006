# -*- coding: utf-8 -*-
"""dialogue.py validate 对节点与选项结构的回归测试。

以 sample.json 的独立临时副本为合法对照，每份失败样例只改一处，
固定以下既有字段要求（错误定位使用实际下标，如 nodes[0].options[0].text）：

- 节点必须是对象，且必须含 id、text、options 三个字段；
- 节点 text 必须是字符串（空字符串与纯空白均合法，不算字段缺失）；
- 节点 options 必须是数组（空数组合法）；
- 选项必须是对象，且必须含 text、target 两个字段；
- 选项 text 必须是字符串（空字符串与纯空白同样合法）。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：失败时退出码 2、标准输出为空、标准错误严格为
「校验失败：<原因>」加一个结尾换行且不含调用栈；成功时退出码 0、
标准错误为空、标准输出严格为「校验通过」加一个结尾换行。
每次调用前后核对输入文件字节不变，派生样例写入临时目录并自动清理，
各用例可单独执行，整组重复执行结果一致。
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIALOGUE = PROJECT_DIR / "dialogue.py"
SAMPLE = PROJECT_DIR / "sample.json"

OK_MESSAGE = "校验通过\n"
FAIL_PREFIX = "校验失败："


def run_validate(path):
    """以命令行方式执行 validate，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "validate", str(path)],
        capture_output=True,
    )


class StructureTestCase(unittest.TestCase):
    """公共断言：临时样例写入与清理、文件字节不变、输出流严格匹配。"""

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

    def assert_file_unchanged(self, path, before):
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )

    def run_and_assert_ok(self, path, case_desc):
        """成功：退出码 0，标准错误为空，标准输出严格为校验通过加换行。"""
        before = path.read_bytes()
        result = run_validate(path)
        self.assert_file_unchanged(path, before)
        self.assertEqual(
            result.returncode, 0,
            "{}：退出码应为 0，stderr: {!r}".format(case_desc, result.stderr),
        )
        self.assertEqual(
            result.stderr, b"",
            "{}：成功时标准错误应为空".format(case_desc),
        )
        self.assertEqual(
            result.stdout.decode("utf-8"), OK_MESSAGE,
            "{}：标准输出应只有校验通过和一个结尾换行".format(case_desc),
        )
        return result

    def run_and_assert_fail(self, path, case_desc, reason):
        """失败：退出码 2，标准输出为空，标准错误严格为校验失败加原因加换行。"""
        before = path.read_bytes()
        result = run_validate(path)
        self.assert_file_unchanged(path, before)
        self.assertEqual(
            result.returncode, 2,
            "{}：失败时退出码应为 2".format(case_desc),
        )
        self.assertEqual(
            result.stdout, b"",
            "{}：失败时标准输出应为空".format(case_desc),
        )
        stderr = result.stderr.decode("utf-8")
        self.assertNotIn("Traceback", stderr, "{}：标准错误不应含调用栈".format(case_desc))
        self.assertEqual(
            stderr, FAIL_PREFIX + reason + "\n",
            "{}：标准错误应严格为校验失败加原因加一个结尾换行".format(case_desc),
        )
        return result


class TestNodeStructureFailure(StructureTestCase):
    """节点级结构失败：每份样例只在 nodes[0] 上改一处。"""

    def test_node_not_object(self):
        """nodes[0] 改为 null：报 nodes[0] 必须是对象。"""
        data = self.load_sample_data()
        data["nodes"][0] = None
        path = self.make_sample(data)
        self.run_and_assert_fail(path, "nodes[0] 为 null", "nodes[0] 必须是对象")

    def test_node_missing_id(self):
        """删除 nodes[0].id：报缺少字段并给出完整路径。"""
        data = self.load_sample_data()
        del data["nodes"][0]["id"]
        path = self.make_sample(data)
        self.run_and_assert_fail(path, "nodes[0] 缺 id", "缺少字段 nodes[0].id")

    def test_node_missing_text(self):
        """删除 nodes[0].text：报缺少字段并给出完整路径。"""
        data = self.load_sample_data()
        del data["nodes"][0]["text"]
        path = self.make_sample(data)
        self.run_and_assert_fail(path, "nodes[0] 缺 text", "缺少字段 nodes[0].text")

    def test_node_missing_options(self):
        """删除 nodes[0].options：报缺少字段并给出完整路径。"""
        data = self.load_sample_data()
        del data["nodes"][0]["options"]
        path = self.make_sample(data)
        self.run_and_assert_fail(path, "nodes[0] 缺 options", "缺少字段 nodes[0].options")

    def test_node_text_null(self):
        """nodes[0].text 改为 null：报 nodes[0].text 必须是字符串。"""
        data = self.load_sample_data()
        data["nodes"][0]["text"] = None
        path = self.make_sample(data)
        self.run_and_assert_fail(path, "nodes[0].text 为 null", "nodes[0].text 必须是字符串")

    def test_node_text_number(self):
        """nodes[0].text 改为数字：报 nodes[0].text 必须是字符串。"""
        data = self.load_sample_data()
        data["nodes"][0]["text"] = 42
        path = self.make_sample(data)
        self.run_and_assert_fail(path, "nodes[0].text 为数字", "nodes[0].text 必须是字符串")

    def test_node_text_boolean(self):
        """nodes[0].text 改为布尔值：报 nodes[0].text 必须是字符串。"""
        data = self.load_sample_data()
        data["nodes"][0]["text"] = True
        path = self.make_sample(data)
        self.run_and_assert_fail(path, "nodes[0].text 为布尔值", "nodes[0].text 必须是字符串")

    def test_node_options_null(self):
        """nodes[0].options 改为 null：报 nodes[0].options 必须是数组。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"] = None
        path = self.make_sample(data)
        self.run_and_assert_fail(path, "nodes[0].options 为 null", "nodes[0].options 必须是数组")

    def test_node_options_string(self):
        """nodes[0].options 改为字符串：报 nodes[0].options 必须是数组。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"] = "forest"
        path = self.make_sample(data)
        self.run_and_assert_fail(path, "nodes[0].options 为字符串", "nodes[0].options 必须是数组")

    def test_node_options_object(self):
        """nodes[0].options 改为对象：报 nodes[0].options 必须是数组。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"] = {"text": "向左走", "target": "forest"}
        path = self.make_sample(data)
        self.run_and_assert_fail(path, "nodes[0].options 为对象", "nodes[0].options 必须是数组")


class TestOptionStructureFailure(StructureTestCase):
    """选项级结构失败：每份样例只在 nodes[0].options[0] 上改一处。"""

    def test_option_not_object(self):
        """nodes[0].options[0] 改为 null：报 nodes[0].options[0] 必须是对象。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0] = None
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "nodes[0].options[0] 为 null", "nodes[0].options[0] 必须是对象"
        )

    def test_option_missing_text(self):
        """删除 nodes[0].options[0].text：报缺少字段并给出完整路径。"""
        data = self.load_sample_data()
        del data["nodes"][0]["options"][0]["text"]
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "nodes[0].options[0] 缺 text", "缺少字段 nodes[0].options[0].text"
        )

    def test_option_missing_target(self):
        """删除 nodes[0].options[0].target：报缺少字段并给出完整路径。"""
        data = self.load_sample_data()
        del data["nodes"][0]["options"][0]["target"]
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "nodes[0].options[0] 缺 target", "缺少字段 nodes[0].options[0].target"
        )

    def test_option_text_null(self):
        """nodes[0].options[0].text 改为 null：报该路径必须是字符串。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0]["text"] = None
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "nodes[0].options[0].text 为 null",
            "nodes[0].options[0].text 必须是字符串",
        )

    def test_option_text_number(self):
        """nodes[0].options[0].text 改为数字：报该路径必须是字符串。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0]["text"] = 42
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "nodes[0].options[0].text 为数字",
            "nodes[0].options[0].text 必须是字符串",
        )

    def test_option_text_boolean(self):
        """nodes[0].options[0].text 改为布尔值：报该路径必须是字符串。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0]["text"] = False
        path = self.make_sample(data)
        self.run_and_assert_fail(
            path, "nodes[0].options[0].text 为布尔值",
            "nodes[0].options[0].text 必须是字符串",
        )


class TestStructureSuccess(StructureTestCase):
    """成功对照：空文字与空选项数组均合法，不能当作字段缺失。"""

    def test_verbatim_copy_passes(self):
        """sample.json 的原样临时副本：逐字节复制后应通过。"""
        path = self.tmp_dir / "case.json"
        shutil.copyfile(SAMPLE, path)
        self.run_and_assert_ok(path, "sample.json 原样副本")

    def test_node_text_empty_string_passes(self):
        """nodes[0].text 为空字符串：合法，不算字段缺失。"""
        data = self.load_sample_data()
        data["nodes"][0]["text"] = ""
        path = self.make_sample(data)
        self.run_and_assert_ok(path, "nodes[0].text 为空字符串")

    def test_node_text_whitespace_only_passes(self):
        """nodes[0].text 只含空格和制表符：合法，不算字段缺失。"""
        data = self.load_sample_data()
        data["nodes"][0]["text"] = " \t "
        path = self.make_sample(data)
        self.run_and_assert_ok(path, "nodes[0].text 只含空白")

    def test_option_text_empty_string_passes(self):
        """nodes[0].options[0].text 为空字符串：合法，不算字段缺失。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0]["text"] = ""
        path = self.make_sample(data)
        self.run_and_assert_ok(path, "nodes[0].options[0].text 为空字符串")

    def test_option_text_whitespace_only_passes(self):
        """nodes[0].options[0].text 只含空格和制表符：合法，不算字段缺失。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"][0]["text"] = "\t "
        path = self.make_sample(data)
        self.run_and_assert_ok(path, "nodes[0].options[0].text 只含空白")

    def test_node_options_empty_array_passes(self):
        """nodes[0].options 为空数组：结尾节点合法，应通过。"""
        data = self.load_sample_data()
        data["nodes"][0]["options"] = []
        path = self.make_sample(data)
        self.run_and_assert_ok(path, "nodes[0].options 为空数组")


if __name__ == "__main__":
    unittest.main()
