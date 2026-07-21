"""
auto_learn.py — 自动注入 Outcome + 触发 Learning 闭环

策略：
1. 扫描所有到期但未验证的 active predictions（horizon 已过）
2. 用模拟数据生成 Outcome（测试股票用，后替换为真实数据源）
3. 调用 EnhancedLearningPipeline 完成 Learning 闭环

Usage:
    python scripts/auto_learn.py                    # 自动处理所有到期 prediction
    python scripts/auto_learn.py --stock 腾讯       # 只处理腾讯相关
    python scripts/auto_learn.py --dry-run          # 只看有哪些到期，不执行
    python scripts/auto_learn.py --prediction-id xxx --actual-value 28.5 --result "实际毛利率28.5%"
"""
import argparse
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

V4_DIR = Path.home() / "hermes" / "cognition-v4"
sys.path.insert(0, str(V4_DIR))

from workflow import EnhancedLearningPipeline
from core import Outcome, ErrorType
from memory import BeliefStore, PredictionStore, OutcomeStore


# ============================================================
# 测试股票模拟数据（替换为真实数据源前使用）
# 格式：subject → {expected_value, actual_value, result_description}
# ============================================================
TEST_STOCK_DATA: Dict[str, Dict[str, Any]] = {
    "腾讯毛利率": {
        "expected": 46.0,
        "actual": 44.5,
        "result": "2026Q2 毛利率 44.5%，略低于预期，受游戏业务拖累",
        "error_type": ErrorType.MISSING_SIGNAL,
    },
    "招行净息差": {
        "expected": 2.15,
        "actual": 2.08,
        "result": "2026H1 净息差 2.08%，银行让利实体经济拖累",
        "error_type": ErrorType.OVERCONFIDENCE,
    },
    "英伟达营收增长": {
        "expected": 85.0,
        "actual": 122.0,
        "result": "2026Q2 营收同比 +122%，AI 芯片需求超预期",
        "error_type": ErrorType.MISSING_SIGNAL,
    },
    "工行不良贷款率": {
        "expected": 1.42,
        "actual": 1.45,
        "result": "2026H1 不良率 1.45%，房地产风险传导略超预期",
        "error_type": ErrorType.REGIME_MISMATCH,
    },
    "ZTO 单票成本": {
        "expected": 2.10,
        "actual": 2.18,
        "result": "2026Q2 单票成本 2.18 元，燃油+人力成本上涨超预期",
        "error_type": ErrorType.OVERCONFIDENCE,
    },
}


def get_test_outcome_data(target: str) -> Optional[Dict[str, Any]]:
    """根据 target 匹配测试数据。"""
    for key, data in TEST_STOCK_DATA.items():
        if key in target or target in key:
            return data
    return None


def compute_error(expected: float, actual: float) -> tuple[float, ErrorType]:
    """计算预测误差和类型。"""
    error = abs(actual - expected)
    if error < 0.03:
        return round(error, 4), ErrorType.NO_ERROR
    elif error > 0.25:
        return round(error, 4), ErrorType.OVERCONFIDENCE
    else:
        return round(error, 4), ErrorType.REASONABLE


def process_prediction(
    pred_id: str,
    actual_value: float,
    result_desc: str,
    db_path: str,
    dry_run: bool = False,
    error_type_override: Optional[ErrorType] = None,
) -> Optional[Dict[str, Any]]:
    """处理单个 prediction → Outcome → Learning。"""
    pred_store = PredictionStore.get(db_path)
    belief_store = BeliefStore.get(db_path)
    outcome_store = OutcomeStore.get(db_path)

    prediction = pred_store.get(pred_id)
    if not prediction:
        return None

    # 获取测试数据
    test_data = get_test_outcome_data(prediction.target)
    if test_data:
        expected_value = test_data["expected"]
    else:
        expected_value = prediction.expected_value or 0.5

    if error_type_override:
        error_type = error_type_override
        error = abs(actual_value - expected_value) / expected_value if expected_value else abs(actual_value - expected_value)
    else:
        error, error_type = compute_error(expected_value, actual_value)

    # 构建 Outcome
    outcome = Outcome(
        id=Outcome.generate_id(prediction.id, str(actual_value)),
        prediction_id=prediction.id,
        actual_value=actual_value,
        actual_result=result_desc,
        prediction_error=round(error, 4),
        error_type=error_type,
        reason=f"实际值={actual_value}, 预期值={expected_value:.4f}, 误差={error:.4f}",
    )

    if dry_run:
        return {
            "prediction_id": prediction.id[:8],
            "target": prediction.target,
            "expected_value": expected_value,
            "actual_value": actual_value,
            "error": round(error, 4),
            "error_type": error_type.value,
            "status": "DRY-RUN（未执行）",
        }

    # 持久化 Outcome
    outcome_store.insert(outcome)

    # 找 Belief
    belief = None
    if prediction.belief_id:
        try:
            belief = belief_store.get(prediction.belief_id)
        except Exception:
            pass

    # 触发 Learning
    learning = None
    belief_adjustment = 0.0
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
        # 无 belief 时直接标记 realized
        pred_store.mark_realized(prediction.id)

    return {
        "prediction_id": prediction.id[:8],
        "target": prediction.target,
        "outcome_id": outcome.id[:8],
        "error": round(error, 4),
        "error_type": error_type.value,
        "learning_id": learning.id[:8] if learning else None,
        "belief_adjustment": round(belief_adjustment, 4),
        "status": "success",
    }


def list_due_predictions(db_path: str, as_of: Optional[datetime] = None) -> List[Any]:
    """列出所有到期的 active predictions。"""
    pred_store = PredictionStore.get(db_path)
    return pred_store.list_due(as_of or datetime.now())


def auto_fill_outcomes(db_path: str, dry_run: bool = False) -> List[Dict[str, Any]]:
    """自动为到期 predictions 生成 Outcome + Learning。"""
    pred_store = PredictionStore.get(db_path)
    outcome_store = OutcomeStore.get(db_path)

    due_preds = pred_store.list_due()
    results = []

    for pred in due_preds:
        # 检查是否已有 outcome
        conn = outcome_store._connect()
        existing = conn.execute(
            "SELECT id FROM outcomes WHERE prediction_id=?", (pred.id,)
        ).fetchone()
        conn.close()
        if existing:
            results.append({
                "prediction_id": pred.id[:8],
                "target": pred.target,
                "status": "已有效 outcome，跳过",
            })
            continue

        # 获取测试数据
        test_data = get_test_outcome_data(pred.target)
        if not test_data:
            results.append({
                "prediction_id": pred.id[:8],
                "target": pred.target,
                "expected_value": pred.expected_value,
                "status": "无测试数据，跳过（需手动 verify.py）",
            })
            continue

        # 使用测试数据
        actual_value = test_data["actual"]
        result_desc = test_data["result"]
        error_type_override = test_data.get("error_type")

        outcome_result = process_prediction(
            pred_id=pred.id,
            actual_value=actual_value,
            result_desc=result_desc,
            db_path=db_path,
            dry_run=dry_run,
            error_type_override=error_type_override,
        )
        if outcome_result:
            results.append(outcome_result)

    return results


def main():
    parser = argparse.ArgumentParser(description="自动 Learning 闭环")
    parser.add_argument("--dry-run", action="store_true", help="只显示到期 prediction，不执行")
    parser.add_argument("--stock", help="只处理指定股票的 prediction")
    parser.add_argument("--prediction-id", help="指定 prediction ID")
    parser.add_argument("--actual-value", type=float, help="手动指定实际值")
    parser.add_argument("--result", help="手动指定结果描述")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    db_path = str(V4_DIR / "cognition_v4.db")

    if args.prediction_id and args.actual_value is not None and args.result:
        # 手动单条验证
        result = process_prediction(
            args.prediction_id,
            args.actual_value,
            args.result,
            db_path,
        )
        if not result:
            print("未找到 Prediction", file=sys.stderr)
            sys.exit(1)
        output = [result] if args.json else format_results([result])
    else:
        # 自动处理所有到期
        results = auto_fill_outcomes(db_path, dry_run=args.dry_run)

        if args.stock:
            results = [r for r in results if args.stock in r.get("target", "")]

        if args.dry_run:
            for r in results:
                r["status"] = "DRY-RUN"
            output = results
        else:
            output = results

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for line in format_results(output):
            print(line)


def format_results(results: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for r in results:
        if "status" in r and "DRY-RUN" in r["status"]:
            target = r.get("target", "?")
            exp = r.get("expected_value", "?")
            act = r.get("actual_value", "?")
            err = r.get("error", "?")
            lines.append(f"  [DRY-RUN] {target}: exp={exp} act={act} error={err}")
        elif r.get("status") == "success":
            lines.append(
                f"  ✅ {r['target']}: error={r['error']} ({r['error_type']}) "
                f"→ learning={r.get('learning_id','N/A')} adj={r.get('belief_adjustment',0):+.4f}"
            )
        elif r.get("status") == "已有效 outcome，跳过":
            lines.append(f"  ⏭ {r['target']}: {r['status']}")
        else:
            lines.append(f"  ⚠ {r.get('target','?')}: {r.get('status','?')}")
    return lines


if __name__ == "__main__":
    main()
