"""
Cognition-V4 全面测试套件 — 40条用例
覆盖: Entity / Engine / Store / Config / DataSource
"""
import pytest
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core import (
    Observation, ObservationSource,
    Evidence, EvidenceType, NoveltyLevel, HorizonType,
    Belief, BeliefStatus,
    Prediction, PredictionStatus, HorizonLabel, Scenario,
    Outcome, ErrorType,
    Learning, LearningType, CausalEdgeUpdate,
)
from memory import (
    ObservationStore, EvidenceStore, BeliefStore,
    PredictionStore, OutcomeStore, LearningStore, CausalGraph,
)
from engines import (
    ObservationEngine, EvidenceEngine, BeliefEngine,
    PredictionEngine, LearningEngine, DecisionEngine,
    ConfidenceEngine, GapEngine, CounterfactualEngine,
    FeatureLearningEngine, WeightLearningEngine, WorldModelEngine,
)
from config import (
    Domain, INVESTMENT_DIMENSIONS, LEARNING_RATE,
    WEIGHT_LEARNING_RATE, BELIEF_LEARNING_RATE,
    CONFIDENCE_DECAY_RATE, CONFIDENCE_HALFLIFE_DAYS,
    HORIZON_DAYS, HORIZON_THRESHOLDS, days_to_horizon_label,
    DECISION_THRESHOLDS, ENGINE_PIPELINE_ORDER,
)
from data_fetcher import DataFetcher, TENCENT_SYMBOLS, FINANCIAL_SIMULATED, THS_SYMBOLS


@pytest.fixture
def memory_db(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def sample_obs():
    return Observation(
        id="test-obs-001", source=ObservationSource.NEWS,
        raw_content="赛力斯2026Q2毛利率达到28，同比增长5个百分点。",
        title="赛力斯中报", timestamp=datetime.now(),
    )


@pytest.fixture
def sample_ev():
    return Evidence(
        id="test-ev-001", observation_ids=["test-obs-001"],
        content="毛利率 28", type=EvidenceType.QUANTITATIVE,
        confidence=0.8, novelty=NoveltyLevel.HIGH,
        horizon=HorizonType.MEDIUM, importance=0.9,
    )


@pytest.fixture
def sample_belief():
    return Belief(
        id="b1", subject="赛力斯毛利率", probability=0.7,
        confidence=0.8, version=1, metadata={"base_value": 0.28},
    )


# ===== Entity Layer =====

class TestEntityLayer:
    def test_01_id_deterministic(self):
        id1 = Observation.generate_id("news", "test", "2026-01-01")
        id2 = Observation.generate_id("news", "test", "2026-01-01")
        assert id1 == id2

    def test_02_different_params_different_id(self):
        assert Observation.generate_id("news", "test1") != Observation.generate_id("news", "test2")

    def test_03_serialization_datetime(self, sample_obs):
        d = sample_obs.__dict__
        assert isinstance(d["timestamp"], datetime)

    def test_04_fingerprint_consistency(self, sample_obs):
        assert sample_obs.fingerprint() == sample_obs.fingerprint()

    def test_05_belief_decay_formula(self):
        bel = Belief(id="b1", subject="test", probability=0.5,
                     confidence=1.0, decay_rate=CONFIDENCE_DECAY_RATE)
        decayed = bel.decay_confidence(10)
        expected = 1.0 * ((1 - CONFIDENCE_DECAY_RATE) ** 10)
        assert abs(decayed - expected) < 0.001

    def test_06_scenario_probability_sum(self):
        sc = [Scenario(name="基准", probability=0.60),
              Scenario(name="乐观", probability=0.25),
              Scenario(name="悲观", probability=0.15)]
        assert abs(sum(s.probability for s in sc) - 1.0) < 0.001

    def test_07_outcome_no_error(self):
        o = Outcome(id="o1", prediction_id="p1", actual_value=0.28,
                    actual_result="毛利率28", prediction_error=0.001,
                    error_type=ErrorType.NO_ERROR)
        assert o.error_type == ErrorType.NO_ERROR

    def test_08_learning_id_generation(self):
        lid = Learning.generate_id("outcome-1", "pred-1")
        assert len(lid) == 16

    def test_09_evidence_fingerprint_changes(self, sample_ev):
        fp1 = sample_ev.fingerprint()
        sample_ev.content = "修改内容"
        assert sample_ev.fingerprint() != fp1

    def test_10_belief_version_chain(self):
        b1 = Belief(id="b1", subject="test", probability=0.5,
                    confidence=0.5, version=1)
        b2 = Belief(id="b2", subject="test", probability=0.6,
                    confidence=0.55, version=2, previous_version_id="b1")
        assert b2.previous_version_id == "b1"
        assert b2.version == b1.version + 1

    def test_11_error_type_reasonable_exists(self):
        """ErrorType.REASONABLE 必须存在于枚举中（auto_learn.py 使用）。"""
        assert hasattr(ErrorType, "REASONABLE")
        assert ErrorType.REASONABLE.value == "reasonable"

    def test_12_belief_no_evidence_no_change(self):
        """无证据时贝叶斯更新应保持概率不变。"""
        old = Belief(id="old", subject="test", probability=0.7,
                     confidence=0.8, version=1)
        engine = BeliefEngine("test")
        result = engine.run({"evidence": [], "subject": "test",
                             "existing_belief": old})
        assert abs(result["belief"].probability - old.probability) < 0.001


# ===== Engine Layer =====

class TestEngineLayer:
    def test_13_bayesian_update_with_support(self, sample_ev):
        old = Belief(id="old", subject="test", probability=0.5,
                     confidence=0.6, version=1)
        engine = BeliefEngine("test")
        result = engine.run({"evidence": [sample_ev], "subject": "test",
                             "existing_belief": old})
        assert result["belief"].probability > old.probability
        assert result["belief"].version == 2

    def test_14_kelly_positive(self):
        """Kelly公式: 正期望时应返回正仓位。"""
        engine = DecisionEngine("test")
        f = engine._kelly_fraction(win_rate=0.6, expected_return_pct=10.0)
        assert f > 0
        assert f <= 0.25  # 上限

    def test_15_kelly_negative(self):
        """Kelly公式: 负期望时应返回零仓位。"""
        engine = DecisionEngine("test")
        f = engine._kelly_fraction(win_rate=0.3, expected_return_pct=-5.0)
        assert f == 0.0

    def test_16_decision_strong_buy(self):
        engine = DecisionEngine("test")
        pred = type("", (), {"confidence": 0.8, "scenarios": [],
                             "expected_value": 1.1, "bound_evidence_ids": []})()
        assert engine._derive_signal(pred) == "强烈买入"

    def test_17_decision_sell(self):
        engine = DecisionEngine("test")
        pred = type("", (), {"confidence": 0.2, "scenarios": [],
                             "expected_value": 1.0, "bound_evidence_ids": []})()
        assert engine._derive_signal(pred) == "强烈卖出"

    def test_18_prediction_three_scenarios(self, sample_belief):
        engine = PredictionEngine("test")
        result = engine.run({"belief": sample_belief, "bound_evidence": [],
                             "horizon_days": 90, "target": "test",
                             "calibrated_accuracy": 0.7})
        pred = result["prediction"]
        assert pred is not None
        assert len(pred.scenarios) == 3
        names = {s.name for s in pred.scenarios}
        assert names == {"基准", "乐观", "悲观"}

    def test_19_confidence_overconfident(self):
        engine = ConfidenceEngine()
        engine.calibration_cache["t"] = [
            {"confidence": 0.9, "accuracy": 0.3},
            {"confidence": 0.85, "accuracy": 0.25},
            {"confidence": 0.95, "accuracy": 0.2},
        ]
        result = engine._calibrate([MagicMock(confidence=0.9)], [], "t")
        assert result["report"]["bias"] == "overconfident"

    def test_20_gap_missing_evidence(self):
        low = Belief(id="low", subject="test", probability=0.5,
                     confidence=0.3, version=1,
                     support_evidence_ids=[])
        engine = GapEngine("test")
        result = engine.run({"beliefs": [low]})
        gaps = result.get("gaps", [])
        assert len(gaps) >= 1
        assert any(g.gap_type.value in ("missing_evidence", "low_confidence") for g in gaps)

    def test_21_counterfactual_high_error(self):
        engine = CounterfactualEngine("test")
        pred = Prediction(id="p1", target="test", belief_id="b1",
                          confidence=0.9, expected_value=1.1,
                          scenarios=[], probability_distribution={})
        outcome = Outcome(id="o1", prediction_id="p1", actual_value=0.8,
                          actual_result="大跌", prediction_error=0.3,
                          error_type=ErrorType.OVERCONFIDENCE)
        result = engine.run({"prediction": pred, "outcome": outcome})
        assert len(result.get("counterfactuals", [])) >= 1

    def test_22_learning_type_classification(self):
        engine = LearningEngine("test")
        assert engine._classify_learning_type("missing_signal", 0.1) == LearningType.FEATURE
        assert engine._classify_learning_type("regime_mismatch", 0.1) == LearningType.REGIME
        assert engine._classify_learning_type("overconfidence", 0.1) == LearningType.BELIEF

    def test_23_weight_learning_init(self):
        engine = WeightLearningEngine()
        engine._init_dimensions()
        assert len(engine.accuracy_history.get("investment", {})) == 8

    def test_24_world_model_macro_regime(self):
        """World Model: 高置信度信念应触发AI牛市宏观判断。"""
        engine = WorldModelEngine("test")
        ev = Evidence(id="e1", observation_ids=[], content="利好",
                      type=EvidenceType.QUANTITATIVE, confidence=0.9,
                      novelty=NoveltyLevel.HIGH, horizon=HorizonType.LONG,
                      importance=0.9)
        belief = Belief(id="b1", subject="test", probability=0.8,
                        confidence=0.9, version=1, domain="investment")
        result = engine.run({"evidence": [ev], "beliefs": [belief],
                             "subject": "test"})
        world_view = result.get("world_view", {})
        regime = world_view.get("regime", "")
        assert regime == "AI牛市"

    def test_25_feature_learning_empty(self):
        """特征学习: 空特征列表应返回空排名。"""
        engine = FeatureLearningEngine("test")
        result = engine.run({"features": [], "domain": "investment"})
        ranking = result.get("feature_ranking", [])
        assert ranking == []


# ===== Store Layer =====

class TestStoreLayer:
    def test_25_obs_crud(self, memory_db, sample_obs):
        store = ObservationStore.get(memory_db)
        store.insert(sample_obs)
        r = store.get_by_id("test-obs-001")
        assert r is not None
        assert r.title == "赛力斯中报"

    def test_26_belief_archive(self, memory_db):
        store = BeliefStore.get(memory_db)
        store.insert(Belief(id="b1", subject="test", probability=0.5,
                            confidence=0.5, version=1))
        store.archive_previous("b1")
        assert len(store.get_active("test")) == 0

    def test_27_evidence_by_domain(self, memory_db, sample_ev):
        store = EvidenceStore.get(memory_db)
        store.insert(sample_ev)
        results = store.list_by_domain("investment")
        assert len(results) >= 1

    def test_28_prediction_indexes(self, memory_db):
        store = PredictionStore.get(memory_db)
        conn = store._connect()
        idxs = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='predictions'"
        ).fetchall()
        conn.close()
        names = {r[0] for r in idxs}
        assert "idx_pred_belief" in names
        assert "idx_pred_status" in names
        assert "idx_pred_target" in names

    def test_29_outcome_fk(self, memory_db):
        store = OutcomeStore.get(memory_db)
        conn = store._connect()
        fks = conn.execute("PRAGMA foreign_key_list(outcomes)").fetchall()
        conn.close()
        assert any(col[2] == "predictions" for col in fks)

    def test_30_learning_by_type(self, memory_db):
        store = LearningStore.get(memory_db)
        store.insert(Learning(id="l1", outcome_id="o1", prediction_id="p1",
                              belief_id="b1", learning_type=LearningType.WEIGHT))
        results = store.list_by_type(LearningType.WEIGHT)
        assert len(results) >= 1

    def test_31_foreign_keys_enabled(self, memory_db):
        """外键约束应被启用。"""
        store = ObservationStore.get(memory_db)
        conn = store._connect()
        fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        conn.close()
        assert fk_status == 1

    def test_32_observation_store_timestamp_index(self, memory_db):
        """observations 表应有 timestamp 索引。"""
        store = ObservationStore.get(memory_db)
        conn = store._connect()
        idxs = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='observations'"
        ).fetchall()
        conn.close()
        names = {r[0] for r in idxs}
        assert "idx_obs_timestamp" in names

    def test_33_belief_store_active_query(self, memory_db):
        """BeliefStore.get_active 应只返回 active 状态的信念。"""
        store = BeliefStore(memory_db)  # Fresh instance, bypass singleton
        store.insert(Belief(id="b1", subject="test", probability=0.5,
                            confidence=0.5, version=1,
                            status=BeliefStatus.ACTIVE))
        store.insert(Belief(id="b2", subject="test", probability=0.6,
                            confidence=0.6, version=2,
                            status=BeliefStatus.ARCHIVED))
        active = store.get_active("test")
        assert len(active) == 1
        assert active[0].id == "b1"

    def test_34_evidence_store_pagination(self, memory_db, sample_ev):
        """EvidenceStore.list_by_domain 应支持 limit。"""
        store = EvidenceStore.get(memory_db)
        for i in range(5):
            ev = Evidence(
                id=f"ev-{i}", observation_ids=[],
                content=f"content {i}", type=EvidenceType.QUALITATIVE,
                confidence=0.5, novelty=NoveltyLevel.MEDIUM,
                horizon=HorizonType.SHORT, importance=0.5,
            )
            store.insert(ev)
        results = store.list_by_domain("investment", limit=3)
        assert len(results) <= 3


# ===== Config & Data Source =====

class TestConfigAndDataSource:
    def test_35_dimensions_sum_one(self):
        total = sum(d["weight"] for d in INVESTMENT_DIMENSIONS.values())
        assert abs(total - 1.0) < 0.001

    def test_36_horizon_mapping(self):
        assert HORIZON_DAYS[HorizonLabel.D5] == 5
        assert HORIZON_DAYS[HorizonLabel.D90] == 90
        assert HORIZON_DAYS[HorizonLabel.Y1] == 365

    def test_37_days_to_label(self):
        assert days_to_horizon_label(3) == HorizonLabel.D5
        assert days_to_horizon_label(10) == HorizonLabel.D20
        assert days_to_horizon_label(50) == HorizonLabel.D90
        assert days_to_horizon_label(100) == HorizonLabel.D180
        # 400 > 365 but <= 1095, should be Y3 (not Y1)
        assert days_to_horizon_label(400) == HorizonLabel.Y3
        assert days_to_horizon_label(1200) == HorizonLabel.Y3

    def test_38_thresholds_ordered(self):
        assert DECISION_THRESHOLDS["strong_buy"] > DECISION_THRESHOLDS["buy"]
        assert DECISION_THRESHOLDS["buy"] > DECISION_THRESHOLDS["hold"]
        assert DECISION_THRESHOLDS["hold"] > DECISION_THRESHOLDS["sell"]

    def test_39_fetcher_simulated(self):
        fetcher = DataFetcher(sources=["simulated"])
        r = fetcher.fetch("赛力斯毛利率")
        assert r is not None
        assert "expected" in r
        assert "actual" in r

    def test_40_tencent_coverage(self):
        # 股价指标走腾讯财经（至少6只）
        assert len(TENCENT_SYMBOLS) >= 6
        assert TENCENT_SYMBOLS["赛力斯股价"]["type"] == "stock_price"
        # 财报指标走 akshare（招行/工行）
        assert "招行净息差" in THS_SYMBOLS
        assert "工行不良贷款率" in THS_SYMBOLS
        # 数据源优先级
        fetcher = DataFetcher()
        assert "akshare" in fetcher.sources

    def test_41_simulated_has_errors(self):
        for subj, data in FINANCIAL_SIMULATED.items():
            assert "error_type" in data
            assert "expected" in data
            assert "actual" in data

    def test_42_pipeline_order(self):
        assert ENGINE_PIPELINE_ORDER[0].value == "observation_engine"
        assert ENGINE_PIPELINE_ORDER[1].value == "evidence_engine"

    def test_43_domain_enum(self):
        assert Domain.INVESTMENT.value == "investment"
        assert Domain.MACRO.value == "macro"
        assert Domain.POLICY.value == "policy"

    def test_44_learning_rates(self):
        assert 0 < LEARNING_RATE < 1
        assert 0 < WEIGHT_LEARNING_RATE < LEARNING_RATE
        assert 0 < BELIEF_LEARNING_RATE < 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
