"""Scenario Engine — 多场景模拟（Phase 2 独立引擎）

职责：
- 从 Belief 和 Evidence 生成多场景（基准/乐观/悲观/黑天鹅）
- 每个场景含：概率、假设、目标值、预期收益
- 场景之间概率分布合理（sum=1.0）
- 输入可被 DecisionEngine / PredictionEngine 复用

输出：
- scenarios: List[Scenario] - 完整场景集
- expected_value: float - Σ(prob × target_value)
- downside_risk: float - 悲观场景下最大回撤
- upside_potential: float - 乐观场景下最大收益
"""
from typing import List, Dict, Any
from core import Scenario
from .base_engine import BaseEngine


class ScenarioEngine(BaseEngine):
    """多场景模拟引擎。"""

    def __init__(self, name: str = "scenario_engine", config: Dict[str, Any] = None):
        super().__init__(name, config)
        # 默认场景参数
        self.optimistic_uplift = 0.15    # 乐观场景基准值上浮 15%
        self.pessimistic_drawdown = 0.15 # 悲观场景基准值下跌 15%
        self.base_prob = 0.60            # 基准场景概率
        self.optimistic_prob = 0.25      # 乐观场景概率
        self.pessimistic_prob = 0.10     # 悲观场景概率
        self.black_swan_prob = 0.05      # 黑天鹅概率

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - belief: Belief（必需）
          - evidence: List[Evidence]（可选，用于场景假设）
          - target_value: float（基准目标值，可选，默认 1.0）
          - scenarios: List[Scenario]（可选：覆盖默认 3 场景）
          - n_scenarios: int（场景数，默认 4：基准/乐观/悲观/黑天鹅）

        输出 context 新增：
          - scenarios: List[Scenario]
          - expected_value: float
          - downside_risk: float
          - upside_potential: float
        """
        self.info("Scenario Engine 开始运行")
        belief = context.get("belief")
        if not belief:
            self.warning("无 Belief 输入，跳过")
            context["scenarios"] = []
            context["expected_value"] = None
            return context

        evidence = context.get("evidence", [])
        base_value = context.get("target_value", 1.0)
        n_scenarios = context.get("n_scenarios", 4)

        # 检测证据强度（支持 vs 矛盾），用于动态调整场景概率
        support_count = sum(1 for e in evidence if e.type.value in ("quantitative", "qualitative"))
        contradict_count = sum(1 for e in evidence if e.type.value == "categorical")

        # 根据 belief.probability 调整场景权重
        belief_prob = max(min(belief.probability, 0.95), 0.05)
        # belief 越确定 → 基准场景权重越大；越不确定 → 悲观/黑天鹅权重越大
        prob_factor = belief_prob  # 0~1

        # 动态场景概率（保证 sum=1.0）
        base_prob = self.base_prob * prob_factor + 0.20  # 0.20~0.80
        optimistic_prob = self.optimistic_prob * prob_factor + 0.05  # 0.05~0.30
        pessimistic_prob = self.pessimistic_prob + (1 - prob_factor) * 0.20  # 0.10~0.30
        black_swan_prob = max(0.02, self.black_swan_prob - contradict_count * 0.02)
        # 矛盾证据越多，黑天鹅概率越高

        # 归一化使概率和=1.0
        total = base_prob + optimistic_prob + pessimistic_prob + black_swan_prob
        base_prob /= total
        optimistic_prob /= total
        pessimistic_prob /= total
        black_swan_prob /= total

        # 动态乐观/悲观幅度（belief 不确定时放大）
        opt_uplift = self.optimistic_uplift + (1 - prob_factor) * 0.10
        pess_drawdown = self.pessimistic_drawdown + (1 - prob_factor) * 0.10

        # 构造场景列表
        scenarios = [
            Scenario(
                name="基准",
                probability=round(base_prob, 4),
                assumptions=self._extract_assumptions(evidence, "base"),
                target_value=round(base_value, 4),
                expected_return=round(base_value, 4),
            ),
            Scenario(
                name="乐观",
                probability=round(optimistic_prob, 4),
                assumptions=self._extract_assumptions(evidence, "optimistic"),
                target_value=round(base_value * (1 + opt_uplift), 4),
                expected_return=round(base_value * (1 + opt_uplift), 4),
            ),
            Scenario(
                name="悲观",
                probability=round(pessimistic_prob, 4),
                assumptions=self._extract_assumptions(evidence, "pessimistic"),
                target_value=round(base_value * (1 - pess_drawdown), 4),
                expected_return=round(base_value * (1 - pess_drawdown), 4),
            ),
            Scenario(
                name="黑天鹅",
                probability=round(black_swan_prob, 4),
                assumptions=["极端事件", "不可预测的黑天鹅"],
                target_value=round(base_value * 0.50, 4),  # 黑天鹅=腰斩
                expected_return=round(base_value * 0.50, 4),
            ),
        ]

        # 仅取 n_scenarios 个（默认 4）
        scenarios = scenarios[:n_scenarios]

        # 计算期望值、最大收益、最大回撤
        expected_value = sum(s.probability * s.target_value for s in scenarios)
        downside_risk = base_value - scenarios[2].target_value if len(scenarios) >= 3 else 0
        upside_potential = scenarios[1].target_value - base_value if len(scenarios) >= 2 else 0

        context["scenarios"] = scenarios
        context["expected_value"] = round(expected_value, 4)
        context["downside_risk"] = round(downside_risk, 4)
        context["upside_potential"] = round(upside_potential, 4)

        self.info(
            f"Scenario Engine 完成: {len(scenarios)} scenarios, "
            f"E[V]={expected_value:.3f}, downside={downside_risk:.3f}"
        )
        return context

    def _extract_assumptions(self, evidence, scenario_type: str) -> List[str]:
        """从 evidence 提取场景假设。"""
        base_assumptions = {
            "base": ["无超预期因素", "趋势延续"],
            "optimistic": ["催化剂兑现", "超预期表现"],
            "pessimistic": ["低于预期", "风险暴露"],
        }
        assumptions = base_assumptions.get(scenario_type, ["未知"]).copy()

        # 根据 evidence 添加具体假设
        if scenario_type == "optimistic":
            for e in evidence[:2]:
                if e.type.value == "qualitative":
                    assumptions.append(f"{e.content}推动超预期")
        elif scenario_type == "pessimistic":
            for e in evidence[:2]:
                if e.type.value == "categorical":
                    assumptions.append(f"{e.content}导致下行")
        return assumptions