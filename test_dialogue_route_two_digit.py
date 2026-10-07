# -*- coding: utf-8 -*-
"""dialogue.py route 对两位数选项编号数值字典序比较的命令行回归测试。

既有 route 回归样例的选项编号均为一位数，无法区分“完整选项编号序列的
数值字典序”（2 < 10）与字符串字典序（"10" < "2"）。本模块用两份固定
样例补足该既有行为，样例在独立临时目录中以小型 UTF-8 JSON 写入并在
结束后清理，通过 README 公开的 route 命令行入口查询：

1. 十分叉样例：s 恰有十个选项，第 2 个指向 a、第 10 个指向 b，其余
   八个均指向结尾 d；a、b 都只有第 1 个选项指向结尾 t。到 t 的两条
   等长路线编号序列为 [2,1] 与 [10,1]，数值字典序下 [2,1] 更小；
   字符串字典序会错误地选择 [10,1]。
2. 共同前缀样例：s 只有第 1 个选项指向 m，m 的十个选项按前一样例中
   s 的目标顺序组织（2->a、10->b、其余->d），a、b 含义不变。等长
   序列 [1,2,1] 与 [1,10,1] 在共同前缀 1 之后比较 2 与 10。

每份样例另做一次仅改变 nodes 排列顺序（各节点 options 顺序原样保留）
的对照，两次完整查询结果（stdout 字节）必须完全相同。

预期结果直接按上述固定路线写死，不由产品查询结果生成；逐字段核对
start、target 以及 path 每一步的 source、choice、target，并核对结果
对象只含这三个字段，不依赖 JSON 键排列或空白。成功时退出码为 0、
标准错误为空、标准输出只含一行 JSON 和一个结尾换行；每次查询前后
输入文件字节一致，重复执行结果相同。

运行方式（在项目目录下，仅需 Python 3 标准库，无需网络）：

    python -m unittest discover -v
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DIALOGUE = PROJECT_DIR / "dialogue.py"
TARGET = "t"

# 十分叉节点的十个选项里，只有第 2、第 10 个有专门去向，其余统一
# 指向结尾 d，填充选项不形成任何其他到 t 的路线。
FORK_SPECIAL_TARGETS = {2: "a", 10: "b"}

# 预期直接依据固定路线写死：s -(2)-> a -(1)-> t，序列 [2,1]，
# 绝不能是 [10,1]（s -(10)-> b -(1)-> t）。
FORK_EXPECTED = {
    "start": "s",
    "target": "t",
    "path": [
        {"source": "s", "choice": 2, "target": "a"},
        {"source": "a", "choice": 1, "target": "t"},
    ],
}
FORK_EXPECTED_CHOICES = [2, 1]

# 共同前缀样例预期：s -(1)-> m -(2)-> a -(1)-> t，序列 [1,2,1]，
# 优先于 [1,10,1]（s -(1)-> m -(10)-> b -(1)-> t）。
PREFIX_EXPECTED = {
    "start": "s",
    "target": "t",
    "path": [
        {"source": "s", "choice": 1, "target": "m"},
        {"source": "m", "choice": 2, "target": "a"},
        {"source": "a", "choice": 1, "target": "t"},
    ],
}
PREFIX_EXPECTED_CHOICES = [1, 2, 1]


def fork_options(label):
    """构造按序排列的十个选项：第 2 个->a、第 10 个->b，其余->d。

    选项文字均为合法字符串；label 用于区分十分叉节点（s 或 m），
    保证文字不重复。
    """
    options = []
    for choice in range(1, 11):
        target = FORK_SPECIAL_TARGETS.get(choice, "d")
        options.append({
            "text": "{}-岔路选项{}".format(label, choice),
            "target": target,
        })
    return options


def tail_nodes():
    """a、b 都只有第 1 个选项指向结尾 t；d、t 自身为结尾。"""
    return [
        {"id": "a", "text": "第二选项通道", "options": [
            {"text": "a 唯一选项到终点", "target": "t"},
        ]},
        {"id": "b", "text": "第十选项通道", "options": [
            {"text": "b 唯一选项到终点", "target": "t"},
        ]},
        {"id": "d", "text": "填充死路结尾", "options": []},
        {"id": "t", "text": "目标结尾", "options": []},
    ]


def fork_nodes():
    """第一份样例：s 恰有十个选项，2->a、10->b、其余->d。"""
    nodes = [
        {"id": "s", "text": "十分叉起点", "options": fork_options("s")},
    ]
    nodes.extend(tail_nodes())
    return nodes


def prefix_nodes():
    """第二份样例：s 只有第 1 个选项->m；m 的十个选项复刻前一份 s 的顺序。"""
    nodes = [
        {"id": "s", "text": "共同前缀起点", "options": [
            {"text": "s 唯一选项到 m", "target": "m"},
        ]},
        {"id": "m", "text": "十分叉中途", "options": fork_options("m")},
    ]
    nodes.extend(tail_nodes())
    return nodes


def reorder_nodes_only(nodes):
    """仅整体倒排 nodes 顺序；各节点对象（含 options 顺序）原样不动。"""
    return list(reversed(nodes))


def data_with(nodes):
    return {"start": "s", "nodes": nodes}


class TwoDigitRouteTestCase(unittest.TestCase):
    """临时目录、命令行调用与输出/字节核对的公共支撑。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_dir = Path(self._tmp.name)

    def write_case(self, data, name):
        """把固定数据写成独立的临时 UTF-8 JSON 样例文件，返回路径。"""
        path = self.tmp_dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def run_route(self, path):
        """通过 README 公开的 route 入口查询固定目标 t，不捕获异常。"""
        return subprocess.run(
            [sys.executable, str(DIALOGUE), "route", str(path),
             "--node", TARGET],
            capture_output=True,
        )

    def query_success(self, path):
        """一次成功查询的全部断言，返回 (CompletedProcess, 解析后的对象)。

        - 退出码 0、标准错误为空、无调用栈；
        - 标准输出只含一行 JSON 和一个结尾换行；
        - 查询前后输入文件字节一致；
        - 结果对象只含 start、target、path 三个字段。
        """
        before = path.read_bytes()
        result = self.run_route(path)
        self.assertEqual(
            path.read_bytes(), before,
            "输入文件在查询后字节发生变化：{}".format(path),
        )
        self.assertEqual(result.returncode, 0,
                         "成功时退出码应为 0，stderr: {!r}".format(result.stderr))
        self.assertEqual(result.stderr, b"", "成功时标准错误应为空")
        self.assertNotIn(b"Traceback", result.stderr, "标准错误不应含调用栈")

        stdout = result.stdout.decode("utf-8")
        self.assertTrue(
            stdout.endswith("\n"),
            "标准输出应以一个结尾换行结束：{!r}".format(stdout),
        )
        self.assertNotIn(
            "\n", stdout[:-1],
            "结尾换行之前不应再有换行：{!r}".format(stdout),
        )
        actual = json.loads(stdout[:-1])
        self.assertEqual(
            set(actual.keys()), {"start", "target", "path"},
            "结果对象应只含 start、target、path 三个字段",
        )
        return result, actual

    def assert_route_matches(self, actual, expected, expected_choices):
        """按解析后对象逐字段核对，不依赖 JSON 键排列或空白。"""
        # 整体相等已覆盖全部字段；下面再显式逐字段核对一遍，避免只比编号
        # 序列而漏掉 source/target 或多/少一步。
        self.assertEqual(actual, expected, "解析后的 JSON 对象应与固定预期完全一致")
        self.assertEqual(actual["start"], expected["start"], "start 不符")
        self.assertEqual(actual["target"], expected["target"], "target 不符")
        self.assertEqual(len(actual["path"]), len(expected["path"]), "步数不符")
        for index, (actual_step, expected_step) in enumerate(zip(
                actual["path"], expected["path"])):
            self.assertEqual(
                set(actual_step.keys()), {"source", "choice", "target"},
                "第 {} 步字段应为 source/choice/target".format(index),
            )
            self.assertEqual(actual_step["source"], expected_step["source"],
                             "第 {} 步 source 不符".format(index))
            self.assertEqual(actual_step["choice"], expected_step["choice"],
                             "第 {} 步 choice 不符".format(index))
            self.assertEqual(actual_step["target"], expected_step["target"],
                             "第 {} 步 target 不符".format(index))
        choices = [step["choice"] for step in actual["path"]]
        self.assertEqual(choices, expected_choices, "选项编号序列不符")

    def assert_case(self, nodes, name, expected, expected_choices):
        """写入一份样例，连续查询两次：结果符合固定预期且两次输出字节一致。"""
        path = self.write_case(data_with(nodes), name)
        first, first_object = self.query_success(path)
        self.assert_route_matches(first_object, expected, expected_choices)
        # 重复执行得到相同结果（同时再次核对查询前后字节不变）。
        second, second_object = self.query_success(path)
        self.assertEqual(second.stdout, first.stdout, "重复查询的标准输出应完全一致")
        self.assertEqual(second_object, first_object, "重复查询的解析结果应完全一致")
        return first.stdout

    def assert_only_node_order_changed(self, original, reordered):
        """对照前置条件：仅 nodes 排列改变，节点集合与各节点 options 顺序不变。"""
        self.assertNotEqual(
            [node["id"] for node in original],
            [node["id"] for node in reordered],
            "对照样例应确实改变 nodes 排列顺序",
        )
        original_by_id = {node["id"]: node for node in original}
        reordered_by_id = {node["id"]: node for node in reordered}
        self.assertEqual(set(original_by_id), set(reordered_by_id),
                         "对照样例不得增减节点")
        for node_id, node in original_by_id.items():
            # 同一节点对象在两种排列中一致：options 顺序与内容原样保留。
            self.assertIs(reordered_by_id[node_id], node,
                          "节点 {} 应原样保留，仅改变其在 nodes 中的位置".format(node_id))
            self.assertEqual(
                [option["target"] for option in node["options"]],
                [option["target"] for option in
                 reordered_by_id[node_id]["options"]],
                "节点 {} 的 options 顺序不得改变".format(node_id),
            )


class TestTwoDigitChoiceOrdering(TwoDigitRouteTestCase):
    """两位数编号 2 与 10 的数值字典序比较，及共同前缀之后的比较。"""

    def test_choice_2_beats_choice_10_at_fork(self):
        """十分叉：等长序列 [2,1] 优先于 [10,1]，不按字符串字典序比较。"""
        self.assert_case(
            fork_nodes(), "fork.json", FORK_EXPECTED, FORK_EXPECTED_CHOICES
        )

    def test_choice_2_beats_choice_10_at_fork_regardless_of_node_order(self):
        """十分叉对照：仅倒排 nodes 顺序，完整查询结果与原排列逐字节相同。"""
        nodes = fork_nodes()
        reordered = reorder_nodes_only(nodes)
        self.assert_only_node_order_changed(nodes, reordered)
        canonical_stdout = self.assert_case(
            nodes, "fork_canonical.json", FORK_EXPECTED, FORK_EXPECTED_CHOICES
        )
        reordered_stdout = self.assert_case(
            reordered, "fork_reordered.json",
            FORK_EXPECTED, FORK_EXPECTED_CHOICES,
        )
        self.assertEqual(reordered_stdout, canonical_stdout,
                         "仅改变 nodes 排列时完整查询结果应完全相同")

    def test_choice_2_beats_choice_10_after_common_prefix(self):
        """共同前缀一步：[1,2,1] 优先于 [1,10,1]，在共同前缀后比 2 与 10。"""
        self.assert_case(
            prefix_nodes(), "prefix.json", PREFIX_EXPECTED, PREFIX_EXPECTED_CHOICES
        )

    def test_choice_2_beats_choice_10_after_common_prefix_regardless_of_node_order(self):
        """共同前缀对照：仅倒排 nodes 顺序，完整查询结果与原排列逐字节相同。"""
        nodes = prefix_nodes()
        reordered = reorder_nodes_only(nodes)
        self.assert_only_node_order_changed(nodes, reordered)
        canonical_stdout = self.assert_case(
            nodes, "prefix_canonical.json",
            PREFIX_EXPECTED, PREFIX_EXPECTED_CHOICES,
        )
        reordered_stdout = self.assert_case(
            reordered, "prefix_reordered.json",
            PREFIX_EXPECTED, PREFIX_EXPECTED_CHOICES,
        )
        self.assertEqual(reordered_stdout, canonical_stdout,
                         "仅改变 nodes 排列时完整查询结果应完全相同")


if __name__ == "__main__":
    unittest.main()
