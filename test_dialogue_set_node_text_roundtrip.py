# -*- coding: utf-8 -*-
"""dialogue.py set-node-text 输出再读取（roundtrip）命令行回归测试。

现有正文修改测试主要核对解析后的对象；本组专门验证 set-node-text 的
标准输出被原样保存为另一份 UTF-8 对话文件后，重新作为输入读取时，
正文修改仍能由现有 validate 与单步 preview 观察到：

- 以 sample.json 的独立副本为输入，把 forest 正文替换为「林间很安静。」，
  实际标准输出原样保存为结果文件；对结果文件 validate 只输出
  「校验通过」加换行，从起点 preview 选择 1 只输出「林间很安静。」加
  换行、选择 2 仍输出「你到了河边。」加换行；原输入的选项 1 仍预览出
  「你到了森林。」，证明编辑输出与原文件各自独立；结果对象除 forest
  的 text 外与输入等价，start、节点编号、全部选项及数组顺序保持原样。
- 同一复用路径覆盖空字符串正文（预览结果只有一个结尾换行）与含中文、
  双引号、反斜杠和实际换行的正文（经 JSON 保存和再次读取后，预览结果
  逐字符等于传入正文再加一个换行）。
- 失败边界：派生样例将未选中分支的 target 改为 missing 后再修改
  forest，编辑命令返回 2，标准输出为空，标准错误以「校验失败：」开头
  并包含 nodes[0].options[1].target 与 missing，且无调用栈。

产品命令、数据格式及错误语义保持现状；输出的保存由测试完成，产品仍只
向标准输出提供编辑结果。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

验收依据：退出码、标准输出、标准错误，以及所有命令执行前后各自输入
文件字节不变、仓库样例保持原样；临时样例在测试结束后自动清理，用例
可重复运行且结果一致。
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
# text 变化，start、节点编号、全部选项及数组顺序与原对象完全一致。
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

# 含中文、双引号、反斜杠和实际换行的正文。
SPECIAL_TEXT = '他说："看\\这里"\n第二行'


def run_dialogue(*args):
    """以命令行方式执行 dialogue.py，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE)] + [str(a) for a in args],
        capture_output=True,
    )


class RoundtripTestCase(unittest.TestCase):
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

    def make_input_copy(self, name="input.json"):
        """把 sample.json 的当前字节复制为独立的临时输入文件，返回路径。"""
        path = self.tmp_dir / name
        path.write_bytes(SAMPLE.read_bytes())
        return path

    def run_keeping_file(self, path, *args):
        """执行命令并核对给定文件在执行前后字节不变，返回 CompletedProcess。"""
        before = path.read_bytes()
        result = run_dialogue(*args)
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化：{}".format(path),
        )
        return result

    def assert_no_traceback(self, stderr):
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")

    def run_set_text_and_save(self, input_path, new_text, result_name="result.json"):
        """对输入文件执行 set-node-text 修改 forest 正文，核对成功后的输出
        形态（退出码 0、标准错误为空、单行完整 JSON 加一个结尾换行、中文
        不转义），再把实际标准输出原样保存为另一份 UTF-8 文件并返回路径。
        输入文件字节保持不变。"""
        result = self.run_keeping_file(
            input_path, "set-node-text", input_path,
            "--node", "forest", "--text", new_text,
        )
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        stdout = result.stdout.decode("utf-8")
        self.assertTrue(
            stdout.endswith("\n"), "标准输出应以一个结尾换行结束：{!r}".format(stdout)
        )
        self.assertNotIn(
            "\n", stdout[:-1], "结尾换行之前不应再有换行：{!r}".format(stdout)
        )
        self.assertNotIn("\\u", stdout, "中文应直接呈现，不转义")
        # 输出的保存由测试完成：实际标准输出原样写入另一份 UTF-8 文件。
        result_path = self.tmp_dir / result_name
        result_path.write_bytes(result.stdout)
        return result_path

    def run_and_assert_validate_ok(self, path):
        """validate：退出码 0、标准错误为空，只输出「校验通过」加换行。"""
        result = self.run_keeping_file(path, "validate", path)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "校验通过时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"), "校验通过\n",
            "validate 应只输出校验通过加换行",
        )
        return result

    def run_and_assert_preview(self, path, choice, expected_text):
        """preview：退出码 0、标准错误为空，只输出目标正文加一个换行。"""
        result = self.run_keeping_file(path, "preview", path, "--choice", choice)
        self.assertEqual(result.returncode, 0, "stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "预览成功时标准错误应为空")
        self.assertEqual(
            result.stdout.decode("utf-8"), expected_text + "\n",
            "preview 应只输出目标节点正文加一个结尾换行",
        )
        return result


class TestSetNodeTextRoundtrip(RoundtripTestCase):
    """编辑输出保存为对话文件后，修改仍可由 validate 与 preview 观察到。"""

    def test_forest_quiet_roundtrip(self):
        """验收用例：forest 改为「林间很安静。」的输出再读取后，
        校验通过，两个分支的预览各自正确，且与原输入文件各自独立。"""
        input_path = self.make_input_copy()
        result_path = self.run_set_text_and_save(input_path, "林间很安静。")

        # 结果文件是完整对话：整份校验通过。
        self.run_and_assert_validate_ok(result_path)

        # 从起点预览：选项 1 看到新正文，选项 2 仍是原分支正文。
        self.run_and_assert_preview(result_path, "1", "林间很安静。")
        self.run_and_assert_preview(result_path, "2", "你到了河边。")

        # 原输入不受影响：选项 1 仍预览出原正文，两文件各自独立。
        self.run_and_assert_preview(input_path, "1", "你到了森林。")
        self.run_and_assert_validate_ok(input_path)

        # 结果对象除 forest 的 text 外与输入等价：start、节点编号、
        # 全部选项及数组顺序保持原样。
        result_object = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result_object, EXPECTED_FOREST_QUIET)
        input_object = json.loads(input_path.read_text(encoding="utf-8"))
        self.assertEqual(result_object["start"], input_object["start"])
        self.assertEqual(
            [node["id"] for node in result_object["nodes"]],
            [node["id"] for node in input_object["nodes"]],
            "节点编号及数组顺序应保持原样",
        )
        self.assertEqual(
            [node["options"] for node in result_object["nodes"]],
            [node["options"] for node in input_object["nodes"]],
            "全部选项及数组顺序应保持原样",
        )
        # 中文在保存的结果文件中直接呈现。
        self.assertIn("林间很安静。", result_path.read_text(encoding="utf-8"))

    def test_empty_text_roundtrip(self):
        """空字符串正文经保存再读取后，预览结果只有一个结尾换行。"""
        input_path = self.make_input_copy()
        result_path = self.run_set_text_and_save(input_path, "")

        self.run_and_assert_validate_ok(result_path)
        self.run_and_assert_preview(result_path, "1", "")
        # 另一分支不受影响。
        self.run_and_assert_preview(result_path, "2", "你到了河边。")

        result_object = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result_object["nodes"][1]["text"], "")

    def test_special_text_roundtrip(self):
        """含中文、双引号、反斜杠和实际换行的正文经 JSON 保存和再次读取后，
        预览结果逐字符等于传入正文再加一个换行（正文中的换行与输出末尾的
        换行都计入核对）。"""
        input_path = self.make_input_copy()
        result_path = self.run_set_text_and_save(input_path, SPECIAL_TEXT)

        self.run_and_assert_validate_ok(result_path)
        self.run_and_assert_preview(result_path, "1", SPECIAL_TEXT)
        # 另一分支不受影响。
        self.run_and_assert_preview(result_path, "2", "你到了河边。")

        # 保存的结果文件再次读取后，正文逐字符等于传入正文。
        result_object = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(result_object["nodes"][1]["text"], SPECIAL_TEXT)
        # 原输入仍预览出原正文，两文件各自独立。
        self.run_and_assert_preview(input_path, "1", "你到了森林。")


class TestSetNodeTextRoundtripFailure(RoundtripTestCase):
    """失败边界：整份校验失败时不产生编辑输出。"""

    def test_dangling_unselected_target_fails_before_edit(self):
        """派生样例将未选中分支的 target 改为 missing 后再修改 forest：
        退出码 2、标准输出为空，标准错误以「校验失败：」开头并包含
        nodes[0].options[1].target 与 missing，且无调用栈。"""
        data = json.loads(SAMPLE.read_text(encoding="utf-8"))
        data["nodes"][0]["options"][1]["target"] = "missing"
        input_path = self.tmp_dir / "input.json"
        input_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        result = self.run_keeping_file(
            input_path, "set-node-text", input_path,
            "--node", "forest", "--text", "林间很安静。",
        )
        self.assertEqual(result.returncode, 2, "失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assert_no_traceback(stderr)
        self.assertTrue(
            stderr.startswith("校验失败："), "标准错误应以“校验失败：”开头"
        )
        self.assertIn("nodes[0].options[1].target", stderr)
        self.assertIn("missing", stderr)

        # 未产生任何结果文件，临时目录中只有输入文件。
        self.assertEqual(
            [p.name for p in self.tmp_dir.iterdir()], ["input.json"],
            "校验失败时不应创建结果文件",
        )


if __name__ == "__main__":
    unittest.main()
