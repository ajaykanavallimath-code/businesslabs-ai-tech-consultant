"""
Regression tests for Task 3 task confidence calculations, validation, and serialization.
Verifies that:
1. Valid confidence enum values and numeric confidence_score values are preserved.
2. Missing, null, and invalid confidence values are validated safely.
3. Out-of-range confidence_score values (< 0.0 or > 1.0) raise ValidationError.
4. Capability assessments preserve confidence scores from Task 1.
5. ScopePlanner and DiffEngine generate tasks with valid confidence and confidence scores.
6. Scope total hours and follow-up net hour delta math remain strictly preserved.
"""

import pytest
from pydantic import ValidationError
from src.models import (
    TaskEstimate,
    EstimateConfidence,
    WorkType,
    CapabilityAssessment,
    CapabilityStatus,
    ExtractedRequirement,
    RequirementStatus,
    RequirementCertainty,
)
from src.agents.planner import ScopePlanner
from src.agents.diff_engine import DiffEngine


class TestTaskEstimateConfidenceValidation:
    """Tests validation of confidence and confidence_score on TaskEstimate."""

    def test_valid_confidence_enum_and_score(self):
        """Valid enum and score within [0.0, 1.0] must be accepted."""
        task = TaskEstimate(
            task_id="TSK-001",
            title="Setup Directory",
            description="Configure initial directory settings.",
            work_type=WorkType.CONFIGURATION,
            estimated_hours=4.0,
            estimation_rationale="Standard baseline setup.",
            confidence=EstimateConfidence.HIGH,
            confidence_score=0.95,
        )
        assert task.confidence == EstimateConfidence.HIGH
        assert task.confidence_score == 0.95

    def test_default_confidence_and_none_score(self):
        """Default confidence must be MEDIUM and confidence_score must default to None."""
        task = TaskEstimate(
            task_id="TSK-002",
            title="General Task",
            description="Task without explicit confidence.",
            work_type=WorkType.CONFIGURATION,
            estimated_hours=2.0,
            estimation_rationale="General estimate.",
        )
        assert task.confidence == EstimateConfidence.MEDIUM
        assert task.confidence_score is None

    def test_confidence_score_boundary_values(self):
        """Boundary values 0.0 and 1.0 must be valid."""
        task_min = TaskEstimate(
            task_id="TSK-MIN",
            title="Min Boundary",
            description="0.0 confidence.",
            work_type=WorkType.CONFIGURATION,
            estimated_hours=1.0,
            estimation_rationale="Boundary test.",
            confidence=EstimateConfidence.LOW,
            confidence_score=0.0,
        )
        assert task_min.confidence_score == 0.0

        task_max = TaskEstimate(
            task_id="TSK-MAX",
            title="Max Boundary",
            description="1.0 confidence.",
            work_type=WorkType.CONFIGURATION,
            estimated_hours=1.0,
            estimation_rationale="Boundary test.",
            confidence=EstimateConfidence.HIGH,
            confidence_score=1.0,
        )
        assert task_max.confidence_score == 1.0

    def test_out_of_range_negative_confidence_score_raises_error(self):
        """Negative confidence_score (< 0.0) must raise ValidationError."""
        with pytest.raises(ValidationError):
            TaskEstimate(
                task_id="TSK-ERR-1",
                title="Negative Confidence",
                description="Should fail validation.",
                work_type=WorkType.CONFIGURATION,
                estimated_hours=2.0,
                estimation_rationale="Negative confidence test.",
                confidence_score=-0.1,
            )

    def test_out_of_range_excessive_confidence_score_raises_error(self):
        """Excessive confidence_score (> 1.0) must raise ValidationError."""
        with pytest.raises(ValidationError):
            TaskEstimate(
                task_id="TSK-ERR-2",
                title="Excessive Confidence",
                description="Should fail validation.",
                work_type=WorkType.CONFIGURATION,
                estimated_hours=2.0,
                estimation_rationale="Excessive confidence test.",
                confidence_score=1.05,
            )


class TestCapabilityAssessmentConfidence:
    """Tests preservation of capability match confidence scores."""

    def test_capability_assessment_with_valid_confidence(self):
        """CapabilityAssessment must preserve Task 1 confidence score."""
        ass = CapabilityAssessment(
            requirement_id="REQ-001",
            status=CapabilityStatus.SUPPORTED,
            evidence_summary="Supported natively.",
            confidence=0.95,
        )
        assert ass.confidence == 0.95

    def test_capability_assessment_out_of_range_confidence_raises_error(self):
        """CapabilityAssessment confidence outside [0.0, 1.0] must raise ValidationError."""
        with pytest.raises(ValidationError):
            CapabilityAssessment(
                requirement_id="REQ-001",
                status=CapabilityStatus.SUPPORTED,
                evidence_summary="Supported natively.",
                confidence=1.5,
            )


class TestPlannerAndDiffEngineConfidenceGeneration:
    """Tests end-to-end task generation and confidence preservation across versions."""

    def test_planner_generates_valid_confidence_scores_for_all_tasks(self):
        """Every generated task must have valid confidence enum and numeric confidence_score."""
        planner = ScopePlanner()
        reqs = [
            ExtractedRequirement(
                id="REQ-001",
                title="Design & Styling",
                description="Custom styling setup.",
                transcript_evidence="Quote",
            ),
            ExtractedRequirement(
                id="REQ-002",
                title="Stripe Gateway",
                description="Stripe billing integration.",
                transcript_evidence="Quote",
            ),
        ]
        assessments = [
            CapabilityAssessment(
                requirement_id="REQ-001",
                status=CapabilityStatus.SUPPORTED,
                evidence_summary="Supported.",
                confidence=0.95,
            ),
            CapabilityAssessment(
                requirement_id="REQ-002",
                status=CapabilityStatus.SUPPORTED,
                evidence_summary="Supported.",
                confidence=0.90,
            ),
        ]

        scope = planner.build_scope(
            project_id="PRJ-CONF-01",
            project_title="Confidence Test Project",
            requirements=reqs,
            assessments=assessments,
            analysis_data={"client_objectives": ["Test"], "assumptions": [], "exclusions": [], "risks": []},
            version="v1.0",
        )

        assert len(scope.tasks) >= 4  # Setup + 2 Reqs + UAT + Deploy
        for t in scope.tasks:
            assert isinstance(t.confidence, EstimateConfidence)
            assert t.confidence in {EstimateConfidence.HIGH, EstimateConfidence.MEDIUM, EstimateConfidence.LOW, EstimateConfidence.PROVISIONAL}
            assert t.confidence_score is not None
            assert 0.0 <= t.confidence_score <= 1.0
            assert t.estimated_hours >= 0.0

    def test_diff_engine_preserves_confidence_and_hours_math(self):
        """DiffEngine must preserve task confidence on revised tasks and keep exact hour math."""
        planner = ScopePlanner()
        diff_engine = DiffEngine()

        base_reqs = [
            ExtractedRequirement(
                id="REQ-001",
                title="Branding Setup",
                description="Theme setup.",
                transcript_evidence="Quote",
            ),
            ExtractedRequirement(
                id="REQ-002",
                title="Stripe Billing",
                description="Single currency USD.",
                transcript_evidence="Quote",
            ),
        ]
        base_ass = [
            CapabilityAssessment(
                requirement_id="REQ-001",
                status=CapabilityStatus.SUPPORTED,
                evidence_summary="Supported.",
                confidence=0.95,
            ),
            CapabilityAssessment(
                requirement_id="REQ-002",
                status=CapabilityStatus.SUPPORTED,
                evidence_summary="Supported.",
                confidence=0.90,
            ),
        ]
        baseline = planner.build_scope(
            project_id="PRJ-CONF-02",
            project_title="Baseline Diff Test",
            requirements=base_reqs,
            assessments=base_ass,
            analysis_data={"client_objectives": ["Test"], "assumptions": [], "exclusions": [], "risks": []},
            version="v1.0",
        )

        followup_reqs = [
            ExtractedRequirement(
                id="REQ-002",
                title="Stripe Billing",
                description="Multi-currency USD, CAD, GBP with custom invoicing.",
                transcript_evidence="Modified Quote",
            ),
            ExtractedRequirement(
                id="REQ-003",
                title="Zapier Lead Sync",
                description="Outbound webhook to CRM.",
                transcript_evidence="Added Quote",
            ),
        ]
        followup_ass = [
            CapabilityAssessment(
                requirement_id="REQ-003",
                status=CapabilityStatus.PARTIALLY_SUPPORTED,
                evidence_summary="Supported with middleware.",
                confidence=0.75,
            ),
        ]

        report, rev_scope, rev_proposal = diff_engine.detect_changes(
            baseline_scope=baseline,
            followup_requirements=followup_reqs,
            followup_assessments=followup_ass,
            followup_analysis_data={"client_objectives": ["Expanded"], "assumptions": [], "exclusions": [], "risks": []},
            new_version="v2.0",
        )

        # 1. All revised tasks must have valid confidence and confidence_score
        assert len(rev_scope.tasks) > 0
        for t in rev_scope.tasks:
            assert isinstance(t.confidence, EstimateConfidence)
            assert t.confidence_score is not None
            assert 0.0 <= t.confidence_score <= 1.0

        # 2. Scope total hours must strictly equal sum of task hours
        expected_total = round(sum(t.estimated_hours for t in rev_scope.tasks), 2)
        assert rev_scope.total_estimated_hours == expected_total

        # 3. Net delta math must be exact
        expected_delta = round(rev_scope.total_estimated_hours - baseline.total_estimated_hours, 2)
        assert report.net_hour_delta == expected_delta
        assert report.total_original_hours == baseline.total_estimated_hours
        assert report.total_revised_hours == rev_scope.total_estimated_hours
