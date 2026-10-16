"""FastAPI application for Knowledge Brain."""

from contextlib import asynccontextmanager
from typing import Optional, List
from fastapi import FastAPI, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.models import (
    ArticleStatus,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    CapabilityCheckRequest,
    CapabilityCheckResponse,
    SyncResponse,
    SyncStats,
    EscalationStatus,
    EscalationTask,
    EscalationResolveRequest,
    ImageCitation,
    SourceCitation,
)
from src.sitemap_sync import SitemapCrawler
from src.vector_store import VectorStore
from src.escalation_manager import EscalationManager
from src.rag_engine import RAGEngine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle startup and shutdown handler."""
    settings.ensure_directories()
    yield


app = FastAPI(
    title="Knowledge Brain API",
    description="RAG & Knowledge Automation System for Brilliant Directories Solution Center",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for cross-language integration (e.g. TypeScript Inbox Agent)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check and status metrics",
    tags=["System"],
)
async def health_check() -> HealthResponse:
    """Return current service health and knowledge base index statistics."""
    crawler = SitemapCrawler(config=settings)
    store = VectorStore(config=settings)

    active_articles = sum(1 for r in crawler.state.values() if r.status == ArticleStatus.ACTIVE)
    total_chunks = store.count()

    return HealthResponse(
        status="healthy",
        version="0.1.0",
        service="Knowledge Brain",
        total_articles=active_articles,
        total_chunks=total_chunks,
        last_sync=None,
    )


@app.post(
    "/api/v1/sync",
    response_model=SyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger incremental sitemap synchronization",
    tags=["Ingestion"],
)
async def trigger_sitemap_sync(
    limit: Optional[int] = Query(default=None, description="Max articles to process"),
    force: bool = Query(default=False, description="Force re-crawl of unchanged articles"),
) -> SyncResponse:
    """Run 3-way incremental sitemap synchronization (Added, Updated, Removed, Unchanged)."""
    crawler = SitemapCrawler(config=settings)
    return await crawler.run_sync(max_articles=limit, force=force)


@app.post(
    "/api/v1/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Grounded question-answering with strict source citations and escalation",
    tags=["Retrieval & QA"],
)
async def query_knowledge_base(req: QueryRequest) -> QueryResponse:
    """Answer technical questions using ChromaDB retrieval and Claude synthesis.

    If evidence is insufficient, returns escalated=True and creates an expert task.
    """
    engine = RAGEngine(config=settings)
    return await engine.answer_query(req)


@app.get(
    "/api/v1/escalations",
    response_model=List[EscalationTask],
    status_code=status.HTTP_200_OK,
    summary="List human expert escalation tasks",
    tags=["Escalations"],
)
async def list_escalations(
    status_filter: Optional[EscalationStatus] = Query(
        default=None,
        alias="status",
        description="Filter by status (pending, resolved, dismissed)",
    )
) -> List[EscalationTask]:
    """Retrieve human escalation tasks."""
    manager = EscalationManager(config=settings)
    return manager.list_escalations(status=status_filter)


@app.get(
    "/api/v1/escalations/{task_id}",
    response_model=EscalationTask,
    status_code=status.HTTP_200_OK,
    summary="Get details of a specific escalation task",
    tags=["Escalations"],
)
async def get_escalation(task_id: str) -> EscalationTask:
    """Fetch an escalation task by its unique ID."""
    manager = EscalationManager(config=settings)
    task = manager.get_escalation(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Escalation task '{task_id}' not found.",
        )
    return task


@app.post(
    "/api/v1/escalations/{task_id}/resolve",
    response_model=EscalationTask,
    status_code=status.HTTP_200_OK,
    summary="Resolve an escalation task with expert feedback",
    tags=["Escalations"],
)
async def resolve_escalation(task_id: str, req: EscalationResolveRequest) -> EscalationTask:
    """Resolve an escalation task with verified consultant knowledge."""
    manager = EscalationManager(config=settings)
    task = manager.resolve_escalation(
        task_id=task_id,
        resolution=req.resolution,
        expert_name=req.expert_name,
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Escalation task '{task_id}' not found.",
        )
    return task


@app.post(
    "/api/v1/capability-check",
    response_model=CapabilityCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Check if a client requirement can be fulfilled natively or requires custom code",
    tags=["Consultant Tools"],
)
async def check_capability(req: CapabilityCheckRequest) -> CapabilityCheckResponse:
    """Verify whether a client feature requirement is natively supported in Brilliant Directories."""
    engine = RAGEngine(config=settings)
    rag_resp = await engine.answer_query(
        QueryRequest(query=f"Is this feature supported natively in Brilliant Directories: {req.requirement}?", top_k=3)
    )

    if rag_resp.escalated or not rag_resp.sources:
        return CapabilityCheckResponse(
            requirement=req.requirement,
            supported_natively=False,
            confidence=rag_resp.confidence_score,
            matching_feature=None,
            configuration_path=None,
            documentation_urls=[],
            notes="No native Brilliant Directories setting found. Likely requires custom widget or script development.",
        )

    top_src = rag_resp.sources[0]
    return CapabilityCheckResponse(
        requirement=req.requirement,
        supported_natively=True,
        confidence=rag_resp.confidence_score,
        matching_feature=top_src.title,
        configuration_path=top_src.section or "Admin Dashboard",
        documentation_urls=[s.url for s in rag_resp.sources],
        notes=rag_resp.answer,
    )
