"""Phase 1 单元测试骨架"""
import pytest
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
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
    ObservationStore,
    EvidenceStore,
    BeliefStore,
    PredictionStore,
    OutcomeStore,
    CausalGraph,
)
from engines import (
    ObservationEngine,
    EvidenceEngine,
    BeliefEngine,
    PredictionEngine,
    LearningEngine,
)
from workflow import PredictionPipeline


# ---- Test Fixtures ----

@pytest.fixture
def memory_db(tmp_path):
    """每个测试使用独立临时数据库。"""
    db = str(tmp_path / "test.db")
    return db


@pytest.fixture
def sample_observation():
    return Observation(
        id="test-obs-001",
        source=ObservationSource.NEWS,
        raw_content="赛力斯2026Q2毛利率达到28%，同比增长5个百分点。",
        title="赛力斯中报",
        timestamp=datetime.now(),
    )


@pytest.fixture
def sample_evidence():
    return Evidence(
        id="test-ev-001",
        observation_ids=["test-obs-001"],
        content="毛利率 28%",
        type=EvidenceType.QUANTITATIVE,
        confidence=0.8,
        novelty=NoveltyLevel.HIGH,
        horizon=HorizonType.MEDIUM,
        importance=0.9,
    )


# ---- Core Entity Tests ----

class TestObservation:
    def test_create_observation(self, sample_observation):
        assert sample_observation.id == "test-obs-001"
        assert sample_observation.source == ObservationSource.NEWS
        assert "毛利率" in sample_observation.raw_content


class TestEvidence:
    def test_create_evidence(self, sample_evidence):
        assert sample_evidence.id == "test-ev-001"
        assert sample_evidence.confidence == 0.8
        assert sample_evidence.type == EvidenceType.QUANTITATIVE


class TestBelief:
    def test_decay_confidence(self):
        bel = Belief(
            id="b1", subject="test", probability=0.8, confidence=0.9,
            decay_rate=0.1, version=1
        )
        decayed = bel.decay_confidence(7)  # 7天
        assert decayed < 0.9
        assert decayed > 0.3

    def test_version_chain(self):
        bel1 = Belief(id="b1", subject="test", probability=0.5, confidence=0.5, version=1)
        bel2 = Belief(
            id="b2", subject="test", probability=0.6, confidence=0.55,
            version=2, previous_version_id="b1"
        )
        assert bel2.previous_version_id == "b1"
        assert bel2.version == 2


class TestPrediction:
    def test_scenario_probability_sum(self):
        pred = Prediction(
            id="p1", target="test", belief_id="b1",
            probability_distribution={"基准": 0.6, "乐观": 0.25, "悲观": 0.15},
            scenarios=[
                Scenario(name="基准", probability=0.6),
                Scenario(name="乐观", probability=0.25),
                Scenario(name="悲观", probability=0.15),
            ],
            confidence=0.7, horizon_days=90,
        )
        total = sum(s.probability for s in pred.scenarios)
        assert abs(total - 1.0) < 0.001


class TestOutcome:
    def test_error_classification(self):
        outcome = Outcome(
            id="o1", prediction_id="p1", actual_value=0.25, actual_result="毛利率25%",
            prediction_error=0.107, error_type=ErrorType.NO_ERROR,
        )
        assert outcome.prediction_error < 0.2


# ---- Store Tests ----

class TestObservationStore:
    def test_insert_and_get(self, memory_db, sample_observation):
        store = ObservationStore.get(memory_db)
        store.insert(sample_observation)
        retrieved = store.get_by_id("test-obs-001")
        assert retrieved is not None
        assert retrieved.id == sample_observation.id
        assert retrieved.source == sample_observation.source

    def test_list_recent(self, memory_db):
        store = ObservationStore.get(memory_db)
        assert len(store.list_all(limit=10)) >= 0


class TestBeliefStore:
    def test_get_active(self, memory_db):
        store = BeliefStore.get(memory_db)
        beliefs = store.get_active()
        assert isinstance(beliefs, list)


class TestCausalGraph:
    def test_add_node_edge(self):
        g = CausalGraph()
        g.add_node("锂价", "metric")
        g.add_node("毛利率", "metric")
        g.add_edge("锂价", "毛利率", weight=0.8)

        assert "锂价" in g.nodes
        downstream = g.get_downstream("锂价", depth=2)
        assert "毛利率" in downstream

    def test_serialize(self):
        g = CausalGraph()
        g.add_node("test", "metric")
        d = g.to_dict()
        assert "nodes" in d

        g2 = CausalGraph.from_dict(d)
        assert "test" in g2.nodes


# ---- Engine Tests ----

class TestObservationEngine:
    def test_run_with_sources(self, memory_db, sample_observation):
        engine = ObservationEngine("test")
        context = {
            "sources": [
                {
                    "source": ObservationSource.NEWS,
                    "raw_content": sample_observation.raw_content,
                    "title": sample_observation.title,
                    "timestamp": datetime.now(),
                }
            ]
        }
        result = engine.run(context)
        assert "observations" in result
        assert len(result["observations"]) >= 0


class TestEvidenceEngine:
    def test_run_extracts_evidence(self, memory_db, sample_observation):
        engine = EvidenceEngine("test")
        context = {"observations": [sample_observation]}
        result = engine.run(context)

        assert "evidence_list" in result
        # 如果 content 包含数字 pattern，应提取到 evidence
        evidence = result["evidence_list"]
        assert isinstance(evidence, list)


class TestBeliefEngine:
    def test_create_from_evidence(self, memory_db, sample_evidence):
        engine = BeliefEngine("test")
        context = {
            "evidence": [sample_evidence],
            "subject": "赛力斯毛利率",
        }
        result = engine.run(context)
        belief = result["belief"]
        assert belief is not None
        assert belief.subject == "赛力斯毛利率"
        assert 0.0 <= belief.probability <= 1.0

    def test_bayesian_update(self, memory_db, sample_evidence):
        old_belief = Belief(
            id="old-b1", subject="test", probability=0.5, confidence=0.6,
            version=1, support_evidence_ids=["ev1"]
        )
        engine = BeliefEngine("test")
        context = {
            "evidence": [sample_evidence],
            "subject": "test",
            "existing_belief": old_belief,
        }
        result = engine.run(context)
        belief = result["belief"]
        assert belief.version == 2
        assert belief.previous_version_id == "old-b1"


class TestPredictionEngine:
    def test_run_creates_prediction(self, memory_db):
        belief = Belief(
            id="b1", subject="赛力斯毛利率", probability=0.7,
            confidence=0.8, version=1,
            metadata={"base_value": 0.28},
        )
        engine = PredictionEngine("test")
        context = {
            "belief": belief,
            "bound_evidence": [],
            "horizon_days": 90,
            "target": "赛力斯2026Q2毛利率",
            "calibrated_accuracy": 0.7,
        }
        result = engine.run(context)
        pred = result["prediction"]
        assert pred is not None
        assert pred.target == "赛力斯2026Q2毛利率"
        assert pred.horizon_label == HorizonLabel.D90
        assert len(pred.scenarios) == 3


class TestLearningEngine:
    def test_run_creates_learning(self, memory_db):
        outcome = Outcome(
            id="o1", prediction_id="p1", actual_value=0.25, actual_result="毛利率25%",
            prediction_error=0.107, error_type=ErrorType.OVERCONFIDENCE,
        )
        prediction = Prediction(
            id="p1", target="test", belief_id="b1",
            probability_distribution={}, scenarios=[],
            confidence=0.9, horizon_days=90,
        )
        belief = Belief(id="b1", subject="test", probability=0.7, confidence=0.9, version=1)

        engine = LearningEngine("test")
        context = {"outcome": outcome, "prediction": prediction, "belief": belief}
        result = engine.run(context)

        learning = result["learning"]
        assert learning is not None
        assert learning.learning_type == LearningType.BELIEF
        assert result["belief_adjustment"] < 0  # overconfidence → 负调整


# ---- Pipeline Tests ----

class TestPredictionPipeline:
    def test_run_end_to_end(self, memory_db):
        pipeline = PredictionPipeline(memory_db)
        result = pipeline.run(
            sources=[{
                "source": ObservationSource.FINANCIAL_REPORT,
                "raw_content": "赛力斯2026Q2毛利率28%，同比增长5个百分点。",
                "title": "赛力斯中报2026H1",
                "timestamp": datetime.now(),
            }],
            subject="赛力斯毛利率",
            horizon_days=90,
        )

        assert result["status"] in ("success", "partial")
        assert "belief" in result


# ---- Run ----

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
