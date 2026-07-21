"""Generate causal graph snapshot for Obsidian wiki."""
import sqlite3
from pathlib import Path

DB = Path.home() / "hermes" / "cognition-v4" / "cognition_v4.db"
OUT = Path.home() / "wiki" / "cognition-v4" / "causal-graph-snapshot.md"

db = sqlite3.connect(str(DB))
db.row_factory = sqlite3.Row

# 基础统计
node_types = {}
cur = db.execute("SELECT node_type, COUNT(*) as cnt FROM causal_nodes GROUP BY node_type")
for r in cur:
    node_types[r["node_type"]] = r["cnt"]

edge_types = {}
cur = db.execute("SELECT edge_type, COUNT(*) as cnt FROM causal_edges GROUP BY edge_type")
for r in cur:
    edge_types[r["edge_type"]] = r["cnt"]

# 最强边
cur = db.execute("""
    SELECT from_node, edge_type, to_node, ROUND(weight,3) as w
    FROM causal_edges ORDER BY weight DESC LIMIT 10
""")
strong_edges = [(r["from_node"], r["edge_type"], r["to_node"], r["w"]) for r in cur.fetchall()]

# 每个主体被影响的边
cur = db.execute("SELECT DISTINCT to_node FROM causal_edges ORDER BY to_node")
entity_edges = {}
for r in cur.fetchall():
    e = r["to_node"]
    rows = db.execute(
        "SELECT from_node, edge_type, ROUND(weight,3) as w FROM causal_edges WHERE to_node=? ORDER BY weight DESC",
        (e,),
    ).fetchall()
    entity_edges[e] = [(r2["from_node"], r2["edge_type"], r2["w"]) for r2 in rows]

# 写 Markdown
lines = []
lines.append("---")
lines.append("created: 2026-07-21T13:00")
lines.append("updated: 2026-07-21T13:00")
lines.append("tags: [cognition-v4, causal, 因果图谱]")
lines.append("---")
lines.append("")
lines.append("# 认知系统 V4 因果图谱")
lines.append("")
lines.append("> 数据来源：`cognition_v4.db` causal_nodes / causal_edges 表")
lines.append("> 自动更新：cron 每天凌晨 3:00（也可手动 `hermes cron run d524ae68f8b0`）")
lines.append("")
lines.append("## 统计概览")
lines.append("")
lines.append(f"- 总节点：{sum(node_types.values())} 个")
lines.append(f"- 总边：{sum(edge_types.values())} 条")
lines.append("")
lines.append("### 节点类型分布")
lines.append("")
lines.append("| 类型 | 数量 | 说明 |")
lines.append("|------|------|------|")
lines.append(f"| macro | {node_types.get('macro', 0)} | 宏观因素（GDP/利率）|")
lines.append(f"| industry | {node_types.get('industry', 0)} | 行业因素（MDI 价格）|")
lines.append(f"| entity | {node_types.get('entity', 0)} | 公司/主体 |")
lines.append(f"| metric | {node_types.get('metric', 0)} | 指标（增长/下滑/下降）|")
lines.append(f"| event | {node_types.get('event', 0)} | 事件（突破）|")
lines.append("")
lines.append("### 边类型分布")
lines.append("")
for t, c in sorted(edge_types.items()):
    lines.append(f"- **{t}**：{c} 条")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## 最强因果链（Top 10）")
lines.append("")
lines.append("| 原因 | 关系 | 结果 | 权重 |")
lines.append("|------|------|------|------|")
for f, et, to, w in strong_edges:
    lines.append(f"| {f} | {et} | {to} | {w} |")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## 按主体查看")
lines.append("")
for entity, edges in sorted(entity_edges.items()):
    lines.append(f"### {entity}")
    lines.append("")
    lines.append("| 上游节点 | 关系 | 权重 |")
    lines.append("|----------|------|------|")
    for fn, et, w in edges:
        lines.append(f"| {fn} | {et} | {w} |")
    lines.append("")
lines.append("---")
lines.append("")
lines.append("## 更新说明")
lines.append("")
lines.append("因果图谱由 cron（d524ae68f8b0）每天凌晨 3:00 自动更新。")
lines.append("如需手动刷新：`hermes cron run d524ae68f8b0`")
lines.append("")

db.close()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"✅ 写入 {OUT}")