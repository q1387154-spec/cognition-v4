"""Memory — 持久化层"""
from .base_store import BaseStore
from .belief_store import BeliefStore
from .evidence_store import EvidenceStore
from .learning_store import LearningStore
from .observation_store import ObservationStore
from .outcome_store import OutcomeStore
from .prediction_store import PredictionStore
from .causal_graph import CausalGraph, CausalGraphStore
from .entity_accuracy_store import EntityAccuracyStore
from .prediction_binding_store import PredictionBindingStore


def reset_all_stores():
    """Reset all store singletons (for testing)."""
    for cls in [BeliefStore, EvidenceStore, LearningStore,
                ObservationStore, OutcomeStore, PredictionStore,
                EntityAccuracyStore, PredictionBindingStore]:
        if hasattr(cls, '_instance'):
            cls._instance = None
    if hasattr(CausalGraphStore, '_instance'):
        CausalGraphStore._instance = None

__all__ = [
    "BaseStore",
    "ObservationStore",
    "EvidenceStore",
    "BeliefStore",
    "PredictionStore",
    "OutcomeStore",
    "LearningStore",
    "CausalGraph",
    "CausalGraphStore",
    "EntityAccuracyStore",
    "PredictionBindingStore",
]
