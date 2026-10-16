"""
Tests for Task 3 FastAPI REST endpoints.
Uses fastapi.testclient.TestClient to test API routes, status codes, payload validations, and security gates.
"""

import pytest
from fastapi.testclient import TestClient

from src.api import app, storage


@pytest.fixture(autouse=True)
def clean_storage():
    """Ensure clean storage before and after each API test."""
    storage.clear_all()
    yield
    storage.clear_all()


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    """Verify health check endpoint returns 200."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "Task 3" in data["service"]


def test_scenarios_listing_endpoint(client):
    """Verify scenarios endpoint returns all 3 prepared demo scenarios."""
    resp = client.get("/api/v1/scenarios")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 3
    assert len(data["scenarios"]) == 3


def test_initial_meeting_and_retrieval_flow(client, scenario_a_data):
    """Verify initial meeting submission, scope, requirements, and tasks retrieval."""
    # 1. Submit initial meeting
    payload = {
        "project_id": "PRJ-API-01",
        "title": scenario_a_data["title"],
        "transcript_text": scenario_a_data["transcript"],
        "client_name": scenario_a_data["client_name"],
    }
    init_resp = client.post("/api/v1/meetings/initial", json=payload)
    assert init_resp.status_code == 201
    init_data = init_resp.json()
    assert init_data["project_id"] == "PRJ-API-01"
    assert init_data["version"] == "v1.0"
    proposal_id = init_data["proposal"]["proposal_id"]

    # 2. Get Scope
    scope_resp = client.get("/api/v1/projects/PRJ-API-01/scope")
    assert scope_resp.status_code == 200
    assert scope_resp.json()["total_estimated_hours"] > 0

    # 3. Get Requirements
    req_resp = client.get("/api/v1/projects/PRJ-API-01/requirements")
    assert req_resp.status_code == 200
    assert len(req_resp.json()) >= 4

    # 4. Get Capabilities
    cap_resp = client.get("/api/v1/projects/PRJ-API-01/capabilities")
    assert cap_resp.status_code == 200
    assert len(cap_resp.json()) >= 4

    # 5. Get Tasks
    tasks_resp = client.get("/api/v1/projects/PRJ-API-01/tasks")
    assert tasks_resp.status_code == 200
    assert tasks_resp.json()["task_count"] > 0

    # 6. Attempt delivery without approval -> MUST FAIL WITH 403 FORBIDDEN
    deliver_payload = {
        "proposal_id": proposal_id,
        "recipient_email": "client@example.com",
        "delivered_by": "API Test",
    }
    block_resp = client.post("/api/v1/projects/PRJ-API-01/deliver", json=deliver_payload)
    assert block_resp.status_code == 403
    assert "without explicit human approval" in block_resp.json()["detail"]

    # 7. Approve Proposal
    review_payload = {
        "proposal_id": proposal_id,
        "action": "approve",
        "reviewer_id": "Lead Consultant",
        "comments": "Approved via API test",
    }
    appr_resp = client.post("/api/v1/projects/PRJ-API-01/review", json=review_payload)
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "approved"

    # 8. Delivery now succeeds
    success_deliver = client.post("/api/v1/projects/PRJ-API-01/deliver", json=deliver_payload)
    assert success_deliver.status_code == 200
    assert success_deliver.json()["success"] is True


def test_followup_and_change_reports_flow(client, scenario_a_data, scenario_c_data):
    """Verify follow-up meeting submission and change detection reports via API."""
    # Submit initial
    client.post("/api/v1/meetings/initial", json={
        "project_id": "PRJ-API-02",
        "title": scenario_a_data["title"],
        "transcript_text": scenario_a_data["transcript"],
    })

    # Submit follow-up
    followup_resp = client.post("/api/v1/meetings/followup", json={
        "project_id": "PRJ-API-02",
        "title": scenario_c_data["title"],
        "transcript_text": scenario_c_data["transcript"],
    })
    assert followup_resp.status_code == 200
    fol_data = followup_resp.json()
    assert fol_data["revised_version"] == "v2.0"
    assert "net_hour_delta" in fol_data

    # Retrieve change reports
    changes_resp = client.get("/api/v1/projects/PRJ-API-02/changes")
    assert changes_resp.status_code == 200
    reports = changes_resp.json()
    assert len(reports) >= 1
    assert len(reports[0]["changes"]) >= 3

    # Retrieve history
    hist_resp = client.get("/api/v1/projects/PRJ-API-02/history")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert "v1.0" in hist_data["scope_versions"]
    assert "v2.0" in hist_data["scope_versions"]
