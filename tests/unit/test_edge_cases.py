"""补充测试 — 覆盖低覆盖率模块的关键分支。"""
import pytest
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core import (
    Observation, ObservationSource,
    Evidence, EvidenceType, NoveltyLevel, HorizonType,
    Belief, BeliefStatus,
    Prediction, PredictionStatus, HorizonLabel, Scenario,
    Outcome, ErrorType,
    Learning, LearningType,
)
from memory import (
    ObservationStore, EvidenceStore, BeliefStore,
    PredictionStore, OutcomeStore, LearningStore,
    CausalGraph, CausalGraphStore,
    reset_all_stores,
)
from engines import (
    ObservationEngine, EvidenceEngine, BeliefEngine,
    PredictionEngine, LearningEngine, DecisionEngine,
    ConfidenceEngine, GapEngine, CounterfactualEngine,
    FeatureLearningEngine, WeightLearningEngine, WorldModelEngine,
)
from workflow import PredictionPipeline, EnhancedLearningPipeline, LearningPipeline


@pytest.fixture(autouse=True)
def _reset():
    reset_all_stores()


@pytest.fixture
def memory_db(tmp_path):
    return str(tmp_path / "test.db")


# ===== Workflow Pipeline Tests =====

class TestWorkflowPipelines:
    def test_45_enhanced_learning_pipeline(self, memory_db):
        pred = Prediction(id="p1", target="test", belief_id="b1",
            confidence=0.8, expected_value=1.1,
            probability_distribution={}, scenarios=[])
        belief = Belief(id="b1", subject="test", probability=0.7, confidence=0.8, version=1)
        outcome = Outcome(id="o1", prediction_id="p1", actual_value=0.95,
            actual_result="略低于预期", prediction_error=0.15,
            error_type=ErrorType.OVERCONFIDENCE)
        pipeline = EnhancedLearningPipeline(memory_db)
        result = pipeline.run(outcome, pred, belief)
        assert result["status"] == "success"
        assert result["learning"] is not None
        assert result["belief_adjustment"] < 0

    def test_46_learning_pipeline(self, memory_db):
        pred = Prediction(id="p2", target="test", belief_id="b2",
            confidence=0.7, expected_value=1.0,
            probability_distribution={}, scenarios=[])
        belief = Belief(id="b2", subject="test", probability=0.6, confidence=0.7, version=1)
        outcome = Outcome(id="o2", prediction_id="p2", actual_value=1.0,
            actual_result="符合预期", prediction_error=0.01,
            error_type=ErrorType.NO_ERROR)
        pipeline = LearningPipeline(memory_db)
        result = pipeline.run(outcome, pred, belief)
        assert result["status"] == "success"
        assert result["learning"] is not None

    def test_47_prediction_pipeline_partial(self, memory_db):
        pipeline = PredictionPipeline(memory_db)
        result = pipeline.run(sources=[], subject="test", horizon_days=90)
        assert "status" in result

    def test_48_prediction_pipeline_with_sources(self, memory_db):
        pipeline = PredictionPipeline(memory_db)
        result = pipeline.run(
            sources=[{"source": ObservationSource.NEWS,
                       "raw_content": "赛力斯发布新车型，月销破万。",
                       "title": "赛力斯新车发布", "timestamp": datetime.now()}],
            subject="赛力斯股价", horizon_days=5)
        assert "belief" in result
        assert "evidence_list" in result


# ===== Engine Edge Cases =====

class TestEngineEdgeCases:
    def test_49_decision_engine_run(self, memory_db):
        pred = Prediction(
            id="dp1", target="test", belief_id="b1",
            probability_distribution={"基准": 0.6, "乐观": 0.25, "悲观": 0.15},
            scenarios=[
                Scenario(name="基准", probability=0.6, target_value=1.0),
                Scenario(name="乐观", probability=0.25, target_value=1.15),
                Scenario(name="悲观", probability=0.15, target_value=0.85),
            ],
            confidence=0.75, horizon_days=90, horizon_label=HorizonLabel.D90,
            expected_value=1.05, expected_return=0.05,
            bound_evidence_ids=["e1"], status=PredictionStatus.ACTIVE)
        engine = DecisionEngine("test")
        result = engine.run({"prediction": pred})
        decision = result["decision"]
        assert decision is not None
        assert decision.signal in ("买入", "强烈买入", "持有", "卖出", "强烈卖出")
        assert 0 <= decision.kelly_fraction <= 0.25

    def test_50_confidence_underconfident(self):
        engine = ConfidenceEngine()
        engine.calibration_cache["t"] = [
            {"confidence": 0.3, "accuracy": 0.8},
            {"confidence": 0.25, "accuracy": 0.85},
            {"confidence": 0.35, "accuracy": 0.75},
        ]
        result = engine._calibrate([MagicMock(confidence=0.3)], [], "t")
        assert result["report"]["bias"] == "underconfident"

    def test_51_confidence_balanced(self):
        engine = ConfidenceEngine()
        engine.calibration_cache["t"] = [
            {"confidence": 0.7, "accuracy": 0.68},
            {"confidence": 0.75, "accuracy": 0.72},
            {"confidence": 0.65, "accuracy": 0.65},
        ]
        result = engine._calibrate([MagicMock(confidence=0.7)], [], "t")
        assert result["report"]["bias"] == "well_calibrated"

    def test_52_confidence_insufficient_data(self):
        engine = ConfidenceEngine()
        result = engine._calibrate([], [], "t")
        assert result["report"]["status"] == "insufficient_data"
        assert result["confidence"] == 0.5

    def test_53_weight_learning_compute_weights(self):
        engine = WeightLearningEngine()
        engine._init_dimensions()
        engine.accuracy_history["investment"]["growth"] = [0.8, 0.9, 0.7]
        engine.accuracy_history["investment"]["value"] = [0.4, 0.5, 0.3]
        updates = engine._compute_weights("investment")
        assert len(updates) == 8
        assert updates["growth"] >= updates["value"]

    def test_54_weight_learning_dimension_accuracy(self):
        engine = WeightLearningEngine()
        engine._init_dimensions()
        engine.accuracy_history["investment"]["growth"] = [0.8, 0.9]
        acc = engine._get_dimension_accuracy("investment")
        assert "growth" in acc
        assert acc["growth"] == 0.85

    def test_55_evidence_engine_llm_fallback(self, memory_db):
        mock_client = MagicMock()
        mock_client.return_value = {"error": "network timeout"}
        engine = EvidenceEngine(llm_client=mock_client)
        obs = Observation(id="obs1", source=ObservationSource.NEWS,
            raw_content="赛力斯推出新车型，月销破万。",
            title="新车发布", timestamp=datetime.now())
        ctx = {"observations": [obs], "use_llm": True}
        result = engine.run(ctx)
        assert "evidence_list" in result

    def test_56_observation_engine_wiki_ingestion(self, tmp_path):
        wiki_dir = str(tmp_path / "wiki")
        md_dir = Path(wiki_dir) / "raw" / "sources"
        md_dir.mkdir(parents=True)
        md_file = md_dir / "财报_赛力斯.md"
        md_file.write_text("---\ntitle: 赛力斯中报\n---\n赛力斯2026Q2毛利率28%。", encoding="utf-8")
        engine = ObservationEngine("test")
        ctx = {"sources": [], "wiki_dir": wiki_dir}
        result = engine.run(ctx)
        assert len(result["observations"]) >= 1

    def test_57_counterfactual_missing_signal(self):
        engine = CounterfactualEngine("test")
        pred = Prediction(id="p1", target="test", belief_id="b1",
            confidence=0.5, expected_value=1.0,
            scenarios=[], probability_distribution={})
        outcome = Outcome(id="o1", prediction_id="p1", actual_value=1.2,
            actual_result="超预期", prediction_error=0.2,
            error_type=ErrorType.MISSING_SIGNAL)
        result = engine.run({"prediction": pred, "outcome": outcome})
        cfs = result.get("counterfactuals", [])
        assert len(cfs) >= 1


# ===== Store Edge Cases =====

class TestStoreEdgeCases:
    def test_58_base_store_update(self, memory_db):
        store = ObservationStore.get(memory_db)
        obs = Observation(id="u1", source=ObservationSource.NEWS,
            raw_content="test content", title="update test", timestamp=datetime.now())
        store.insert(obs)
        obs.title = "updated title"
        store.update(obs)
        assert store.get_by_id("u1").title == "updated title"

    def test_59_base_store_delete(self, memory_db):
        store = ObservationStore.get(memory_db)
        store.insert(Observation(id="d1", source=ObservationSource.NEWS,
            raw_content="delete me", title="del", timestamp=datetime.now()))
        store.delete("d1")
        assert store.get_by_id("d1") is None

    def test_60_base_store_count(self, memory_db):
        store = ObservationStore.get(memory_db)
        for i in range(3):
            store.insert(Observation(id=f"c{i}", source=ObservationSource.NEWS,
                raw_content=f"count {i}", title="cnt", timestamp=datetime.now()))
        assert store.count() == 3

    def test_61_prediction_store_mark_realized(self, memory_db):
        belief_store = BeliefStore.get(memory_db)
        belief_store.insert(Belief(id="b_mr", subject="test", probability=0.5,
            confidence=0.5, version=1))
        pred_store = PredictionStore.get(memory_db)
        pred = Prediction(id="mr1", target="test", belief_id="b_mr",
            confidence=0.5, expected_value=1.0,
            probability_distribution={}, scenarios=[],
            status=PredictionStatus.ACTIVE)
        pred_store.insert(pred)
        pred_store.mark_realized("mr1")
        assert pred_store.get_by_id("mr1").status == PredictionStatus.REALIZED

    def test_62_prediction_store_list_due(self, memory_db):
        belief_store = BeliefStore.get(memory_db)
        belief_store.insert(Belief(id="b_ld", subject="test", probability=0.5,
            confidence=0.5, version=1))
        store = PredictionStore.get(memory_db)
        past = datetime.now() - timedelta(days=100)
        pred = Prediction(id="ld1", target="test", belief_id="b_ld",
            confidence=0.5, expected_value=1.0,
            probability_distribution={}, scenarios=[],
            created_at=past, status=PredictionStatus.ACTIVE)
        store.insert(pred)
        due = store.list_due()
        assert len(due) >= 1

    def test_63_observation_store_list_by_source(self, memory_db):
        store = ObservationStore.get(memory_db)
        store.insert(Observation(id="lbs1", source=ObservationSource.NEWS,
            raw_content="news", title="n", timestamp=datetime.now()))
        store.insert(Observation(id="lbs2", source=ObservationSource.FINANCIAL_REPORT,
            raw_content="report", title="r", timestamp=datetime.now()))
        news = store.list_by_source(ObservationSource.NEWS)
        assert len(news) >= 1
        assert all(o.source == ObservationSource.NEWS for o in news)

    def test_64_outcome_store_list_by_error_type(self, memory_db):
        # FK requires predictions table to exist first
        belief_store = BeliefStore.get(memory_db)
        belief_store.insert(Belief(id="b_ob", subject="test", probability=0.5,
            confidence=0.5, version=1))
        pred_store = PredictionStore.get(memory_db)
        pred_store.insert(Prediction(id="p_ob", target="test", belief_id="b_ob",
            confidence=0.5, expected_value=1.0,
            probability_distribution={}, scenarios=[]))
        store = OutcomeStore.get(memory_db)
        store.insert(Outcome(id="ob1", prediction_id="p_ob", actual_value=0.9,
            actual_result="test", prediction_error=0.1,
            error_type=ErrorType.OVERCONFIDENCE))
        results = store.list_by_error_type(ErrorType.OVERCONFIDENCE)
        assert len(results) >= 1
        assert all(r.error_type == ErrorType.OVERCONFIDENCE for r in results)

    def test_65_causal_graph_operations(self):
        g = CausalGraph()
        g.add_node("a", "belief", "A")
        g.add_node("b", "belief", "B")
        g.add_edge("a", "b", 0.8, "supports")
        g.add_edge("b", "a", 0.3, "weakly_supports")
        assert "a" in g.get_upstream("b")
        assert "b" in g.get_downstream("a")
        d = g.to_dict()
        g2 = CausalGraph.from_dict(d)
        assert len(g2.nodes) == 2
        assert len(g2.edges) == 2
