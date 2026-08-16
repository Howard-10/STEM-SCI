"""Research data-version contracts."""

from .freeze import DataFreezeService, FrozenDatasetIntegrityError
from .analysis_dataset import DeterministicDataProcessor
from .audit import ModelEligibilityEvaluator, StructuralDataAuditor, StructuralDataAuditReport
from .models import (
    AnalysisDatasetRef,
    AnalysisDatasetSerializationPolicy,
    DatasetRef,
    FrozenDatasetRef,
    ModelEligibilityManifest,
    ParticipantEligibilityManifest,
    ProcessedDatasetRef,
    RawDatasetRef,
    SyntheticDatasetGenerationManifest,
)
from .processing import DataProcessingService

__all__ = [
    "DataFreezeService",
    "DeterministicDataProcessor",
    "DataProcessingService",
    "AnalysisDatasetRef",
    "AnalysisDatasetSerializationPolicy",
    "DatasetRef",
    "FrozenDatasetIntegrityError",
    "FrozenDatasetRef",
    "ModelEligibilityManifest",
    "ModelEligibilityEvaluator",
    "ParticipantEligibilityManifest",
    "ProcessedDatasetRef",
    "RawDatasetRef",
    "StructuralDataAuditor",
    "StructuralDataAuditReport",
    "SyntheticDatasetGenerationManifest",
]
