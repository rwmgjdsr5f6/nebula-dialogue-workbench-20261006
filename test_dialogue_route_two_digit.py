# -*- coding: utf-8 -*-
"""dialogue.py 路线查询（route）两位数选项编号的命令行回归测试。

现有 route 回归样例只用到一位数选项编号；本文件补充固定样例，验证等长
路线按完整选项编号序列做**数值**字典序比较时的两个既有行为：

1. 编号 2 与 10 的比较：序列 [2,1] 必须优先于 [10,1]（数值比较
   2 < 10，而不是字符串比较 "10" < "2"）。
2. 共同前缀之后的比较：序列 [1,2,1] 必须优先于 [1,10,1]（第一个
   元素相同，继续在共同前缀之后逐位比较）。

两份样例均以 s 为起点、t 为目标：

- 第一份：s 恰有十个选项，选项 2 指向 a、选项 10 指向 b，其余选项
  全部指向结尾 d；a、b 都只有选项 1 指向结尾 t。预期路线为 s 经
  选项 2 到 a、再经选项 1 到 t，编号序列 [2,1]。
- 第二份：在相同分叉前增加共同一步——s 只有选项 1 指向 m，m 的十个
  选项按第一份 s 的目标顺序组织，其余节点含义不变。预期路线为 s 经
  选项 1 到 m、m 经选项 2 到 a、a 经选项 1 到 t，编号序列
  [1,2,1]。

每份样例另做一次仅改变 nodes 排列顺序（各节点 options 顺序原样
保留）的对照，完整查询结果必须完全一致。填充选项只指向结尾 d，
不形成其他到 t 的路线。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v

预期结果直接依据上述固定路线手写为常量，不由产品查询结果生成。
所有样例在独立临时目录中以小型 UTF-8 JSON 写入并在结束后清理；
每次查询前后输入文件字节一致；程序源码、sample.json 与现有公开
文档均不改动。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIALOGUE = PROJECT_DIR / "dialogue.py"


def fork_options(fork_id):
    """分叉节点的固定十个选项：2 指向 a、10 指向 b、其余指向结尾 d。

    选项顺序固定为编号 1..10；对照样例只重排节点，不改动这里的顺序。
    """
    targets = {2: "a", 10: "b"}
    return [
        {"text": "{} 的选项 {}（去 {}）".format(
            fork_id, i, targets.get(i, "d")),
         "target": targets.get(i, "d")}
        for i in range(1, 11)
    ]


def sample_one_data():
    """第一份固定样例：s 直接分叉，[2,1] 优先于 [10,1]。"""
    return {
        "start": "s",
        "nodes": [
            {"id": "s", "text": "起点（十个选项）", "options": fork_options("s")},
            {"id": "a", "text": "甲节点", "options": [
                {"text": "a 的选项 1（去 t）", "target": "t"},
            ]},
            {"id": "b", "text": "乙节点", "options": [
                {"text": "b 的选项 1（去 t）", "target": "t"},
            ]},
            {"id": "d", "text": "填充选项汇入的结尾", "options": []},
            {"id": "t", "text": "目标终点", "options": []},
        ],
    }


def sample_two_data():
    """第二份固定样例：共同前缀一步后再分叉，[1,2,1] 优先于 [1,10,1]。"""
    return {
        "start": "s",
        "nodes": [
            {"id": "s", "text": "起点（唯一选项去 m）", "options": [
                {"text": "s 的选项 1（去 m）", "target": "m"},
            ]},
            {"id": "m", "text": "中途分叉（十个选项）",
             "options": fork_options("m")},
            {"id": "a", "text": "甲节点", "options": [
                {"text": "a 的选项 1（去 t）", "target": "t"},
            ]},
            {"id": "b", "text": "乙节点", "options": [
                {"text": "b 的选项 1（去 t）", "target": "t"},
            ]},
            {"id": "d", "text": "填充选项汇入的结尾", "options": []},
            {"id": "t", "text": "目标终点", "options": []},
        ],
    }


def reordered(data):
    """仅整体反转 nodes 排列顺序；各节点对象及其 options 顺序原样保留。"""
    shuffled = dict(data)
    shuffled["nodes"] = list(reversed(data["nodes"]))
    return shuffled


# 以下预期直接依据题目固定路线手写，不通过查询产品结果取得。
EXPECTED_ONE = {
    "start": "s",
    "target": "t",
    "path": [
        {"source": "s", "choice": 2, "target": "a"},
        {"source": "a", "choice": 1, "target": "t"},
    ],
}

EXPECTED_TWO = {
    "start": "s",
    "target": "t",
    "path": [
        {"source": "s", "choice": 1, "target": "m"},
        {"source": "m", "choice": 2, "target": "a"},
        {"source": "a", "choice": 1, "target": "t"},
    ],
}

EXPECTED_SEQUENCE_ONE = [2, 1]
EXPECTED_SEQUENCE_TWO = [1, 2, 1]


def run_route(path, node):
    """以 README 公开的 route 入口执行查询，返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, str(DIALOGUE), "route", str(path), "--node", node],
        capture_output=True,
    )


class TestRouteTwoDigitChoices(unittest.TestCase):
    """两位数选项编号：2 与 10 的比较及共同前缀之后的比较。"""

    def write_isolated_sample(self, data, dir_name):
        """在独立临时目录中写入小型 UTF-8 JSON 样例，结束后自动清理。"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / dir_name / "dialogue.json"
        path.parent.mkdir()
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def assert_route_matches_fixed_expectation(
        self, path, expected, expected_sequence
    ):
        """核对退出码、标准错误、单行 JSON 输出及逐步 source/choice/target。"""
        before = path.read_bytes()
        result = run_route(path, "t")
        # 每次查询前后输入文件字节一致（只读查询）。
        self.assertEqual(
            path.read_bytes(), before, "输入文件在查询后字节发生变化"
        )

        self.assertEqual(
            result.returncode, 0,
            "成功时退出码应为 0，stderr: {!r}".format(result.stderr),
        )
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")

        stdout = result.stdout.decode("utf-8")
        self.assertTrue(
            stdout.endswith("\n"), "标准输出应以一个结尾换行结束：{!r}".format(stdout)
        )
        self.assertNotIn(
            "\n", stdout[:-1], "结尾换行之前不应再有换行：{!r}".format(stdout)
        )

        # 按解析后的 JSON 对象核对，不依赖键排列或空格。
        actual = json.loads(stdout[:-1])
        self.assertEqual(
            set(actual.keys()), {"start", "target", "path"},
            "结果对象应只含 start、target、path 三个字段",
        )
        self.assertEqual(actual, expected, "完整查询结果应与固定预期一致")

        # 在整对象相等之外，再显式核对 start、target 与每一步的
        # source、choice、target，而不仅比较编号序列。
        self.assertEqual(actual["start"], expected["start"])
        self.assertEqual(actual["target"], expected["target"])
        self.assertEqual(len(actual["path"]), len(expected_sequence))
        for actual_step, expected_step in zip(actual["path"], expected["path"]):
            self.assertEqual(
                set(actual_step.keys()), {"source", "choice", "target"},
                "每个步骤应只含 source、choice、target 三个字段",
            )
            self.assertEqual(actual_step["source"], expected_step["source"])
            self.assertEqual(actual_step["choice"], expected_step["choice"])
            self.assertEqual(actual_step["target"], expected_step["target"])
        # 编号序列本身再单独核对一次（2 与 10 的数值比较是本用例重点）。
        self.assertEqual(
            [step["choice"] for step in actual["path"]], expected_sequence
        )

    def test_two_beats_ten_and_node_order_variants(self):
        """第一份：[2,1] 优先于 [10,1]；nodes 重排对照结果完全相同。"""
        cases = [
            ("sample_one", sample_one_data(), EXPECTED_ONE,
             EXPECTED_SEQUENCE_ONE),
            ("sample_one_reordered", reordered(sample_one_data()),
             EXPECTED_ONE, EXPECTED_SEQUENCE_ONE),
        ]
        for dir_name, data, expected, sequence in cases:
            with self.subTest(case=dir_name):
                path = self.write_isolated_sample(data, dir_name)
                self.assert_route_matches_fixed_expectation(
                    path, expected, sequence
                )

    def test_comparison_after_common_prefix_and_node_order_variants(self):
        """第二份：共同前缀后 [1,2,1] 优先于 [1,10,1]；重排对照结果相同。"""
        cases = [
            ("sample_two", sample_two_data(), EXPECTED_TWO,
             EXPECTED_SEQUENCE_TWO),
            ("sample_two_reordered", reordered(sample_two_data()),
             EXPECTED_TWO, EXPECTED_SEQUENCE_TWO),
        ]
        for dir_name, data, expected, sequence in cases:
            with self.subTest(case=dir_name):
                path = self.write_isolated_sample(data, dir_name)
                self.assert_route_matches_fixed_expectation(
                    path, expected, sequence
                )

    def test_reordered_only_moves_nodes_not_options(self):
        """对照样例只改变 nodes 排列：各节点 options 顺序必须原样保留。"""
        for name, builder in [("one", sample_one_data),
                              ("two", sample_two_data)]:
            with self.subTest(case=name):
                original = builder()
                shuffled = reordered(original)
                self.assertEqual(
                    [node["id"] for node in shuffled["nodes"]],
                    list(reversed([node["id"] for node in original["nodes"]])),
                )
                options_by_id_original = {
                    node["id"]: [opt["target"] for opt in node["options"]]
                    for node in original["nodes"]
                }
                options_by_id_shuffled = {
                    node["id"]: [opt["target"] for opt in node["options"]]
                    for node in shuffled["nodes"]
                }
                self.assertEqual(
                    options_by_id_shuffled, options_by_id_original,
                    "重排 nodes 不得改变任何节点的 options 顺序",
                )


if __name__ == "__main__":
    unittest.main()
