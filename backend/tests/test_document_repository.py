from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import pytest

from app.models.documents import DocumentMetadata
from app.repositories.documents import DocumentRepository


@pytest.fixture
def repository(tmp_path) -> DocumentRepository:
    return DocumentRepository(db_path=tmp_path / "metadata.db")


def test_repository_stores_documents_per_user(repository: DocumentRepository) -> None:
    first = DocumentMetadata(user_id=1, title="Pierwszy")
    second = DocumentMetadata(user_id=2, title="Drugi")
    first.doc_id = uuid4()
    second.doc_id = uuid4()
    first.created_at = datetime.now(timezone.utc)
    second.created_at = datetime.now(timezone.utc)
    repository.upsert(first)
    repository.upsert(second)

    retrieved_first = repository.get(1, first.doc_id)
    assert retrieved_first.user_id == 1
    assert retrieved_first.doc_id == first.doc_id

    retrieved_second = repository.get(2, second.doc_id)
    assert retrieved_second.user_id == 2

    with pytest.raises(KeyError):
        repository.get(1, second.doc_id)

    user_docs = list(repository.list_for_user(1))
    assert [doc.doc_id for doc in user_docs] == [first.doc_id]


def test_repository_serializes_paths(repository: DocumentRepository, tmp_path) -> None:
    metadata = DocumentMetadata(user_id=3, title="Umowa")
    raw_dir = tmp_path / "data" / "raw.txt"
    raw_dir.parent.mkdir(parents=True, exist_ok=True)
    raw_dir.write_text("treść", encoding="utf-8")
    metadata.doc_id = uuid4()
    metadata.created_at = datetime.now(timezone.utc)
    metadata.source_path = raw_dir
    repository.upsert(metadata)

    restored = repository.get(metadata.user_id, metadata.doc_id)
    assert isinstance(restored.source_path, Path)
    assert restored.source_path.read_text(encoding="utf-8") == "treść"
