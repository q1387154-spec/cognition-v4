#!/usr/bin/env python3
"""决策记录与复盘系统
记录每次买入/卖出/持有建议，定期复盘实际结果。

用法:
  python decision_log.py record          # 交互式录入新决策
  python decision_log.py record --json '{"type":"buy","name":"赛力斯","price":55.89}'
  python decision_log.py check           # 检查所有待复盘决策
  python decision_log.py report          # 生成统计报告
  python decision_log.py summary         # 一句话总结
"""

import json, sys, os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

LOG_DIR = Path.home() / "hermes" / "decision-log"
LOG_FILE = LOG_DIR / "decisions.json"
WIKI_DIR = Path.home() / "wiki" / "concepts" / "决策记录"

# 八个持仓的基准信息
HOLDINGS = {
    "招商银行": {"symbol": "sh600036", "market": "A股", "buy_ref": 36, "target": 50, "stop": 32},
    "中国移动H": {"symbol": "hk00941", "market": "港股", "buy_ref": 82, "target": 110, "stop": 74},
    "腾讯": {"symbol": "hk00700", "market": "港股", "buy_ref": 450, "target": 600, "stop": 400},
    "ZTO": {"symbol": "usZTO", "market": "美股", "buy_ref": 23, "target": 32, "stop": 20},
    "英伟达": {"symbol": "usNVDA", "market": "美股", "buy_ref": 200, "target": 280, "stop": 170},
    "工商银行": {"symbol": "sh601398", "market": "A股", "buy_ref": 7.0, "target": 9, "stop": 6.2},
    "赛力斯": {"symbol": "sh601127", "market": "A股", "buy_ref": 82, "target": 115, "stop": 69},
    "伯克希尔B": {"symbol": "usBRK.B", "market": "美股", "buy_ref": 480.90, "target": 600, "stop": 390},
}


def ensure_dir():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    WIKI_DIR.mkdir(parents=True, exist_ok=True)


def load():
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    return {"decisions": [], "next_id": 1}


def save(data):
    LOG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def next_id(data):
    nid = data["next_id"]
    data["next_id"] += 1
    return f"D{datetime.now().strftime('%Y%m%d')}_{nid:03d}"


def record_decision(
    name: str,
    action: str,  # buy | sell | hold | adjust_target | adjust_stop
    price: float,
    reason: str,
    seven_star: Optional[dict] = None,
    four_ring: Optional[int] = None,
    target: Optional[float] = None,
    stop: Optional[float] = None,
):
    """记录一条决策"""
    data = load()
    hid = HOLDINGS.get(name, {})
    entry = {
        "id": next_id(data),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "name": name,
        "symbol": hid.get("symbol", ""),
        "market": hid.get("market", ""),
        "action": action,
        "price": price,
        "target": target or hid.get("target"),
        "stop": stop or hid.get("stop"),
        "reason": reason,
        "七星评分": seven_star,
        "四环评分": four_ring,
        "outcome": {
            "status": "pending",
            "check_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            "result": None,
            "delta_pct": None,
            "note": None,
        },
    }
    data["decisions"].append(entry)
    save(data)

    # 同时写入 Wiki (人可读)
    wiki_path = WIKI_DIR / f"{entry['id']}.md"
    lines = [
        f"---",
        f"title: 决策记录 {entry['id']}",
        f"date: {entry['date']}",
        f"type: decision",
        f"tags: [decision, {action}, {name}]",
        f"---",
        f"",
        f"# 决策 {entry['id']}：{name}",
        f"",
        f"| 字段 | 值 |",
        f"|------|------|",
        f"| 日期 | {entry['date']} |",
        f"| 操作 | {action} |",
        f"| 价格 | {price} |",
        f"| 原因 | {reason} |",
        f"| 目标 | {target or hid.get('target', '—')} |",
        f"| 止损 | {stop or hid.get('stop', '—')} |",
    ]
    if seven_star:
        lines.append(f"| 七星评分 | {json.dumps(seven_star, ensure_ascii=False)} |")
    if four_ring is not None:
        lines.append(f"| 四环评分 | {four_ring} |")
    lines.append(f"")
    lines.append(f"## 复盘结果")
    lines.append(f"")
    lines.append(f"待复盘日期：{entry['outcome']['check_date']}")
    lines.append(f"状态：⏳ 待复盘")
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"✅ 已记录决策 {entry['id']}：{action} {name} @ {price}")
    print(f"   Wiki: {wiki_path}")
    return entry


def check_pending():
    """检查所有待复盘决策"""
    data = load()
    pending = [d for d in data["decisions"] if d["outcome"]["status"] == "pending"]
    due = [d for d in pending if d["outcome"]["check_date"] <= datetime.now().strftime("%Y-%m-%d")]

    if not pending:
        print("✅ 没有待复盘决策")
        return
    if not due:
        print(f"⏳ {len(pending)} 条待处理，最早到期：{pending[0]['outcome']['check_date']}")
        return

    print(f"📋 {len(due)} 条决策到期需复盘：")
    for d in due:
        print(f"   {d['id']} | {d['name']} | {d['action']} @ {d['price']} | 到期 {d['outcome']['check_date']}")


def report():
    """生成统计报告"""
    data = load()
    ds = data["decisions"]
    if not ds:
        print("暂无决策记录")
        return

    total = len(ds)
    by_action = {}
    by_outcome = {"pending": 0, "correct": 0, "wrong": 0, "partial": 0}
    for d in ds:
        by_action[d["action"]] = by_action.get(d["action"], 0) + 1
        s = d["outcome"]["status"]
        by_outcome[s] = by_outcome.get(s, 0) + 1

    print(f"📊 决策记录统计")
    print(f"━━━━━━━━━━━━━━━━━")
    print(f"总决策数：{total}")
    print(f"")
    print(f"按操作类型：")
    for a, c in sorted(by_action.items(), key=lambda x: -x[1]):
        print(f"  {a}: {c} 次")
    print(f"")
    print(f"按结果：")
    print(f"  ✅ 正确：{by_outcome['correct']}")
    print(f"  ❌ 错误：{by_outcome['wrong']}")
    print(f"  ⚠️ 部分正确：{by_outcome['partial']}")
    print(f"  ⏳ 待复盘：{by_outcome['pending']}")

    if by_outcome["correct"] + by_outcome["wrong"] > 0:
        total_closed = by_outcome["correct"] + by_outcome["wrong"]
        win_rate = by_outcome["correct"] / total_closed * 100
        print(f"")
        print(f"胜率：{win_rate:.1f}% ({by_outcome['correct']}/{total_closed})")


def summary():
    """一句话总结（给微信推送用）"""
    data = load()
    ds = data["decisions"]
    total = len(ds)
    pending = sum(1 for d in ds if d["outcome"]["status"] == "pending")
    correct = sum(1 for d in ds if d["outcome"]["status"] == "correct")
    wrong = sum(1 for d in ds if d["outcome"]["status"] == "wrong")
    print(f"📊 {total}条决策 | ✅{correct} ❌{wrong} ⏳{pending}待复盘")
    if correct + wrong > 0:
        print(f"胜率 {correct/(correct+wrong)*100:.0f}%")


if __name__ == "__main__":
    ensure_dir()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "record":
        if "--json" in sys.argv:
            idx = sys.argv.index("--json") + 1
            jd = json.loads(sys.argv[idx]) if idx < len(sys.argv) else {}
            record_decision(
                name=jd.get("name", "未知"),
                action=jd.get("action", "hold"),
                price=jd.get("price", 0),
                reason=jd.get("reason", ""),
                seven_star=jd.get("七星评分"),
                four_ring=jd.get("四环评分"),
                target=jd.get("target"),
                stop=jd.get("stop"),
            )
        else:
            print("交互式录入：")
            name = input("股票名称: ")
            action = input("操作 (buy/sell/hold): ")
            price = float(input("价格: "))
            reason = input("原因: ")
            record_decision(name=name, action=action, price=price, reason=reason)

    elif cmd == "check":
        check_pending()

    elif cmd == "report":
        report()

    elif cmd == "summary":
        summary()

    else:
        print(f"未知命令: {cmd}")
        print(__doc__)