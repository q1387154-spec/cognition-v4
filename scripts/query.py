#!/usr/bin/env python3
"""
Query cognitive state — 查询信念/预测/准确率

Usage:
    python scripts/query.py --subject "赛力斯"                  # 查询指定信念
    python scripts/query.py --list                                # 列出所有活跃信念
    python scripts/query.py --accuracy --subject "赛力斯"        # 查询准确率
    python scripts/query.py --due-predictions                    # 列出到期未验证的预测
"""
import argparse, sys, json
from pathlib import Path

V4_DIR = Path.home() / "hermes" / "cognition-v4"
sys.path.insert(0, str(V4_DIR))

from memory import BeliefStore, PredictionStore, OutcomeStore, LearningStore


def main():
    parser = argparse.ArgumentParser(description="认知状态查询")
    parser.add_argument("--subject", help="信念主体")
    parser.add_argument("--list", action="store_true", help="列出所有活跃信念")
    parser.add_argument("--accuracy", action="store_true", help="查询准确率")
    parser.add_argument("--due-predictions", action="store_true", help="到期未验证的预测")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    db_path = str(V4_DIR / "cognition_v4.db")
    belief_store = BeliefStore.get(db_path)
    pred_store = PredictionStore.get(db_path)
    outcome_store = OutcomeStore.get(db_path)
    learning_store = LearningStore.get(db_path)

    if args.list:
        # 列出所有活跃 Belief
        all_beliefs = []
        conn = belief_store._connect()
        rows = conn.execute("SELECT DISTINCT subject FROM beliefs WHERE status='active' ORDER BY subject").fetchall()
        conn.close()
        for r in rows:
            all_beliefs.append(r["subject"])
        if args.json:
            print(json.dumps({"subjects": all_beliefs}, ensure_ascii=False, indent=2))
        else:
            print(f"=== 活跃信念 ({len(all_beliefs)}) ===")
            for s in all_beliefs:
                print(f"  - {s}")

    elif args.subject and not args.accuracy:
        # 查询 Belief + Prediction
        if args.json:
            result = {"subject": args.subject, "beliefs": [], "predictions": []}
        else:
            print(f"=== 信念状态: {args.subject} ===")

        conn = belief_store._connect()
        rows = conn.execute(
            "SELECT * FROM beliefs WHERE subject=? ORDER BY version DESC LIMIT 5",
            (args.subject,)
        ).fetchall()
        conn.close()

        for row in rows:
            b = {
                "version": row["version"],
                "probability": row["probability"],
                "confidence": row["confidence"],
                "status": row["status"],
                "updated": row["update_time"],
            }
            if args.json:
                result["beliefs"].append(b)
            else:
                print(f"  v{row['version']}: 概率={row['probability']:.2f} 置信度={row['confidence']:.2f} 状态={row['status']} [{row['update_time']}]")

        # 查询 Prediction
        conn = pred_store._connect()
        p_rows = conn.execute(
            "SELECT * FROM predictions WHERE target=? AND status='active' ORDER BY created_at DESC LIMIT 5",
            (args.subject,)
        ).fetchall()
        conn.close()
        for row in p_rows:
            p = {
                "id": row["id"][:8],
                "horizon": row["horizon_label"],
                "confidence": row["confidence"],
                "effective_score": row["effective_score"],
                "catalyst": row["catalyst"],
                "regime": row["regime"],
                "created": row["created_at"],
            }
            if args.json:
                result["predictions"].append(p)
            else:
                print(f"  预测: horizon={row['horizon_label']} 置信度={row['confidence']:.2f} 得分={row['effective_score']:.3f}")
                if row["catalyst"]:
                    print(f"    催化剂: {row['catalyst']}")
                if row["regime"]:
                    print(f"    Regime: {row['regime']}")

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.accuracy and args.subject:
        # 查询准确率
        conn = outcome_store._connect()
        rows = conn.execute("""
            SELECT o.prediction_id, o.actual_result, o.prediction_error, o.error_type, o.realized_at
            FROM outcomes o
            JOIN predictions p ON o.prediction_id = p.id
            WHERE p.target=?
            ORDER BY o.realized_at DESC
        """, (args.subject,)).fetchall()
        conn.close()

        if args.json:
            outcomes = [{"prediction_id": r["prediction_id"][:8], "result": r["actual_result"], "error": r["prediction_error"], "type": r["error_type"], "realized": r["realized_at"]} for r in rows]
            print(json.dumps({"subject": args.subject, "outcomes": outcomes}, ensure_ascii=False, indent=2))
        else:
            print(f"=== 验证历史: {args.subject} ({len(rows)} 条) ===")
            for r in rows:
                print(f"  {r['realized_at']}: 误差={r['prediction_error']:.3f} 类型={r['error_type']} 结果={r['actual_result']}")

    elif args.due_predictions:
        # 到期未验证的预测
        due = pred_store.list_due()
        if args.json:
            print(json.dumps({"due": [{"id": d.id[:8], "target": d.target, "horizon": d.horizon_label.value} for d in due]}, ensure_ascii=False, indent=2))
        else:
            print(f"=== 到期未验证预测 ({len(due)}) ===")
            for d in due:
                print(f"  {d.target} | {d.horizon_label.value} | id={d.id[:8]}")


if __name__ == "__main__":
    main()