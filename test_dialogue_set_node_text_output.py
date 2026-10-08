# -*- coding: utf-8 -*-
"""dialogue.py set-node-text 编辑输出落盘后再次读取的命令行回归测试。

与 test_dialogue_set_node_text.py 的分工：后者主要把标准输出按解析后的
JSON 对象核对；本组测试专门验证产品写出的实际字节流——测试把
set-node-text 的标准输出原样保存为另一份 UTF-8 文件（产品本身不保存
结果），再把该文件作为对话文件交给 validate 与单步 preview，确认正文
修改经 JSON 落盘、再次读取后仍能被现有校验与预览观察到。

覆盖同一复用路径上的三种正文：
  * 普通中文正文：forest 改为「林间很安静。」，结果文件 validate 通过，
    从 start 预览选项 1 得到新正文、选项 2 仍为「你到了河边。」；
  * 空字符串正文：预览结果只有一个结尾换行；
  * 含中文、双引号、反斜杠与实际换行的正文：经 JSON 保存和再次读取后，
    预览结果逐字符等于传入正文再加一个结尾换行。
另核对原输入副本的选项 1 仍预览出「你到了森林。」，证明编辑输出与原
文件各自独立；结果对象除 forest 的 text 外与输入等价（start、节点编号、
全部选项及数组顺序保持原样）。失败边界只派生一个样例：把未选中分支
nodes[0].options[1].target 改为 missing 后再修改 forest，编辑命令应以
退出码 2 结束、标准输出为空、标准错误以「校验失败：」开头并包含
nodes[0].options[1].target 与 missing，且无调用栈。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

所有命令执行前后都核对各自输入文件字节不变；sample.json 保持原样，
临时样例在测试结束后清理，用例可重复运行且结果一致。
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


def run_command(args):
    """以命令行方式执行 dialogue.py，返回 CompletedProcess（不抛异常）。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE)] + [str(a) for a in args],
        capture_output=True,
    )


class SetNodeTextOutputRoundTripTestCase(unittest.TestCase):
    """编辑输出原样落盘后再读取：set-node-text / validate / preview 闭环。"""

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

    def sample_copy(self, name="input.json"):
        """复制一份 sample.json 的独立字节副本（原样复制，不重新序列化）。"""
        path = self.tmp_dir / name
        shutil.copyfile(SAMPLE, self.tmp_dir / name)
        return path

    def derived_copy(self, mutate, name="input.json"):
        """以解析后的样例数据派生一份独立临时样例。"""
        data = json.loads(SAMPLE.read_text(encoding="utf-8"))
        mutate(data)
        path = self.tmp_dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    def assert_file_unchanged(self, path, before, label=None):
        self.assertEqual(
            before,
            path.read_bytes(),
            "输入文件在执行后发生变化（{}）：{}".format(label or "", path),
        )

    def edit_and_save_stdout(self, input_path, output_path, node_id, new_text):
        """执行 set-node-text，并把实际标准输出原样保存为另一份文件。

        产品本身只写标准输出、不保存结果；保存动作由测试完成。断言：
        退出码 0、标准错误为空、标准输出为单行完整 JSON 加恰好一个结尾
        换行（中文直接呈现），且输入文件字节不变。
        """
        before = input_path.read_bytes()
        result = run_command(
            ["set-node-text", input_path, "--node", node_id, "--text", new_text]
        )
        self.assert_file_unchanged(input_path, before, "set-node-text")
        self.assertEqual(
            result.returncode, 0, "编辑命令应退出码 0；stderr={!r}".format(
                result.stderr)
        )
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")

        stdout = result.stdout
        self.assertTrue(
            stdout.endswith(b"\n"),
            "标准输出应以一个结尾换行结束：{!r}".format(stdout),
        )
        self.assertEqual(
            stdout.count(b"\n"), 1,
            "标准输出应为单行 JSON 加一个结尾换行：{!r}".format(stdout),
        )
        # 正文中的换行按 JSON 规则转义，原始字节里不出现额外实际换行。
        self.assertNotIn(b"\r", stdout)
        # 中文直接呈现，不转义为 \\uXXXX。
        self.assertNotIn(b"\\u", stdout)

        # 原样落盘：不重新序列化，直接把标准输出字节写成 UTF-8 文件。
        self.assertFalse(output_path.exists(), "结果文件不应由产品预先创建")
        output_path.write_bytes(stdout)
        return result

    def assert_validate_ok(self, path):
        """validate：退出码 0、标准错误为空、只输出「校验通过」加换行。"""
        before = path.read_bytes()
        result = run_command(["validate", path])
        self.assert_file_unchanged(path, before, "validate")
        self.assertEqual(result.returncode, 0, "stderr={!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "校验成功时标准错误应为空")
        self.assertEqual(
            result.stdout, "校验通过\n".encode("utf-8"),
            "validate 应只输出校验通过加一个结尾换行",
        )

    def assert_preview_from_start(self, path, choice, expected_text):
        """从 start 单步预览：退出码 0、标准错误为空，输出逐字符等于
        目标正文再加一个结尾换行；输入文件字节不变。"""
        before = path.read_bytes()
        result = run_command(
            ["preview", path, "--choice", str(choice)]
        )
        self.assert_file_unchanged(
            path, before, "preview --choice {}".format(choice))
        self.assertEqual(result.returncode, 0, "stderr={!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "预览成功时标准错误应为空")
        expected_bytes = (expected_text + "\n").encode("utf-8")
        self.assertEqual(
            result.stdout, expected_bytes,
            "预览输出应逐字符等于正文加一个结尾换行",
        )

    def expected_sample_with_forest_text(self, new_text):
        """样例数据仅把 forest 的 text 换成 new_text 的期望对象。"""
        expected = json.loads(SAMPLE.read_text(encoding="utf-8"))
        expected["nodes"][1]["text"] = new_text
        return expected

    def assert_result_object_equivalent(self, output_path, new_text):
        """结果文件解析后：仅 forest 的 text 改变，其余与输入等价。"""
        saved = json.loads(output_path.read_text(encoding="utf-8"))
        expected = self.expected_sample_with_forest_text(new_text)
        self.assertEqual(saved, expected, "结果对象除 forest.text 外应与输入等价")
        # 逐项再核对一遍关键不变量，使失败定位更直接。
        original = json.loads(SAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(saved["start"], original["start"], "start 应保持原样")
        self.assertEqual(
            [node["id"] for node in saved["nodes"]],
            [node["id"] for node in original["nodes"]],
            "节点编号与顺序应保持原样",
        )
        self.assertEqual(
            [node["options"] for node in saved["nodes"]],
            [node["options"] for node in original["nodes"]],
            "全部选项及数组顺序应保持原样",
        )
        self.assertEqual(
            [node["text"] for node in saved["nodes"] if node["id"] != "forest"],
            [node["text"] for node in original["nodes"] if node["id"] != "forest"],
            "其他节点正文应保持原样",
        )

    def test_quiet_forest_text_round_trip(self):
        """普通中文正文：编辑输出落盘后可被 validate 与 preview 观察到。"""
        input_path = self.sample_copy("input.json")
        output_path = self.tmp_dir / "edited.json"
        new_text = "林间很安静。"

        result = self.edit_and_save_stdout(
            input_path, output_path, "forest", new_text
        )
        # 中文直接呈现在原始输出字节中。
        self.assertIn(new_text.encode("utf-8"), result.stdout)

        # 落盘字节即标准输出；可被再次解析为完整对话对象。
        self.assert_result_object_equivalent(output_path, new_text)

        # 结果文件通过整份校验。
        self.assert_validate_ok(output_path)

        # 从起点单步预览：选项 1 为新正文，选项 2 仍是河边正文。
        self.assert_preview_from_start(output_path, 1, new_text)
        self.assert_preview_from_start(output_path, 2, "你到了河边。")

        # 再校验一次，证明多次只读命令之间互不影响。
        self.assert_validate_ok(output_path)

        # 原输入副本独立：选项 1 仍预览出修改前的森林正文。
        self.assert_preview_from_start(input_path, 1, "你到了森林。")
        self.assert_preview_from_start(input_path, 2, "你到了河边。")
        self.assert_validate_ok(input_path)

    def test_empty_text_round_trip(self):
        """空字符串正文：落盘再读取后预览结果只有一个结尾换行。"""
        input_path = self.sample_copy("empty_input.json")
        output_path = self.tmp_dir / "empty_edited.json"
        new_text = ""

        self.edit_and_save_stdout(input_path, output_path, "forest", new_text)
        self.assert_result_object_equivalent(output_path, new_text)
        self.assert_validate_ok(output_path)

        # forest 正文为空：预览输出恰好一个结尾换行。
        self.assert_preview_from_start(output_path, 1, "")
        # 未修改的分支不受影响。
        self.assert_preview_from_start(output_path, 2, "你到了河边。")

        # 原文件保持修改前内容。
        self.assert_preview_from_start(input_path, 1, "你到了森林。")

    def test_special_text_round_trip(self):
        """中文、双引号、反斜杠与实际换行：经 JSON 保存再读取后逐字符一致。"""
        input_path = self.sample_copy("special_input.json")
        output_path = self.tmp_dir / "special_edited.json"
        # 同时包含中文、英文双引号、一个反斜杠与一个实际换行（不以下行结尾）。
        new_text = '他说："林间\\小路"\n第二行'

        result = self.edit_and_save_stdout(
            input_path, output_path, "forest", new_text
        )
        # 实际换行在单行 JSON 中只能以转义形式出现：原始字节里除结尾换行外，
        # 不允许出现正文中那个换行的原始字节；JSON 转义序列 \\n 应当存在。
        self.assertIn(b"\\n", result.stdout)
        self.assertNotIn(new_text.encode("utf-8"), result.stdout)
        # 双引号与反斜杠按 JSON 规则转义后仍可被解析还原。
        self.assert_result_object_equivalent(output_path, new_text)
        self.assert_validate_ok(output_path)

        # 预览输出逐字符等于传入正文再加一个结尾换行：正文内换行实际换行
        # 与输出末尾的换行都计入核对。
        self.assert_preview_from_start(output_path, 1, new_text)
        self.assert_preview_from_start(output_path, 2, "你到了河边。")

        # 原文件保持修改前内容。
        self.assert_preview_from_start(input_path, 1, "你到了森林。")

    def test_dangling_unselected_target_fails_before_edit(self):
        """失败边界：未选中分支 target 悬空时，整份校验先于正文修改失败。

        只派生一个样例：把 nodes[0].options[1]（未选中的河边分支）的
        target 改为 missing，再尝试修改 forest。编辑命令退出码 2、标准
        输出为空、标准错误以「校验失败：」开头并包含字段位置与 missing，
        无调用栈；输入文件字节不变。
        """
        input_path = self.derived_copy(lambda data: data["nodes"][0][
            "options"][1].__setitem__("target", "missing"), name="broken_input.json")
        output_path = self.tmp_dir / "should_not_exist.json"

        before = input_path.read_bytes()
        result = run_command(
            ["set-node-text", input_path, "--node", "forest",
             "--text", "林间很安静。"]
        )
        self.assert_file_unchanged(input_path, before, "失败的 set-node-text")

        self.assertEqual(result.returncode, 2, "校验失败时退出码应为 2")
        self.assertEqual(result.stdout, b"", "失败时标准输出应为空")
        stderr = result.stderr.decode("utf-8")
        self.assertTrue(
            stderr.startswith("校验失败："),
            "标准错误应以“校验失败：”开头，实际 {!r}".format(stderr),
        )
        self.assertIn("nodes[0].options[1].target", stderr)
        self.assertIn("missing", stderr)
        self.assertNotIn("Traceback", stderr, "标准错误中不应出现调用栈")

        # 产品不保存结果：失败时不应留下任何输出文件。
        self.assertFalse(output_path.exists(), "校验失败不应产生结果文件")

        # 原文件仍可预览出未改动的悬空分支之外的内容这一点不做要求，
        # 但样例仓库文件必须保持原样（tearDown 统一核对）。


if __name__ == "__main__":
    unittest.main()
