"""
Hermes Cognitive OS V4 — Cron Pipeline

每日 03:00 执行：
1. Prediction Pipeline（多 subject）
2. Auto-Learning（到期 prediction 自动验证，优先真实数据源，fallback 模拟数据）

数据源优先级：akshare → yfinance → simulated
"""
import sys
from pathlib import Path
from typing import List, Dict, Any

# Path setup — 用绝对路径，不依赖 cwd
# 真实脚本位置: ~/hermes/cognition-v4/cron_cognitive_v4.py
# 但 cron 跑时可能从 ~/AppData/Local/hermes/scripts/cron_cognitive_v4.py 复制副本启动
# 两种情况下 V4_DIR 都应该是 ~/hermes/cognition-v4/
V4_DIR = Path.home() / "hermes" / "cognition-v4"
sys.path.insert(0, str(V4_DIR))
# 切到 V4_DIR 让所有相对路径正常工作
os_chdir = None
try:
    os_chdir = Path(__file__).parent.resolve()
    # 验证是否为 V4_DIR 或其 scripts/ 子目录
    if os_chdir != V4_DIR and os_chdir != V4_DIR / "scripts":
        import os as _os
        _os.chdir(str(V4_DIR))
except Exception:
    pass

from workflow import PredictionPipeline, EnhancedLearningPipeline
from memory import PredictionStore, OutcomeStore, BeliefStore
from core import Outcome, ErrorType
from data_fetcher import DataFetcher
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("cognition-v4-cron")

WIKI_DIR = Path.home() / "wiki"
V4_DB = V4_DIR / "cognition_v4.db"
DB_PATH = str(V4_DB)

# ============================================================
# 需要定期预测的 subject（可扩展）
# ============================================================
# 财务指标（毛利率/净息差等）→ 财报发布后用 simulated 兜底
# 股价指标 → 腾讯财经实时接口
SUBJECTS: List[Dict[str, Any]] = [
    {"subject": "赛力斯毛利率", "horizon_days": 90},
    {"subject": "赛力斯股价", "horizon_days": 5},    # 短期股价验证
    {"subject": "腾讯毛利率", "horizon_days": 90},
    {"subject": "腾讯股价", "horizon_days": 5},
    {"subject": "招行净息差", "horizon_days": 90},
    {"subject": "招行股价", "horizon_days": 5},
    {"subject": "英伟达营收增长", "horizon_days": 90},
    {"subject": "英伟达股价", "horizon_days": 5},
    {"subject": "工行不良贷款率", "horizon_days": 90},
    {"subject": "工行股价", "horizon_days": 5},
    {"subject": "ZTO单票成本", "horizon_days": 90},
    {"subject": "ZTO股价", "horizon_days": 5},
]

# ============================================================
# 数据源配置
# ============================================================
DATA_FETCHER = DataFetcher()
# 数据源优先级：akshare → yfinance → simulated
DATA_SOURCE_ORDER = ["akshare", "yfinance", "simulated"]


def run_prediction_pipeline(subject: str, horizon_days: int) -> Dict[str, Any]:
    """运行单个 subject 的预测管道。

    集成：
    - PredictabilityEngine：预测前评估，过低分跳过
    - ScenarioEngine：替代默认 3 场景，生成 4 场景（+黑天鹅）
    - PredictionBindingStore：自动绑定 evidence → prediction
    """
    from engines.predictability_engine import PredictabilityEngine
    from engines.scenario_engine import ScenarioEngine
    from memory import (
        EntityAccuracyStore, PredictionBindingStore, EvidenceStore,
    )
    from datetime import datetime as _dt

    pipeline = PredictionPipeline(DB_PATH)
    result = pipeline.run(
        wiki_dir=str(WIKI_DIR),
        subject=subject,
        horizon_days=horizon_days,
    )

    obs_count = len(result.get("observations", []))
    ev_count = len(result.get("evidence_list", []))
    pred = result.get("prediction")
    belief = result.get("belief")

    # === Step A: 可预测性评估 ===
    pe = PredictabilityEngine()
    entity_acc = {}
    if belief:
        # 查历史精度（如果存在）
        ea_store = EntityAccuracyStore.get(DB_PATH)
        entity, _, horizon_lbl, *_ = subject.partition("价")  # 简化提取
        # 简单按 subject 全名查
        rec = ea_store.get_record(subject, "value", "any", "numeric")
        if rec:
            entity_acc = rec

    pe_ctx = pe.run({
        "target": subject,
        "evidence": result.get("evidence_list", []),
        "horizon_days": horizon_days,
        "entity_accuracy": entity_acc,
    })
    predictability = pe_ctx["predictability_score"]

    # 跳过：可预测性太低（< 0.3）
    if predictability < 0.3:
        logger.info(
            f"  ⏭ {subject}: 可预测性={predictability:.3f} 跳过 | {pe_ctx['recommendation']}"
        )
        return {
            "subject": subject,
            "observations": obs_count,
            "evidence": ev_count,
            "prediction_id": None,
            "effective_score": None,
            "status": "skipped_low_predictability",
            "predictability": predictability,
        }

    # === Step B: 场景生成（增强版） ===
    if belief and pred:
        se = ScenarioEngine()
        sc_ctx = se.run({
            "belief": belief,
            "evidence": result.get("evidence_list", []),
            "target_value": pred.expected_value or 1.0,
            "n_scenarios": 4,
        })
        new_scenarios = sc_ctx["scenarios"]
        # 重新赋值场景到 prediction
        from dataclasses import replace
        pred = replace(pred, scenarios=new_scenarios)
        pred_store = PredictionStore.get(DB_PATH)
        # 更新 DB（如果之前 insert 过）
        try:
            pred_store.update(pred)
        except Exception:
            pass
        logger.info(
            f"  🎬 场景重生成: E[V]={sc_ctx['expected_value']:.3f} "
            f"downside={sc_ctx['downside_risk']:.3f}"
        )

    # === Step C: 自动绑定 evidence → prediction ===
    bound_count = 0
    if pred and result.get("evidence_list"):
        pb_store = PredictionBindingStore.get(DB_PATH)
        for ev in result["evidence_list"]:
            pb_store.auto_bind(
                evidence_id=ev.id,
                prediction_id=pred.id,
                evidence_type=ev.type.value,
                horizon_label=pred.horizon_label.value,
            )
            bound_count += 1

    # === Step D: 因果图谱构建 ===
    causal_added = 0
    if result.get("evidence_list") and belief:
        from engines.causal_engine import CausalEngine as _Causal
        ce = _Causal("causal_engine", {"db_path": DB_PATH})
        ce.run({
            "evidence": result["evidence_list"],
            "subject": subject,
        })
        causal_added = len(ce.query_causes(subject, depth=1))

    report = {
        "subject": subject,
        "observations": obs_count,
        "evidence": ev_count,
        "prediction_id": pred.id[:8] if pred else None,
        "effective_score": pred.effective_score if pred else None,
        "predictability": predictability,
        "scenarios": len(pred.scenarios) if pred else 0,
        "bindings": bound_count,
        "causal": causal_added,
        "status": "created" if pred else "no_change",
    }

    if pred:
        logger.info(
            f"Pipeline {subject}: {obs_count} obs, {ev_count} ev → "
            f"pred={pred.id[:8]} eff={pred.effective_score:.3f} "
            f"pred_score={predictability:.2f} bound={bound_count}"
        )
    else:
        logger.info(f"Pipeline {subject}: {obs_count} obs, {ev_count} ev → 无新预测")

    return report


def run_auto_learning() -> List[Dict[str, Any]]:
    """自动处理到期 prediction：注入 Outcome → Learning。

    使用 OutcomeEngine 替换手写 Outcome 构造逻辑。
    """
    from engines.outcome_engine import OutcomeEngine
    from core import Outcome, ErrorType
    from memory import PredictionStore, OutcomeStore, BeliefStore, EntityAccuracyStore

    pred_store = PredictionStore.get(DB_PATH)
    outcome_store = OutcomeStore.get(DB_PATH)
    belief_store = BeliefStore.get(DB_PATH)
    entity_acc_store = EntityAccuracyStore.get(DB_PATH)

    due = pred_store.list_due()
    logger.info(f"到期 Prediction: {len(due)} 个")

    if not due:
        return []

    # 用 OutcomeEngine 批量生成 Outcome（自动走真实数据源）
    oe = OutcomeEngine()
    oe_ctx = oe.run({"predictions": due, "dry_run": False})
    new_outcomes = oe_ctx["outcomes"]

    results = []
    # 索引新 outcome by prediction_id
    outcome_by_pred = {o.prediction_id: o for o in new_outcomes}

    for pred in due:
        # 优先使用新生成的 outcome
        outcome = outcome_by_pred.get(pred.id)

        if not outcome:
            # 检查是否已有 outcome
            conn = outcome_store._connect()
            existing = conn.execute(
                "SELECT id FROM outcomes WHERE prediction_id=?", (pred.id,)
            ).fetchone()
            conn.close()
            if existing:
                logger.info(f"  ⏭ {pred.target}: 已有 outcome，跳过")
                results.append({"subject": pred.target, "status": "skipped_existing"})
                continue

            # fallback：用 DataFetcher 拉数据（保留旧逻辑）
            fetcher = DataFetcher()
            vdata = fetcher.fetch(pred.target, source=DATA_SOURCE_ORDER)
            if not vdata:
                logger.info(f"  ⏭ {pred.target}: 无验证数据，跳过")
                results.append({"subject": pred.target, "status": "skipped_no_data"})
                continue

            actual = vdata["actual"]
            expected = vdata.get("expected", pred.expected_value or 0.5)
            error = abs(actual - expected)
            source_label = vdata.get("_source_used", "simulated")
            et_str = vdata.get("error_type", "no_error")

            outcome = Outcome(
                id=Outcome.generate_id(pred.id, str(actual)),
                prediction_id=pred.id,
                actual_value=actual,
                actual_result=vdata["result"],
                prediction_error=round(error, 4),
                error_type=ErrorType(et_str) if et_str in ErrorType._value2member_map_ else ErrorType.NO_ERROR,
                reason=f"实际值={actual}, 预期值={expected} (source={source_label})",
            )

        # 持久化 outcome（如果来自 OutcomeEngine 但未存）
        # 用 outcome.id 集合去重，避免 OE 内部重复 insert
        if not outcome.id.startswith("skipped") and not getattr(outcome, "_persisted", False):
            try:
                outcome_store.insert(outcome)
                outcome._persisted = True
            except Exception as e:
                # UNIQUE 约束冲突 = 已存在，跳过
                logger.debug(f"outcome 持久化跳过: {e}")

        logger.info(
            f"  📊 {pred.target}: err={outcome.prediction_error:.4f} "
            f"type={outcome.error_type.value}"
        )

        # 更新 entity_accuracy
        was_correct = outcome.error_type == ErrorType.NO_ERROR
        # 简化：subject 视为 entity，metric=预测的target类型
        entity_acc_store.upsert(
            entity_name=pred.target,
            metric="value",
            horizon_label=pred.horizon_label.value,
            prediction_type="numeric",
            was_correct=was_correct,
        )

        # 获取 Belief → Learning
        learning = None
        adj = 0.0
        if pred.belief_id:
            belief = belief_store.get_by_id(pred.belief_id)
            if belief:
                pipeline = EnhancedLearningPipeline(DB_PATH)
                lr = pipeline.run(outcome=outcome, prediction=pred, belief=belief)
                learning = lr.get("learning")
                adj = lr.get("belief_adjustment", 0.0)
                logger.info(f"  Learning: {learning.id[:8] if learning else 'N/A'} adj={adj:+.4f}")
            else:
                pred_store.mark_realized(pred.id)
        else:
            pred_store.mark_realized(pred.id)

        results.append({
            "subject": pred.target,
            "outcome": outcome.id[:8],
            "learning": learning.id[:8] if learning else None,
            "adjustment": round(adj, 4),
            "error_type": outcome.error_type.value,
            "status": "learned",
        })

    return results


def _classify_error(error: float, expected: float) -> ErrorType:
    relative = error / expected if expected > 0 else error
    if relative < 0.03:
        return ErrorType.NO_ERROR
    elif relative > 0.25:
        return ErrorType.OVERCONFIDENCE
    elif error > 1.0:
        return ErrorType.MISSING_SIGNAL
    else:
        return ErrorType.NO_ERROR


def run_confidence_decay() -> List[Dict[str, Any]]:
    """对所有 active beliefs 执行置信度衰减。"""
    from engines.confidence_engine import ConfidenceEngine
    import uuid

    belief_store = BeliefStore.get(DB_PATH)
    conn = belief_store._connect()
    # 找出所有活跃 belief（上次更新时间超过7天的）
    rows = conn.execute(
        """SELECT * FROM beliefs
           WHERE status='active'
           AND datetime(update_time) < datetime('now', '-7 days')
           LIMIT 50"""
    ).fetchall()
    conn.close()

    if not rows:
        logger.info("  无需衰减的 Belief（全部在7天内）")
        return []

    engine = ConfidenceEngine()
    results = []
    for row in rows:
        belief = belief_store._row_to_entity(row)
        old_conf = belief.confidence

        # 计算衰减：基于时间
        import time
        try:
            last_update = datetime.fromisoformat(belief.update_time)
            days_elapsed = (datetime.now() - last_update).days
            decay = min(belief.decay_rate * days_elapsed, 0.3)  # 最多衰减30%
            new_conf = max(old_conf - decay, 0.1)
        except Exception:
            new_conf = old_conf

        if abs(new_conf - old_conf) < 0.001:
            continue

        # 更新 belief（archive 旧版本）
        belief_store.archive_previous(belief.id)
        new_belief = belief.__class__(
            id=str(uuid.uuid4())[:16],
            subject=belief.subject,
            probability=belief.probability,
            confidence=round(new_conf, 4),
            support_evidence_ids=belief.support_evidence_ids,
            contradict_evidence_ids=belief.contradict_evidence_ids,
            update_time=datetime.now().isoformat(),
            decay_rate=belief.decay_rate,
            version=belief.version + 1,
            previous_version_id=belief.id,
            domain=belief.domain,
            horizon=belief.horizon,
        )
        belief_store.insert(new_belief)
        results.append({
            "subject": belief.subject,
            "old_conf": round(old_conf, 4),
            "new_conf": round(new_conf, 4),
            "delta": round(new_conf - old_conf, 4),
        })
        logger.info(f"  📉 {belief.subject}: {old_conf:.3f}→{new_conf:.3f} (days={days_elapsed})")

    return results


def main():
    logger.info("=" * 50)
    logger.info("Hermes V4 Cron 开始")
    logger.info("=" * 50)

    # Step 1: 多 subject 预测
    pipeline_results = []
    for item in SUBJECTS:
        result = run_prediction_pipeline(item["subject"], item["horizon_days"])
        pipeline_results.append(result)

    # Step 2: 自动学习（到期验证 + 注入）
    learning_results = run_auto_learning()

    # Step 2.5: 置信度衰减（7天以上的 belief）
    decay_results = run_confidence_decay()

    # Step 3: 汇总报告
    logger.info("=" * 50)
    logger.info("Cron 完成汇总")
    n_pred = sum(1 for r in pipeline_results if r['prediction_id'])
    n_skip = sum(1 for r in pipeline_results if r.get('status') == 'skipped_low_predictability')
    n_outcome = sum(1 for r in learning_results if r.get('status') == 'learned')
    n_learn = sum(1 for r in learning_results if r.get('learning'))
    n_bind = sum(r.get('bindings', 0) for r in pipeline_results)
    n_scenario = sum(r.get('scenarios', 0) for r in pipeline_results if r.get('scenarios', 0) > 0)
    n_causal = sum(r.get('causal', 0) for r in pipeline_results)
    avg_pred = (
        sum(r.get('predictability', 0) for r in pipeline_results) / len(pipeline_results)
        if pipeline_results else 0
    )
    logger.info(f"  Predictions: {n_pred} 个新（{n_skip} 个因可预测性低跳过）")
    logger.info(f"  Outcomes: {n_outcome} 个新")
    logger.info(f"  Learnings: {n_learn} 个新")
    logger.info(f"  Scenarios: {n_scenario} 场景重生成")
    logger.info(f"  Bindings: {n_bind} 条 evidence→prediction 绑定")
    logger.info(f"  Causal: {n_causal} 条因果节点")
    logger.info(f"  Avg Predictability: {avg_pred:.3f}")
    logger.info(f"  Beliefs 衰减: {len(decay_results)} 个")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()