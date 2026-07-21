"""World Model Engine — 三层世界模拟"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

from .base_engine import BaseEngine


class WorldLayer(str, Enum):
    MACRO = "macro"       # 宏观层
    INDUSTRY = "industry" # 产业层
    COMPANY = "company"    # 公司层


class WorldModelEngine(BaseEngine):
    """
    World Model Engine：三层世界模拟。

    不是"新闻 → 预测"，而是"世界模拟 → 预测"。

    三层：
    Layer 1 宏观世界：GDP / 利率 / 汇率 / 通胀 / 政策
    Layer 2 产业动态：竞争格局 / 技术路线 / 政策
    Layer 3 企业价值：市场份额 / 产品 / 成本 / 现金流

    传导路径：
    宏观 → 产业 → 公司 → 估值 → 预期收益 → 股价

    最终输出：
    world_view: 宏观判断
    industry_view: 产业判断
    company_view: 公司判断
    valuation: 估值结论
    signal: 决策信号
    """

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        输入 context：
          - entity_name: str（如"赛力斯"）
          - beliefs: List[Belief]（各层信念）
          - evidence: List[Evidence]（最新证据）
          - causal_graph: CausalGraph

        输出 context 新增：
          - world_view: dict
          - industry_view: dict
          - company_view: dict
          - valuation: dict
          - signal: dict
        """
        self.info("World Model Engine 开始运行")

        entity_name = context.get("entity_name", "unknown")
        beliefs = context.get("beliefs", [])
        evidence = context.get("evidence", [])
        causal_graph = context.get("causal_graph")

        # Step 1: 宏观层判断
        world_view = self._macro_layer(entity_name, beliefs, evidence)
        context["world_view"] = world_view

        # Step 2: 产业层判断
        industry_view = self._industry_layer(entity_name, beliefs, evidence, world_view)
        context["industry_view"] = industry_view

        # Step 3: 公司层判断
        company_view = self._company_layer(entity_name, beliefs, evidence, industry_view)
        context["company_view"] = company_view

        # Step 4: 估值
        valuation = self._valuation(company_view, industry_view, world_view)
        context["valuation"] = valuation

        # Step 5: 决策信号
        signal = self._generate_signal(valuation, world_view)
        context["signal"] = signal

        self.info(
            f"World Model 完成: {entity_name} | "
            f"signal={signal['label']} | "
            f"target_return={valuation.get('expected_return_pct', 'N/A')}"
        )
        return context

    def _macro_layer(self, entity_name: str, beliefs, evidence) -> Dict[str, Any]:
        """宏观层判断。"""
        # 提取宏观相关信念
        macro_beliefs = [b for b in beliefs if b.domain in ("macro", "investment")]
        macro_evidence = [e for e in evidence if e.domain in ("macro",)]

        avg_confidence = (
            sum(b.confidence for b in macro_beliefs) / len(macro_beliefs)
            if macro_beliefs else 0.5
        )

        # 简化：基于信念置信度判断宏观状态
        if avg_confidence > 0.7:
            regime = "AI牛市"
            outlook = "扩张"
        elif avg_confidence > 0.5:
            regime = "价值市"
            outlook = "中性"
        else:
            regime = "熊市/高波动"
            outlook = "收缩"

        return {
            "layer": WorldLayer.MACRO,
            "regime": regime,
            "outlook": outlook,
            "confidence": round(avg_confidence, 3),
            "key_drivers": self._extract_drivers(macro_evidence, top_n=3),
            "description": f"宏观判断：{regime}，{outlook}",
        }

    def _industry_layer(
        self, entity_name: str, beliefs, evidence, world_view: Dict
    ) -> Dict[str, Any]:
        """产业层判断。"""
        industry_beliefs = [b for b in beliefs if b.domain == "investment"]
        industry_evidence = [e for e in evidence if e.domain == "investment"]

        # 提取关键词
        keywords = []
        for e in industry_evidence:
            for kw in ["新能源", "智能驾驶", "价格战", "出口", "降价", "涨价", "竞争"]:
                if kw in e.content:
                    keywords.append(kw)

        # 基于宏观调节产业判断
        macro_regime = world_view.get("regime", "中性")
        if macro_regime == "AI牛市" and "新能源" in str(keywords):
            outlook = "高增长"
            confidence = 0.75
        elif macro_regime == "熊市/高波动":
            outlook = "防御性"
            confidence = 0.5
        else:
            outlook = "稳定"
            confidence = 0.6

        return {
            "layer": WorldLayer.INDUSTRY,
            "outlook": outlook,
            "confidence": confidence,
            "key_factors": list(set(keywords))[:5],
            "macro_adjustment": f"宏观{world_view.get('regime', '中性')}下产业{outlook}",
            "description": f"产业判断：{outlook}",
        }

    def _company_layer(
        self, entity_name: str, beliefs, evidence, industry_view: Dict
    ) -> Dict[str, Any]:
        """公司层判断。"""
        company_beliefs = [b for b in beliefs if entity_name in b.subject]
        company_evidence = [e for e in evidence if entity_name in e.content]

        if not company_beliefs:
            # 无公司特定信念，用行业平均
            probability = 0.5
            confidence = 0.4
            # 只有无信念时才用证据数字
            for e in company_evidence:
                if e.type.value == "quantitative":
                    import re
                    nums = re.findall(r"(\d+\.?\d*)%", e.content)
                    if not nums:
                        raw_nums = re.findall(r"(\d+\.?\d*)", e.content)
                        nums = [n for n in raw_nums if float(n) <= 100]
                    if nums:
                        probability = min(float(nums[0]) / 100, 1.0)
                        confidence = e.confidence
                        break
        else:
            raw_prob = sum(b.probability for b in company_beliefs) / len(company_beliefs)
            raw_conf = sum(b.confidence for b in company_beliefs) / len(company_beliefs)
            # 概率=信念概率×置信度折扣（避免高置信度导致P=1.0）
            probability = raw_prob * (0.5 + 0.5 * raw_conf)  # 0.75×1.0=0.75, 0.5×0.5=0.5
            confidence = raw_conf

        outlook_map = {"高增长": 0.75, "稳定": 0.6, "防御性": 0.5}
        base_prob = outlook_map.get(industry_view.get("outlook", "稳定"), 0.5)
        adjusted_prob = base_prob * probability if probability > 0 else base_prob

        return {
            "layer": WorldLayer.COMPANY,
            "entity": entity_name,
            "probability": round(adjusted_prob, 3),
            "confidence": round(confidence, 3),
            "supporting_evidence": [e.content for e in company_evidence[:3]],
            "description": f"{entity_name}判断：P={adjusted_prob:.0%}",
        }

    def _valuation(
        self, company_view: Dict, industry_view: Dict, world_view: Dict
    ) -> Dict[str, Any]:
        """
        估值层。

        prob = 公司概率 (0-1)
        base = 1.0 (当前价格基准)
        上行空间 = 概率 × (宏观倍数 - 1) + 1
        """
        prob = company_view.get("probability", 0.5)
        base = 1.0

        # 宏观倍数
        macro_mult = {"AI牛市": 1.5, "价值市": 1.15, "熊市/高波动": 0.8}
        m_mult = macro_mult.get(world_view.get("regime", "价值市"), 1.0)

        # 产业倍数
        industry_mult = {"高增长": 1.3, "稳定": 1.1, "防御性": 0.9}
        i_mult = industry_mult.get(industry_view.get("outlook", "稳定"), 1.0)

        # 期望值 = base × 上行空间
        # 上行空间 = prob × (上行乘数 - 1) + 1
        # 上行乘数 = macro × industry
        upside_mult = m_mult * i_mult
        expected_value = base * (prob * (upside_mult - 1) + 1)
        expected_return_pct = round((expected_value - base) * 100, 2)

        return {
            "expected_value": round(expected_value, 4),
            "expected_return_pct": expected_return_pct,
            "prob": prob,
            "upside_mult": round(upside_mult, 3),
            "macro_mult": m_mult,
            "industry_mult": i_mult,
            "valuation_basis": f"prob={prob:.0%} × (宏观{world_view.get('regime')} × 产业{industry_view.get('outlook')})",
            "description": f"估值：预期{'+' if expected_return_pct >= 0 else ''}{expected_return_pct}%",
        }

    def _generate_signal(self, valuation: Dict, world_view: Dict) -> Dict[str, Any]:
        """决策信号。"""
        ret_pct = valuation.get("expected_return_pct", 0)
        macro_regime = world_view.get("regime", "中性")

        # 信号阈值
        if ret_pct >= 20:
            label = "强烈买入"
            strength = 5
        elif ret_pct >= 10:
            label = "买入"
            strength = 4
        elif ret_pct >= 0:
            label = "持有"
            strength = 3
        elif ret_pct >= -10:
            label = "卖出"
            strength = 2
        else:
            label = "强烈卖出"
            strength = 1

        # 熊市降一档
        if macro_regime == "熊市/高波动" and strength >= 3:
            strength -= 1
            labels = {5: "买入", 4: "持有", 3: "卖出", 2: "卖出", 1: "强烈卖出"}
            label = labels.get(strength, "持有")

        return {
            "label": label,
            "strength": strength,
            "expected_return_pct": ret_pct,
            "regime_adjustment": macro_regime,
            "description": f"信号：{label}（预期{'+' if ret_pct >= 0 else ''}{ret_pct}%）",
        }

    def _extract_drivers(self, evidence, top_n: int = 3) -> List[str]:
        """提取关键驱动因素。"""
        drivers = [e.content[:30] for e in evidence[:top_n]]
        return drivers
