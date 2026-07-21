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

# Path setup
HERMES_DIR = Path(__file__).parent.parent.parent
V4_DIR = HERMES_DIR / "cognition-v4"
sys.path.insert(0, str(V4_DIR))

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
    """运行单个 subject 的预测管道。"""
    pipeline = PredictionPipeline(DB_PATH)
    result = pipeline.run(
        wiki_dir=str(WIKI_DIR),
        subject=subject,
        horizon_days=horizon_days,
    )

    obs_count = len(result.get("observations", []))
    ev_count = len(result.get("evidence_list", []))
    pred = result.get("prediction")

    report = {
        "subject": subject,
        "observations": obs_count,
        "evidence": ev_count,
        "prediction_id": pred.id[:8] if pred else None,
        "effective_score": pred.effective_score if pred else None,
        "status": "created" if pred else "no_change",
    }

    if pred:
        logger.info(f"Pipeline {subject}: {obs_count} obs, {ev_count} ev → pred={pred.id[:8]} eff={pred.effective_score:.3f}")
    else:
        logger.info(f"Pipeline {subject}: {obs_count} obs, {ev_count} ev → 无新预测")

    return report


def run_auto_learning() -> List[Dict[str, Any]]:
    """自动处理到期 prediction：注入 Outcome → Learning。"""
    from core import Outcome, ErrorType
    from memory import PredictionStore, OutcomeStore, BeliefStore

    pred_store = PredictionStore.get(DB_PATH)
    outcome_store = OutcomeStore.get(DB_PATH)
    belief_store = BeliefStore.get(DB_PATH)

    due = pred_store.list_due()
    logger.info(f"到期 Prediction: {len(due)} 个")

    results = []
    for pred in due:
        # 跳过已有效 outcome 的
        conn = outcome_store._connect()
        existing = conn.execute(
            "SELECT id FROM outcomes WHERE prediction_id=?", (pred.id,)
        ).fetchone()
        conn.close()
        if existing:
            logger.info(f"  ⏭ {pred.target}: 已有 outcome，跳过")
            results.append({"subject": pred.target, "status": "skipped_existing"})
            continue

        # 通过 DataFetcher 获取验证数据（自动 fallback）
        fetcher = DataFetcher()
        vdata = fetcher.fetch(pred.target, source=DATA_SOURCE_ORDER)
        if not vdata:
            logger.info(f"  ⏭ {pred.target}: 无验证数据，跳过")
            results.append({"subject": pred.target, "status": "skipped_no_data"})
            continue

        # 计算误差
        expected = vdata.get("expected", pred.expected_value or 0.5)
        actual = vdata["actual"]
        error = abs(actual - expected)
        
        # 映射 error_type
        et = vdata.get("error_type", "no_error")
        if et == "no_error":
            error_type = ErrorType.NO_ERROR
        elif et == "missing_signal":
            error_type = ErrorType.MISSING_SIGNAL
        elif et == "overconfidence":
            error_type = ErrorType.OVERCONFIDENCE
        elif et == "regime_mismatch":
            error_type = ErrorType.REGIME_MISMATCH
        else:
            error_type = ErrorType.NO_ERROR

        source_label = vdata.get("_source_used", "simulated")
        logger.info(f"  📊 {pred.target}: 数据源={source_label} exp={expected} act={actual}")

        # 创建 Outcome
        outcome = Outcome(
            id=Outcome.generate_id(pred.id, str(actual)),
            prediction_id=pred.id,
            actual_value=actual,
            actual_result=vdata["result"],
            prediction_error=round(error, 4),
            error_type=error_type,
            reason=f"实际值={actual}, 预期值={expected}, 误差={error:.4f} (source={source_label})",
        )
        outcome_store.insert(outcome)
        logger.info(f"  Outcome 创建: {outcome.id[:8]}")

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
                logger.info(f"  Learning 完成: {learning.id[:8] if learning else 'N/A'} adj={adj:+.4f}")
            else:
                pred_store.mark_realized(pred.id)
                logger.info(f"  Belief 不存在，直接标记 realized")
        else:
            pred_store.mark_realized(pred.id)

        results.append({
            "subject": pred.target,
            "outcome": outcome.id[:8],
            "learning": learning.id[:8] if learning else None,
            "adjustment": round(adj, 4),
            "source": source_label,
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

    # Step 3: 汇总报告
    logger.info("=" * 50)
    logger.info("Cron 完成汇总")
    logger.info(f"  Predictions: {sum(1 for r in pipeline_results if r['prediction_id'])} 个新")
    logger.info(f"  Outcomes: {sum(1 for r in learning_results if r.get('status') == 'learned')} 个新")
    logger.info(f"  Learnings: {sum(1 for r in learning_results if r.get('learning'))} 个新")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()