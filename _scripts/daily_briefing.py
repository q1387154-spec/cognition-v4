"""认知系统每日简报 — 给刘理/徐雄的持仓决策辅助"""
import sqlite3
from pathlib import Path
from datetime import datetime, date

DB = Path.home() / "hermes" / "cognition-v4" / "cognition_v4.db"
db = sqlite3.connect(str(DB))
db.row_factory = sqlite3.Row

today = date.today().isoformat()
today_dt = f"{today}T00:00:00"

lines = []
lines.append(f"🧠 认知系统简报 {today}")
lines.append("")

# ── 1. 今日预测概览 ──
cur = db.execute("""
    SELECT p.target, p.confidence, p.horizon_label,
           json_extract(p.scenarios, '$.optimistic.value') as opt,
           json_extract(p.scenarios, '$.pessimistic.value') as pess,
           json_extract(p.scenarios, '$.black_swan.value') as swan,
           p.expected_value, ROUND(AVG(o.prediction_error), 1) as avg_err
    FROM predictions p
    LEFT JOIN outcomes o ON o.prediction_id = p.id
    WHERE date(p.created_at) = date('now')
    GROUP BY p.target
    ORDER BY p.target
""")
predictions = cur.fetchall()
if predictions:
    lines.append("📊 今日预测")
    for r in predictions:
        tag = "⚠️" if r["avg_err"] and r["avg_err"] > 20 else ""
        lines.append(f"  {tag} {r['target']:15s}  conf={r['confidence']:.2f}  {r['horizon_label']:4s}")
        opt = r['opt'] or '—'
        pess = r['pess'] or '—'
        swan = r['swan'] or '—'
        ev = r['expected_value'] or '—'
        lines.append(f"     乐观 {opt:>8s}  悲观 {pess:>8s}  黑天鹅 {swan:>8s}  expect={ev}")

# ── 2. 今日新因果链 ──
cur = db.execute("""
    SELECT e.from_node, e.edge_type, e.to_node, ROUND(e.weight,2) as w
    FROM causal_edges e
    WHERE date(e.created_at) = date('now')
    ORDER BY e.weight DESC LIMIT 5
""")
edges = cur.fetchall()
if edges:
    lines.append("")
    lines.append("🔗 新因果链")
    for r in edges:
        arrow = "→" if r["edge_type"] in ("drives", "influences", "positively_impacts") else "─"
        lines.append(f"  {r['from_node']:20s} {arrow}[{r['edge_type']:20s}]  {r['to_node']:20s}  w={r['w']:.2f}")

# ── 3. 实体精度变化 ──
cur = db.execute("""
    SELECT entity_name, metric, predicted_count, verified_count,
           ROUND(accuracy_rate, 2) as acc, accuracy_trend
    FROM entity_accuracy
    ORDER BY accuracy_rate DESC
""")
accs = cur.fetchall()
if accs:
    lines.append("")
    lines.append("📈 实体精度")
    for r in accs:
        icon = "✅" if r["acc"] > 0.5 else "⬜" if r["acc"] > 0 else "🆕"
        trend = "↑" if r["accuracy_trend"] == "improving" else "↓" if r["accuracy_trend"] == "declining" else "→"
        lines.append(f"  {icon}{trend} {r['entity_name']:10s} {r['metric']:10s}  {r['acc']:.0%}  ({r['verified_count']}/{r['predicted_count']} 验证)")

# ── 4. 今日新增 outcome ──
cur = db.execute("""
    SELECT o.prediction_error, o.error_type, o.reason
    FROM outcomes o
    WHERE date(o.created_at) = date('now')
    ORDER BY o.prediction_error DESC LIMIT 3
""")
outcomes = cur.fetchall()
if outcomes:
    lines.append("")
    lines.append("❌ 今日误差")
    for r in outcomes:
        lines.append(f"  {r['error_type']:20s}  error={r['prediction_error']:.1f}")

# ── 5. 系统状态 ──
cur = db.execute("SELECT COUNT(*) FROM predictions")
pred_cnt = cur.fetchone()[0]
cur = db.execute("SELECT COUNT(*) FROM causal_nodes")
node_cnt = cur.fetchone()[0]
cur = db.execute("SELECT COUNT(*) FROM causal_edges")
edge_cnt = cur.fetchone()[0]
cur = db.execute("SELECT COUNT(*) FROM entity_accuracy")
acc_cnt = cur.fetchone()[0]

lines.append("")
lines.append("───")
lines.append(f"📊 系统累计: {pred_cnt} 预测 / {node_cnt} 因果节点 / {edge_cnt} 边 / {acc_cnt} 实体精度追踪")

db.close()
print("\n".join(lines))