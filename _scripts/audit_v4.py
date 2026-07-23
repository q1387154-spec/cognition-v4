#!/usr/bin/env python3
"""审计认知系统 V4 —— 数据量、缺陷、精度"""
import sqlite3, json
from pathlib import Path

DB = Path.home() / "hermes" / "cognition-v4" / "cognition_v4.db"
conn = sqlite3.connect(str(DB))

# 1. 各表数据量
print("=" * 60)
print("一、数据量总览")
print("=" * 60)
tables = ["observations", "evidence", "beliefs", "predictions", "outcomes",
          "learning", "entity_accuracy", "causal_nodes", "causal_edges",
          "prediction_bindings"]
for t in tables:
    c = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {c}")

# 新增数据（7月22日起）
print()
new_tables = ["observations", "evidence", "beliefs", "predictions", "outcomes", "learning"]
for t in new_tables:
    c = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE created_at >= '2026-07-22'").fetchone()[0]
    print(f"  {t} (7月22日+): {c}")

# 2. Predictions expected_value
print()
print("=" * 60)
print("二、Predictions — expected_value 分布")
print("=" * 60)
preds = conn.execute("SELECT target, expected_value, confidence, created_at FROM predictions ORDER BY created_at DESC LIMIT 25").fetchall()
for p in preds:
    print(f"  {p[0]:12s} | exp={p[1]:>8.2f} | conf={p[2]:.4f} | {p[3]}")

# 统计有多少 expected_value = 1.015 (默认值)
default_count = conn.execute("SELECT COUNT(*) FROM predictions WHERE expected_value = 1.015").fetchone()[0]
total_preds = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
print(f"\n  expected_value=1.015(默认值): {default_count}/{total_preds} ({default_count/total_preds*100:.0f}%)")

# 3. Outcome 精度
print()
print("=" * 60)
print("三、Outcome 精度")
print("=" * 60)
errs = conn.execute("SELECT error_type, COUNT(*) FROM outcomes GROUP BY error_type").fetchall()
for e in errs:
    print(f"  {e[0]}: {e[1]}")
total_out = sum(e[1] for e in errs)
print(f"  总计: {total_out}")

# 最近10条 outcome
print()
print("  最近10条 outcome:")
outs = conn.execute("SELECT prediction_id, actual_value, error_type, created_at FROM outcomes ORDER BY created_at DESC LIMIT 10").fetchall()
for o in outs:
    print(f"    pred={o[0][:8]} | actual={o[1]:.2f} | {o[2]} | {o[3]}")

# 4. Entity Accuracy
print()
print("=" * 60)
print("四、Entity Accuracy")
print("=" * 60)
cols = [c[1] for c in conn.execute("PRAGMA table_info(entity_accuracy)").fetchall()]
print(f"  列: {cols}")
acc = conn.execute("SELECT * FROM entity_accuracy").fetchall()
for a in acc:
    print(f"  {a}")

# 5. 因果图谱
print()
print("=" * 60)
print("五、因果图谱")
print("=" * 60)
nodes = conn.execute("SELECT COUNT(*) FROM causal_nodes").fetchone()[0]
edges = conn.execute("SELECT COUNT(*) FROM causal_edges").fetchone()[0]
print(f"  nodes: {nodes}, edges: {edges}")

# 6. 错误统计: 有多少 outcome 的 actual_result 里 expected=1.015
print()
print("=" * 60)
print("六、缺陷分析")
print("=" * 60)
# 检查 meta 中 expected_value 异常的
bug_outcomes = conn.execute("""
    SELECT COUNT(*) FROM outcomes 
    WHERE json_extract(metadata, '$.expected_value') = 1.015
""").fetchone()[0]
print(f"  预期值=1.015(默认值未修正)的outcome: {bug_outcomes}/{total_out}")

# 检查 predictions 生成的场景
scenario_count = conn.execute("SELECT SUM(json_array_length(scenarios)) FROM predictions WHERE scenarios != '[]' AND scenarios IS NOT NULL").fetchone()[0]
print(f"  有场景的prediction: {scenario_count}")

# 检查 bound_evidence
bound_count = conn.execute("SELECT COUNT(*) FROM predictions WHERE bound_evidence_ids != '[]' AND bound_evidence_ids IS NOT NULL").fetchone()[0]
print(f"  有绑定证据的prediction: {bound_count}/{total_preds}")

# 检查 beliefs 最新状态
print()
latest_beliefs = conn.execute("""
    SELECT b1.target, b1.probability, b1.confidence, b1.created_at
    FROM beliefs b1
    WHERE b1.created_at = (SELECT MAX(b2.created_at) FROM beliefs b2 WHERE b2.target = b1.target)
    ORDER BY b1.target
""").fetchall()
print("  最新 beliefs:")
for b in latest_beliefs:
    print(f"    {b[0]:12s} | prob={b[1]:.4f} | conf={b[2]:.4f} | {b[3]}")

conn.close()