"""V3.2 → V4.0 数据迁移脚本

用法：
    python migrate_from_v3.py [--dry-run]
    python migrate_from_v3.py

V3.2 源数据库: cognition/cognition.db
V4.0 目标数据库: cognition_v4.db
"""
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HERMES_DIR = Path(__file__).parent.parent.parent
V3_DB = HERMES_DIR / "cognition" / "cognition.db"
V4_DB = HERMES_DIR / "cognition-v4" / "cognition_v4.db"


def migrate_observations(v3_conn: sqlite3.Connection, pipeline) -> int:
    """迁移 observations。"""
    rows = v3_conn.execute(
        "SELECT id, raw_content, source_type, source_url, source_time, parsed_content, metadata, created_at FROM observations"
    ).fetchall()
    migrated = 0
    from core import Observation, ObservationSource
    for row in rows:
        try:
            source_str = row[2] or "other"
            source_map = {
                "news": "news", "announcement": "announcement",
                "financial_report": "financial_report", "research_report": "research_report",
                "policy": "policy", "website": "website",
            }
            obs = Observation(
                id=row[0],
                source=ObservationSource(source_map.get(source_str, "other")),
                url=row[3],
                raw_content=row[6] or row[1] or "",
                title=None,
                timestamp=datetime.fromisoformat(row[4]) if row[4] else datetime.now(),
                metadata={} if not row[6] else {},
                created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
            )
            pipeline.obs_store.insert(obs)
            migrated += 1
        except Exception as e:
            print(f"  ⚠️ Observation {row[0]} 失败: {e}")
    return migrated


def migrate_evidence(v3_conn: sqlite3.Connection, pipeline) -> int:
    """迁移 evidence。"""
    rows = v3_conn.execute(
        "SELECT id, content, observation_id, evidence_type, confidence, parsed_data, entity_names, created_at FROM evidence"
    ).fetchall()
    migrated = 0
    from core import Evidence, EvidenceType, NoveltyLevel, HorizonType
    TYPE_MAP = {
        "quantitative": EvidenceType.QUANTITATIVE,
        "qualitative": EvidenceType.QUALITATIVE,
        "categorical": EvidenceType.CATEGORICAL,
        "financial_performance": EvidenceType.QUANTITATIVE,
        "financial_data": EvidenceType.QUANTITATIVE,
        "operational_expense": EvidenceType.QUANTITATIVE,
        "sales_volume": EvidenceType.QUANTITATIVE,
        "financial_metric": EvidenceType.QUANTITATIVE,
        "financial_forecast": EvidenceType.QUANTITATIVE,
        "product_launch": EvidenceType.QUALITATIVE,
        "business_metric": EvidenceType.QUANTITATIVE,
        "company_profile": EvidenceType.QUALITATIVE,
        "trend": EvidenceType.QUALITATIVE,
        "policy": EvidenceType.QUALITATIVE,
        "general": EvidenceType.QUALITATIVE,
    }
    for row in rows:
        try:
            ev_type_str = row[3].lower() if row[3] else ""
            ev_type = TYPE_MAP.get(ev_type_str, EvidenceType.QUALITATIVE)
            ev = Evidence(
                id=row[0],
                observation_ids=[row[2]] if row[2] else [],
                content=row[1] or "",
                type=ev_type,
                confidence=float(row[4]) if row[4] else 0.5,
                novelty=NoveltyLevel("medium"),
                horizon=HorizonType("medium"),
                importance=0.5,
                domain="investment",
                created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
            )
            pipeline.ev_store.insert(ev)
            migrated += 1
        except Exception as e:
            print(f"  ⚠️ Evidence {row[0]} 失败: {e}")
    return migrated


def migrate_beliefs(v3_conn: sqlite3.Connection, pipeline) -> int:
    """迁移 beliefs。"""
    rows = v3_conn.execute(
        """SELECT id, content, predicate, entity_name, domain, confidence,
                  confidence_decay, supporting_evidence_ids, contradicting_evidence_ids,
                  previous_version_id, status, created_at, updated_at, version
           FROM beliefs WHERE status='active' OR status='inactive'"""
    ).fetchall()
    migrated = 0
    from core import Belief, BeliefStatus
    import json
    for row in rows:
        try:
            bel = Belief(
                id=row[0],
                subject=row[2] or row[1] or row[3] or "unknown",
                probability=0.5,  # V3 没有 probability
                confidence=float(row[5]) if row[5] else 0.5,
                support_evidence_ids=json.loads(row[7]) if row[7] else [],
                contradict_evidence_ids=json.loads(row[8]) if row[8] else [],
                update_time=datetime.fromisoformat(row[12]) if row[12] else datetime.now(),
                decay_rate=float(row[6]) if row[6] else 0.01,
                version=int(row[13]) if row[13] else 1,
                status=BeliefStatus(row[10]) if row[10] else BeliefStatus.ACTIVE,
                previous_version_id=row[9],
                domain=row[4] or "investment",
                created_at=datetime.fromisoformat(row[11]) if row[11] else datetime.now(),
            )
            pipeline.belief_store.insert(bel)
            migrated += 1
        except Exception as e:
            print(f"  ⚠️ Belief {row[0]} 失败: {e}")
    return migrated


def migrate_predictions(v3_conn: sqlite3.Connection, pipeline) -> int:
    """迁移 predictions。"""
    rows = v3_conn.execute(
        """SELECT id, entity_name, metric, target_value, confidence,
                  horizon_days, horizon_label, catalyst, regime,
                  effective_score, belief_ids, created_at
           FROM predictions"""
    ).fetchall()
    migrated = 0
    from core import Prediction, PredictionStatus, HorizonLabel as VH, Scenario
    for row in rows:
        try:
            # 转换 horizon_label
            horizon_label = VH.D90
            if row[6]:
                label_map = {"5d": VH.D5, "20d": VH.D20, "90d": VH.D90,
                             "180d": VH.D180, "1y": VH.Y1, "3y": VH.Y3}
                horizon_label = label_map.get(row[6], VH.D90)

            target = f"{row[1] or ''} {row[2] or ''} {row[3] or ''}".strip()
            belief_id = ""
            try:
                import json
                belief_ids = json.loads(row[10]) if row[10] else []
                belief_id = belief_ids[0] if belief_ids else ""
            except Exception:
                belief_id = ""

            pred = Prediction(
                id=row[0],
                target=target or "unknown",
                belief_id=belief_id,
                probability_distribution={"基准": 0.6, "乐观": 0.25, "悲观": 0.15},
                scenarios=[
                    Scenario(name="基准", probability=0.6, target_value=float(row[3]) if row[3] else None),
                    Scenario(name="乐观", probability=0.25, target_value=float(row[3]) * 1.15 if row[3] else None),
                    Scenario(name="悲观", probability=0.15, target_value=float(row[3]) * 0.85 if row[3] else None),
                ],
                expected_value=float(row[3]) if row[3] else None,
                confidence=float(row[4]) if row[4] else 0.5,
                horizon_days=int(row[5]) if row[5] else 90,
                horizon_label=horizon_label,
                catalyst=row[7],
                regime=row[8] or "neutral",
                effective_score=float(row[9]) if row[9] else 0.5,
                created_at=datetime.fromisoformat(row[11]) if row[11] else datetime.now(),
                status=PredictionStatus.ACTIVE,
            )
            pipeline.pred_store.insert(pred)
            migrated += 1
        except Exception as e:
            print(f"  ⚠️ Prediction {row[0]} 失败: {e}")
    return migrated


def main():
    parser = argparse.ArgumentParser(description="V3.2 → V4.0 数据迁移")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not V3_DB.exists():
        print(f"❌ V3 DB 不存在: {V3_DB}")
        sys.exit(1)

    print(f"源: {V3_DB}")
    print(f"目标: {V4_DB}")

    v3_conn = sqlite3.connect(str(V3_DB))

    if args.dry_run:
        for tbl in ["observations", "evidence", "beliefs", "predictions"]:
            n = v3_conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"  {tbl}: {n} 条")
        v3_conn.close()
        return

    sys.path.insert(0, str(HERMES_DIR / "cognition-v4"))
    from workflow import PredictionPipeline

    pipeline = PredictionPipeline(str(V4_DB))

    print("\n开始迁移...")
    n_obs = migrate_observations(v3_conn, pipeline)
    print(f"  ✅ Observations: {n_obs}")

    n_ev = migrate_evidence(v3_conn, pipeline)
    print(f"  ✅ Evidence: {n_ev}")

    n_bel = migrate_beliefs(v3_conn, pipeline)
    print(f"  ✅ Beliefs: {n_bel}")

    n_pred = migrate_predictions(v3_conn, pipeline)
    print(f"  ✅ Predictions: {n_pred}")

    v3_conn.close()
    print(f"\n✅ 迁移完成！V4 DB: {V4_DB}")


if __name__ == "__main__":
    main()
