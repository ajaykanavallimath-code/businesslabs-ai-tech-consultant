"""
Pytest fixtures for Task 3: Meeting to Scope test suite.
Configures isolated temporary storage directories and mock clients.
"""

import json
import shutil
import tempfile
from pathlib import Path
import pytest

from src.storage import Task3Storage
from src.kb_client import KnowledgeBrainClient
from src.workflow import MeetingToScopeWorkflow
from src.review_service import ReviewService
from src.config import Task3Settings, settings


@pytest.fixture
def temp_dir():
    """Create a temporary directory for isolated test execution."""
    d = tempfile.mkdtemp(prefix="task3_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def test_storage(temp_dir):
    """Storage instance backed by isolated temporary directory."""
    return Task3Storage(data_dir=str(temp_dir))


@pytest.fixture
def mock_kb_client():
    """Deterministic offline mock Knowledge Brain client."""
    return KnowledgeBrainClient(mock_mode=True)


@pytest.fixture
def test_workflow(test_storage, mock_kb_client):
    """Workflow configured with test storage and mock KB."""
    return MeetingToScopeWorkflow(
        storage=test_storage,
        kb_client=mock_kb_client,
    )


@pytest.fixture
def test_review_service(test_storage):
    """Review service configured with test storage."""
    return ReviewService(storage=test_storage)


@pytest.fixture
def scenario_a_data():
    """Load Scenario A fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "scenario_a_initial.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def scenario_b_data():
    """Load Scenario B fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "scenario_b_ambiguous.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def scenario_c_data():
    """Load Scenario C fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "scenario_c_followup.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)
