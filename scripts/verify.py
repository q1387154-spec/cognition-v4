#!/usr/bin/env python3
"""
验证预测 — 输入实际结果，生成 Outcome + Learning

Usage:
    python scripts/verify.py --prediction-id <id> --actual-value <value> --result "描述"
    python scripts/verify.py --subject "赛力斯毛利率" --actual-value 25.0 --result "毛利率25%低于预期"
"""
import argparse, sys, json
from pathlib import Path

V4_DIR = Path.home() / "hermes" / "cognition-v4"
sys.path.insert(0, str(V4_DIR))

from workflow import EnhancedLearningPipeline
from core import Outcome, ErrorType
from memory import BeliefStore, PredictionStore, OutcomeStore


def main():
    parser = argparse.ArgumentParser(description="验证预测 + 学习")
    parser.add_argument("--prediction-id", help="预测 ID")
    parser.add_argument("--subject", help="信念主体（自动选最新活跃预测）")
    parser.add_argument("--actual-value", type=float, required=True, help="实际值")
    parser.add_argument("--result", required=True, help="实际结果描述")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    db_path = str(V4_DIR / "cognition_v4.db")
    pred_store = PredictionStore.get(db_path)
    belief_store = BeliefStore.get(db_path)
    outcome_store = OutcomeStore.get(db_path)

    # 找 Prediction
    prediction = None
    if args.prediction_id:
        prediction = pred_store.get(args.prediction_id)
    elif args.subject:
        conn = pred_store._connect()
        row = conn.execute(
            "SELECT * FROM predictions WHERE target=? AND status='active' ORDER BY created_at DESC LIMIT 1",
            (args.subject,)
        ).fetchone()
        conn.close()
        if row:
            prediction = pred_store._row_to_entity(row)

    if not prediction:
        print("未找到 Prediction", file=sys.stderr)
        sys.exit(1)

    # 计算误差
    expected_value = prediction.expected_value or 0.5
    error = abs(args.actual_value - expected_value)
    error_type = ErrorType.NO_ERROR if error < 0.05 else (
        ErrorType.OVERCONFIDENCE if error > 0.3 else ErrorType.REASONABLE
    )

    # 创建 Outcome
    outcome = Outcome(
        id=Outcome.generate_id(prediction.id, str(args.actual_value)),
        prediction_id=prediction.id,
        actual_value=args.actual_value,
        actual_result=args.result,
        prediction_error=round(error, 4),
        error_type=error_type,
        reason=f"实际值={args.actual_value}, 预期值={expected_value:.4f}, 误差={error:.4f}",
    )

    # 持久化 Outcome
    outcome_store.insert(outcome)

    # 找 Belief
    belief = None
    if prediction.belief_id:
        try:
            belief = belief_store.get(prediction.belief_id)
        except Exception:
            pass

    # 学习
    if belief:
        pipeline = EnhancedLearningPipeline(db_path)
        result = pipeline.run(
            outcome=outcome,
            prediction=prediction,
            belief=belief,
        )
        learning = result.get("learning")
        belief_adjustment = result.get("belief_adjustment", 0.0)
    else:
        learning = None
        belief_adjustment = 0.0

    if args.json:
        out = {
            "prediction": prediction.id[:8],
            "outcome": outcome.id[:8],
            "error": round(error, 4),
            "error_type": error_type.value,
            "learning": learning.id[:8] if learning else None,
            "belief_adjustment": round(belief_adjustment, 4),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"=== 验证完成 ===")
        print(f"  预测:  {prediction.target} | {prediction.horizon_label.value}")
        print(f"  预期值: {expected_value:.4f}")
        print(f"  实际值: {args.actual_value}")
        print(f"  误差:   {error:.4f} ({error_type.value})")
        if learning:
            print(f"  学习:   {learning.id[:8]} | 类型={learning.learning_type.value} | 调整={belief_adjustment:+.4f}")
        print(f"  Outcome: {outcome.id[:8]}")


if __name__ == "__main__":
    main()