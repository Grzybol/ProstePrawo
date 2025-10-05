import time
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from app.models.documents import DocumentMetadata, DocumentUsageMetrics, SectionSimplification
from app.services import inference
from app.services.ingestion import DocumentSection
from app.services.pipeline import DocumentPipeline


@pytest.mark.asyncio
async def test_run_parallel_simplify_honours_semaphore():
    pipeline = DocumentPipeline()
    pipeline.MAX_OPENAI_CONCURRENCY = 2

    active = 0
    observed = 0

    def fake_simplify(sections, use_cloud=None):
        nonlocal active, observed
        active += 1
        observed = max(observed, active)
        time.sleep(0.05)
        result = [
            SectionSimplification(
                identifier=section.identifier,
                source_excerpt=section.text[:20],
                source_text=section.text,
                plain_language=section.text,
            )
            for section in sections
        ]
        active -= 1
        return result, DocumentUsageMetrics()

    sections = [DocumentSection(identifier=f"section-{i}", text=f"Treść {i}") for i in range(6)]
    metadata = DocumentMetadata(user_id=1, title="Test")

    with patch.object(inference, "simplify_sections", side_effect=fake_simplify):
        simplifications, _ = await pipeline._run_parallel_simplify(metadata, sections, use_cloud=False)

    assert len(simplifications) == len(sections)
    assert observed <= pipeline.MAX_OPENAI_CONCURRENCY
