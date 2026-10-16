"""Command-line interface for the Knowledge Brain service."""

import argparse
import asyncio
import json
import sys
from typing import Optional

from src.config import settings
from src.sitemap_sync import SitemapCrawler


def run_crawl(args: argparse.Namespace) -> None:
    """Execute the incremental sitemap crawler."""
    crawler = SitemapCrawler(config=settings)

    print(f"[*] Starting sitemap sync...")
    print(f"[*] Sitemap URL: {args.sitemap_url or settings.sitemap_url}")
    print(f"[*] Max articles: {args.limit or 'unlimited'}")
    print(f"[*] Force re-crawl: {args.force}")

    response = asyncio.run(
        crawler.run_sync(
            sitemap_url=args.sitemap_url,
            max_articles=args.limit,
            force=args.force,
        )
    )

    print("\n[+] Sync Results:")
    print(f"    - Added:     {response.stats.added}")
    print(f"    - Updated:   {response.stats.updated}")
    print(f"    - Removed:   {response.stats.removed}")
    print(f"    - Unchanged: {response.stats.unchanged}")
    print(f"    - Total Active in Index: {response.stats.total_active}")
    print(f"\n[+] {response.message}")


def run_index(args: argparse.Namespace) -> None:
    """Index all crawled articles into the ChromaDB vector database."""
    from src.vector_store import VectorStore

    crawler = SitemapCrawler(config=settings)
    store = VectorStore(config=settings)

    print("[*] Indexing crawled articles into ChromaDB vector database...")
    print(f"[*] Embedding Provider: {settings.embedding_provider} ({settings.embedding_model})")
    print(f"[*] Chroma Persist Dir: {settings.chroma_persist_dir}")

    res = store.sync_all_from_state(crawler.state, force=args.force)

    print("\n[+] Vector Indexing Complete:")
    print(f"    - Indexed Articles:        {res['indexed_articles']}")
    print(f"    - Total Chunks Created:    {res['total_chunks']}")
    print(f"    - Removed Articles Pruned: {res['removed_articles']}")
    print(f"    - Total Chunks in DB:      {res['collection_total']}")


def run_search(args: argparse.Namespace) -> None:
    """Execute a semantic similarity query against the vector store."""
    from src.vector_store import VectorStore

    store = VectorStore(config=settings)
    query = args.query
    top_k = args.top_k
    min_score = args.min_score

    print(f"[*] Searching for: '{query}'")
    print(f"[*] Top K: {top_k}, Min Score: {min_score or settings.similarity_threshold}")

    citations = store.search(query=query, top_k=top_k, min_score=min_score)

    if not citations:
        print("\n[-] No matching citations found above threshold.")
        return

    print(f"\n[+] Found {len(citations)} relevant citations:\n")
    for idx, c in enumerate(citations, 1):
        print(f"[{idx}] {c.title} (Relevance Score: {c.score})")
        print(f"    URL:     {c.url}")
        if c.section:
            print(f"    Section: {c.section}")
        print(f"    Snippet: {c.snippet[:180]}...")
        if c.images:
            print(f"    Images:  {len(c.images)} attached screenshot(s)")
            for img in c.images:
                print(f"             • URL: {img.url}")
                if img.caption:
                    print(f"               Caption: {img.caption}")
        print("-" * 60)


def run_status(args: argparse.Namespace) -> None:
    """Print the current knowledge base crawler index status."""
    from src.vector_store import VectorStore

    crawler = SitemapCrawler(config=settings)
    store = VectorStore(config=settings)

    active = sum(1 for r in crawler.state.values() if r.status == "active")
    removed = sum(1 for r in crawler.state.values() if r.status == "removed")

    print("[*] Knowledge Brain Status:")
    print(f"    - State file:             {settings.sitemap_state_file}")
    print(f"    - Total records tracked:  {len(crawler.state)}")
    print(f"    - Active articles:        {active}")
    print(f"    - Soft-removed articles:  {removed}")
    print(f"    - Total Chunks in Chroma: {store.count()}")


def run_ask(args: argparse.Namespace) -> None:
    """Run grounded RAG query through CLI."""
    from src.rag_engine import RAGEngine
    from src.models import QueryRequest

    engine = RAGEngine(config=settings)
    req = QueryRequest(
        query=args.query,
        top_k=args.top_k,
        min_score=args.min_score,
    )

    print(f"[*] Query: {args.query}")
    resp = asyncio.run(engine.answer_query(req))

    if args.json:
        print(json.dumps(resp.model_dump(mode="json"), indent=2))
        return

    print("\n" + "=" * 60)
    if resp.escalated:
        print(f"[!] ESCALATED TO HUMAN EXPERT (Task ID: {resp.escalation_id})")
        print(f"    Confidence: {resp.confidence_score}")
        print(f"    Notice:     {resp.answer}")
    else:
        print(f"[+] ANSWER (Confidence: {resp.confidence_score}):")
        print(f"    {resp.answer}")

    if resp.sources:
        print("\n[+] Source Citations:")
        for idx, src in enumerate(resp.sources, 1):
            print(f"    [{idx}] {src.title}")
            print(f"        URL:     {src.url}")
            if src.section:
                print(f"        Section: {src.section}")
            print(f"        Score:   {src.score}")

    if resp.images:
        print("\n[+] Supporting Screenshots:")
        for idx, img in enumerate(resp.images, 1):
            print(f"    [{idx}] {img.url}")
            if img.caption:
                print(f"        Caption: {img.caption}")
    print("=" * 60)


def run_escalations(args: argparse.Namespace) -> None:
    """List escalation tasks."""
    from src.escalation_manager import EscalationManager
    from src.models import EscalationStatus

    manager = EscalationManager(config=settings)
    status_filter = None
    if args.status:
        try:
            status_filter = EscalationStatus(args.status.lower())
        except ValueError:
            print(f"[-] Invalid status '{args.status}'. Choose 'pending', 'resolved', or 'dismissed'.")
            return

    tasks = manager.list_escalations(status=status_filter)
    print(f"[*] Total Escalations: {len(tasks)}")
    for t in tasks:
        print(f"[-] ID: {t.id} | Status: {t.status.value} | Created: {t.created_at}")
        print(f"    Query:  {t.query}")
        print(f"    Reason: {t.reason}")
        if t.status == EscalationStatus.RESOLVED:
            print(f"    Resolved by {t.expert_name}: {t.resolution}")
        print("-" * 50)


def run_resolve(args: argparse.Namespace) -> None:
    """Resolve an escalation task."""
    from src.escalation_manager import EscalationManager

    manager = EscalationManager(config=settings)
    task = manager.resolve_escalation(
        task_id=args.task_id,
        resolution=args.resolution,
        expert_name=args.expert or "AI Tech Consultant",
    )
    if not task:
        print(f"[-] Escalation task '{args.task_id}' not found.")
        return

    print(f"[+] Successfully resolved escalation '{args.task_id}'.")
    print(f"    Resolution: {task.resolution}")
    print(f"    Expert:     {task.expert_name}")


def run_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI Uvicorn server."""
    import uvicorn

    host = args.host or settings.kb_api_host
    port = args.port or settings.kb_api_port
    print(f"[*] Starting Knowledge Brain REST API on http://{host}:{port}")
    uvicorn.run("src.api:app", host=host, port=port, reload=args.reload)


def main() -> None:
    """Entry point for CLI commands."""
    parser = argparse.ArgumentParser(
        description="Knowledge Brain CLI: Management & Ingestion for Brilliant Directories"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Crawl command
    crawl_parser = subparsers.add_parser("crawl", help="Run incremental sitemap crawler")
    crawl_parser.add_argument("--limit", type=int, default=None, help="Max articles to process")
    crawl_parser.add_argument("--sitemap-url", type=str, default=None, help="Custom sitemap URL")
    crawl_parser.add_argument("--force", action="store_true", help="Force re-crawl of unchanged articles")

    # Index command
    index_parser = subparsers.add_parser("index", help="Index crawled articles into ChromaDB vector store")
    index_parser.add_argument("--force", action="store_true", help="Force re-indexing of all articles")

    # Search command
    search_parser = subparsers.add_parser("search", help="Semantic similarity search against vector store")
    search_parser.add_argument("query", type=str, help="Search query")
    search_parser.add_argument("--top-k", type=int, default=3, help="Max results to return")
    search_parser.add_argument("--min-score", type=float, default=None, help="Minimum similarity score")

    # Ask command (Step 1.4 Grounded RAG)
    ask_parser = subparsers.add_parser("ask", help="Ask a question with grounded Claude citations and escalation")
    ask_parser.add_argument("query", type=str, help="Question to ask")
    ask_parser.add_argument("--top-k", type=int, default=3, help="Max chunks to retrieve")
    ask_parser.add_argument("--min-score", type=float, default=None, help="Minimum similarity score")
    ask_parser.add_argument("--json", action="store_true", help="Output response in JSON format")

    # Escalations list command
    esc_parser = subparsers.add_parser("escalations", help="List human expert escalation tasks")
    esc_parser.add_argument("--status", type=str, default=None, help="Filter by status (pending, resolved)")

    # Resolve escalation command
    resolve_parser = subparsers.add_parser("resolve", help="Resolve an escalation task")
    resolve_parser.add_argument("task_id", type=str, help="Escalation task ID (e.g. esc_12345678)")
    resolve_parser.add_argument("--resolution", type=str, required=True, help="Expert verified ground truth")
    resolve_parser.add_argument("--expert", type=str, default="AI Tech Consultant", help="Name of expert")

    # Status command
    subparsers.add_parser("status", help="Show current crawled articles and vector index status")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start the FastAPI REST API server")
    serve_parser.add_argument("--host", type=str, default=None, help="Server host")
    serve_parser.add_argument("--port", type=int, default=None, help="Server port")
    serve_parser.add_argument("--reload", action="store_true", help="Enable hot reload")

    args = parser.parse_args()

    if args.command == "crawl":
        run_crawl(args)
    elif args.command == "index":
        run_index(args)
    elif args.command == "search":
        run_search(args)
    elif args.command == "ask":
        run_ask(args)
    elif args.command == "escalations":
        run_escalations(args)
    elif args.command == "resolve":
        run_resolve(args)
    elif args.command == "status":
        run_status(args)
    elif args.command == "serve":
        run_serve(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

