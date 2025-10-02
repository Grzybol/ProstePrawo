"""Lightweight document indexing utilities for the MVP pipeline."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from collections import Counter
from typing import Iterable
from uuid import UUID

from .ingestion import DocumentSection


@dataclass(slots=True)
class RetrievedChunk:
    """Container for retrieved content snippets."""

    identifier: str
    score: float
    text: str


_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


class SimpleIndexer:
    """In-memory TF-IDF like index designed for deterministic unit tests."""

    def __init__(self) -> None:
        self._documents: dict[UUID, list[DocumentSection]] = {}
        self._term_stats: dict[str, Counter[tuple[UUID, str]]] = {}

    def index(self, document_id: UUID, sections: Iterable[DocumentSection]) -> None:
        sections = list(sections)
        self._documents[document_id] = sections
        for section in sections:
            term_counts = Counter(_tokenize(section.text))
            for term, count in term_counts.items():
                key = (document_id, section.identifier)
                self._term_stats.setdefault(term, Counter())[key] = count

    def retrieve(self, document_id: UUID, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        sections = self._documents.get(document_id, [])
        if not sections:
            return []
        query_terms = Counter(_tokenize(query))
        section_by_id = {section.identifier: section for section in sections}
        scores: dict[str, float] = {}
        for term, q_freq in query_terms.items():
            postings = self._term_stats.get(term)
            if not postings:
                continue
            doc_freq = len({doc_id for doc_id, _ in postings})
            idf = math.log(1 + len(self._documents) / (1 + doc_freq))
            for (posting_doc_id, identifier), freq in postings.items():
                if posting_doc_id != document_id:
                    continue
                if identifier not in section_by_id:
                    continue
                scores.setdefault(identifier, 0.0)
                scores[identifier] += (1 + math.log(freq)) * idf * q_freq
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        results: list[RetrievedChunk] = []
        for identifier, score in ranked:
            section = section_by_id.get(identifier)
            if section is None:
                continue
            results.append(RetrievedChunk(identifier=identifier, score=score, text=section.text))
        return results


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]
