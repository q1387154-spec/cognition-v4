"""
seed_test_predictions.py — 为测试股票创建 Prediction + 立即注入 Outcome

用途：演示完整 Learning 闭环（Prediction → Outcome → Learning）
      每次跑完建议清空重来（horizon=1d，每天 cron 自动处理）

Usage:
    python scripts/seed_test_predictions.py          # 创建预测+立即学习
    python scripts/seed_test_predictions.py --dry  # 只建预测，不学习
"""
import argparse
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

V4_DIR = Path.home() / "hermes" / "cognition-v4"
sys.path.insert(0, str(V4_DIR))

from workflow import PredictionPipeline, EnhancedLearningPipeline
from core import Outcome, ErrorType, Belief
from memory import BeliefStore, PredictionStore, OutcomeStore


# 测试股票配置
TEST_STOCKS = [
    {
        "subject": "腾讯毛利率",
        "horizon_days": 1,
        "expected_value": 46.0,
        "actual_value": 44.5,
        "result": "2026Q2 毛利率 44.5%，略低于预期，受游戏业务拖累",
        "error_type": ErrorType.MISSING_SIGNAL,
    },
    {
        "subject": "招行净息差",
        "horizon_days": 1,
        "expected_value": 2.15,
        "actual_value": 2.08,
        "result": "2026H1 净息差 2.08%，银行让利实体经济拖累",
        "error_type": ErrorType.OVERCONFIDENCE,
    },
    {
        "subject": "英伟达营收增长",
        "horizon_days": 1,
        "expected_value": 85.0,
        "actual_value": 122.0,
        "result": "2026Q2 营收同比 +122%，AI 芯片需求超预期",
        "error_type": ErrorType.MISSING_SIGNAL,
    },
    {
        "subject": "工行不良贷款率",
        "horizon_days": 1,
        "expected_value": 1.42,
        "actual_value": 1.45,
        "result": "2026H1 不良率 1.45%，房地产风险传导略超预期",
        "error_type": ErrorType.REGIME_MISMATCH,
    },
    {
        "subject": "ZTO单票成本",
        "horizon_days": 1,
        "expected_value": 2.10,
        "actual_value": 2.18,
        "result": "2026Q2 单票成本 2.18 元，燃油+人力成本上涨超预期",
        "error_type": ErrorType.OVERCONFIDENCE,
    },
]


def run_prediction_only(stock: dict, db_path: str) -> dict:
    """只创建 Prediction。"""
    pipeline = PredictionPipeline(db_path)
    result = pipeline.run(
        wiki_dir=str(Path.home() / "wiki"),
        subject=stock["subject"],
        horizon_days=stock["horizon_days"],
    )
    pred = result.get("prediction")
    return {
        "subject": stock["subject"],
        "expected_value": stock["expected_value"],
        "prediction_id": pred.id[:8] if pred else None,
        "effective_score": pred.effective_score if pred else None,
    }


def run_full_loop(stock: dict, db_path: str) -> dict:
    """完整循环：Prediction → Outcome → Learning。"""
    # Step 1: 创建 Prediction
    pred_result = run_prediction_only(stock, db_path)
    if not pred_result.get("prediction_id"):
        return {**pred_result, "status": "failed: no prediction created"}

    pred_id = pred_result["prediction_id"]

    # Step 2: 获取 Prediction
    pred_store = PredictionStore.get(db_path)
    belief_store = BeliefStore.get(db_path)
    outcome_store = OutcomeStore.get(db_path)

    # 找最新创建的 prediction
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM predictions WHERE id LIKE ? ORDER BY created_at DESC LIMIT 1",
        (pred_id + "%",)
    ).fetchone()
    conn.close()
    if not row:
        return {**pred_result, "status": "failed: prediction not found"}
    prediction = pred_store._row_to_entity(row)

    # Step 3: 注入 Outcome（actual_value 替换 expected）
    actual = stock["actual_value"]
    expected = stock["expected_value"]
    error = abs(actual - expected)
    error_type = stock["error_type"]

    outcome = Outcome(
        id=Outcome.generate_id(prediction.id, str(actual)),
        prediction_id=prediction.id,
        actual_value=actual,
        actual_result=stock["result"],
        prediction_error=round(error, 4),
        error_type=error_type,
        reason=f"实际值={actual}, 预期值={expected}, 误差={error:.4f}",
    )
    outcome_store.insert(outcome)

    # Step 4: 获取 Belief
    belief = None
    if prediction.belief_id:
        try:
            belief = belief_store.get_by_id(prediction.belief_id)
        except Exception:
            pass

    # Step 5: 触发 Learning
    learning = None
    belief_adjustment = 0.0
    if belief:
        pipeline = EnhancedLearningPipeline(db_path)
        lr_result = pipeline.run(
            outcome=outcome,
            prediction=prediction,
            belief=belief,
        )
        learning = lr_result.get("learning")
        belief_adjustment = lr_result.get("belief_adjustment", 0.0)
    else:
        pred_store.mark_realized(prediction.id)

    return {
        "subject": stock["subject"],
        "expected": expected,
        "actual": actual,
        "prediction_id": prediction.id[:8],
        "outcome_id": outcome.id[:8],
        "error": round(error, 4),
        "error_type": error_type.value,
        "learning_id": learning.id[:8] if learning else None,
        "belief_adjustment": round(belief_adjustment, 4),
        "status": "success",
    }


def main():
    parser = argparse.ArgumentParser(description="测试股票 Learning 闭环")
    parser.add_argument("--dry", action="store_true", help="只建预测，不学习")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    db_path = str(V4_DIR / "cognition_v4.db")
    results = []

    for stock in TEST_STOCKS:
        if args.dry:
            r = run_prediction_only(stock, db_path)
            r["status"] = "dry-run"
        else:
            r = run_full_loop(stock, db_path)
        results.append(r)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("=== 测试股票 Learning 闭环 ===")
        for r in results:
            if r["status"] == "success":
                print(
                    f"  ✅ {r['subject']}: "
                    f"exp={r['expected']} act={r['actual']} "
                    f"err={r['error']} ({r['error_type']}) "
                    f"→ learning={r.get('learning_id','N/A')} adj={r.get('belief_adjustment',0):+.4f}"
                )
            elif r["status"] == "dry-run":
                print(f"  [DRY] {r['subject']}: pred={r.get('prediction_id','N/A')} eff={r.get('effective_score')}")
            else:
                print(f"  ❌ {r['subject']}: {r.get('status')}")


if __name__ == "__main__":
    main()
