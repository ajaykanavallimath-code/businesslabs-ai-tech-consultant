"""Manager for logging, storing, and resolving human escalation tasks."""

import json
import logging
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.config import Settings, settings as global_settings
from src.models import (
    EscalationStatus,
    EscalationTask,
    SourceCitation,
)

logger = logging.getLogger("knowledge_brain.escalation_manager")


class EscalationManager:
    """Persistent manager for unanswered inquiries requiring human expert review."""

    def __init__(self, config: Optional[Settings] = None):
        self.config = config or global_settings
        self.config.ensure_directories()
        self.file_path: Path = self.config.escalations_file
        self.tasks: Dict[str, EscalationTask] = {}
        self._load()

    def _load(self) -> None:
        """Load escalations from JSON persistence file."""
        if not self.file_path.exists():
            self.tasks = {}
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.tasks = {
                item_id: EscalationTask.model_validate(item_data)
                for item_id, item_data in data.items()
            }
        except Exception as e:
            logger.error(f"Failed to load escalations from {self.file_path}: {e}")
            self.tasks = {}

    def _save(self) -> None:
        """Atomically save escalations to disk."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            item_id: task.model_dump(mode="json")
            for item_id, task in self.tasks.items()
        }

        temp_dir = self.file_path.parent
        with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, indent=2)
            temp_name = tf.name

        Path(temp_name).replace(self.file_path)

    def create_escalation(
        self,
        query: str,
        reason: str,
        sources: Optional[List[SourceCitation]] = None,
    ) -> EscalationTask:
        """Create and persist a new human expert escalation task."""
        task_id = f"esc_{uuid.uuid4().hex[:8]}"
        task = EscalationTask(
            id=task_id,
            query=query,
            reason=reason,
            retrieved_sources=sources or [],
            status=EscalationStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        self.tasks[task_id] = task
        self._save()
        logger.info(f"Created escalation task {task_id}: '{query}' (Reason: {reason})")
        return task

    def get_escalation(self, task_id: str) -> Optional[EscalationTask]:
        """Fetch a specific escalation task by ID."""
        return self.tasks.get(task_id)

    def list_escalations(
        self,
        status: Optional[EscalationStatus] = None,
    ) -> List[EscalationTask]:
        """List escalation tasks, optionally filtered by status."""
        tasks = list(self.tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def resolve_escalation(
        self,
        task_id: str,
        resolution: str,
        expert_name: str = "AI Tech Consultant",
    ) -> Optional[EscalationTask]:
        """Mark an escalation as resolved with the verified expert ground truth."""
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"Attempted to resolve non-existent escalation {task_id}")
            return None

        task.status = EscalationStatus.RESOLVED
        task.resolution = resolution
        task.expert_name = expert_name
        task.resolved_at = datetime.utcnow()
        self._save()
        logger.info(f"Resolved escalation {task_id} by {expert_name}")

        if self.config.auto_index_resolved_escalations:
            try:
                from src.vector_store import VectorStore
                from src.models import ArticleRecord, ArticleStatus

                store = VectorStore(config=self.config)
                expert_article = ArticleRecord(
                    url=f"https://support.brilliantdirectories.com/support/solutions/expert-guidance/{task_id}",
                    title=f"Expert Guidance: {task.query}",
                    category="Human Expert Guidance",
                    folder="Consultant Resolutions",
                    content=(
                        f"## Question: {task.query}\n\n"
                        f"**Expert Verified Guidance (by {expert_name}):**\n"
                        f"{resolution}\n\n"
                        f"Originally escalated inquiry on Brilliant Directories functionality."
                    ),
                    images=[],
                    lastmod=datetime.utcnow().isoformat(),
                    content_hash=f"expert_{task_id}",
                    status=ArticleStatus.ACTIVE,
                )
                store.index_article(expert_article)
                logger.info(f"Auto-indexed resolved escalation {task_id} into ChromaDB")
            except Exception as e:
                logger.warning(f"Could not auto-index resolved escalation {task_id}: {e}")

        return task
