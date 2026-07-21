#!/usr/bin/env python3
"""同步 V4 认知 DB → Wiki entities/cognition/"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from memory import BeliefStore, PredictionStore, OutcomeStore
import argparse

WIKI_DIR = Path.home() / "wiki"
V4_DIR = Path(__file__).parent.parent

def sync_one(subject: str, dry_run: bool):
    safe_name = "cog_" + subject.replace(" ", "_").replace("/", "_")
    wiki_path = WIKI_DIR / "entities" / "cognition" / f"{safe_name}.md"

    store = BeliefStore.get(str(V4_DIR / "cognition_v4.db"))
    conn = store._connect()
    b_row = conn.execute(
        "SELECT * FROM beliefs WHERE subject=? ORDER BY version DESC LIMIT 1",
        (subject,)
    ).fetchone()
    conn.close()

    if not b_row:
        print(f"❌ 未找到 {subject} 的信念")
        return

    # 查预测
    pstore = PredictionStore.get(str(V4_DIR / "cognition_v4.db"))
    pconn = pstore._connect()
    p_rows = pconn.execute(
        "SELECT * FROM predictions WHERE target=? AND status='active' ORDER BY created_at DESC LIMIT 5",
        (subject,)
    ).fetchall()
    pconn.close()

    # 查历史验证
    ostore = OutcomeStore.get(str(V4_DIR / "cognition_v4.db"))
    oconn = ostore._connect()
    o_rows = oconn.execute("""
        SELECT o.prediction_error, o.error_type, o.realized_at
        FROM outcomes o
        JOIN predictions p ON o.prediction_id = p.id
        WHERE p.target=?
        ORDER BY o.realized_at DESC LIMIT 5
    """, (subject,)).fetchall()
    oconn.close()

    if dry_run:
        print(f"  [dry-run] 会写: {wiki_path}")
        print(f"    信念: v{b_row['version']} prob={b_row['probability']:.2f} conf={b_row['confidence']:.2f}")
        print(f"    预测: {len(p_rows)} 条")
        return

    lines = ["---"]
    lines.append(f"title: 信念: {subject}")
    lines.append(f"created: {b_row['created_at'][:10]}")
    lines.append(f"updated: {b_row['update_time'][:10]}")
    lines.append(f"type: cognition")
    lines.append(f"tags: [cognitive, belief, {b_row['domain']}]")
    lines.append(f"confidence: {b_row['confidence']:.2f}")
    lines.append("---")
    lines.append("")
    lines.append(f"# 信念: {subject}")
    lines.append("")
    lines.append(f"| 属性 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 概率 | {b_row['probability']:.2f} |")
    lines.append(f"| 置信度 | {b_row['confidence']:.2f} |")
    lines.append(f"| 版本 | v{b_row['version']} |")
    lines.append(f"| 状态 | {b_row['status']} |")
    lines.append(f"| 更新 | {b_row['update_time']} |")
    lines.append("")

    if p_rows:
        lines.append("## 活跃预测")
        lines.append("")
        lines.append("| 时间窗口 | 置信度 | 得分 | 催化剂 |")
        lines.append("|---------|--------|------|-------|")
        for p in p_rows:
            lines.append(f"| {p['horizon_label']} | {p['confidence']:.2f} | {p['effective_score']:.3f} | {p['catalyst'] or '-'} |")
        lines.append("")

    if o_rows:
        lines.append("## 历史验证")
        lines.append("")
        avg_err = sum(r["prediction_error"] for r in o_rows) / len(o_rows)
        lines.append(f"平均误差: {avg_err:.4f} ({len(o_rows)} 条)")
        lines.append("")
        for r in o_rows:
            lines.append(f"- {r['realized_at'][:10]}: {r['prediction_error']:.4f} ({r['error_type']})")

    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 已同步: {wiki_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", help="要同步的信念主体")
    parser.add_argument("--all", action="store_true", help="同步所有活跃信念")
    parser.add_argument("--dry-run", action="store_true", help="预览")
    args = parser.parse_args()

    if args.subject:
        sync_one(args.subject, args.dry_run)
    elif args.all:
        store = BeliefStore.get(str(V4_DIR / "cognition_v4.db"))
        conn = store._connect()
        subjects = conn.execute("SELECT DISTINCT subject FROM beliefs WHERE status='active'").fetchall()
        conn.close()
        count = 0
        for r in subjects:
            try:
                sync_one(r["subject"], args.dry_run)
                count += 1
            except Exception as e:
                print(f"  ⚠️ {r['subject']}: {e}")
        print(f"✅ 同步 {count}/{len(subjects)} 个信念")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()