import pytest
from pydantic import ValidationError

from stem_sci.statistics.mode_policy import AnalysisMode, AnalysisModePolicy


def test_analysis_mode_policy_requires_python_for_dual_mode() -> None:
    policy = AnalysisModePolicy(mode=AnalysisMode.PYTHON_ONLY, python_required=True)
    assert policy.mode is AnalysisMode.PYTHON_ONLY

    with pytest.raises(ValidationError):
        AnalysisModePolicy(mode=AnalysisMode.PYTHON_ONLY, python_required=False)
