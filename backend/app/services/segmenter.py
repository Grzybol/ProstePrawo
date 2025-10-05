"""Semantic segmentation helpers for grouping related document sections."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
import re
from typing import Iterable, List

from .ingestion import DocumentSection

_TOKEN_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)


@dataclass(slots=True)
class SemanticSegment:
    """Representation of a semantically coherent segment."""

    identifier: str
    topic: str
    text: str
    source_sections: list[str]
    embedding: list[float]

    def to_dict(self) -> dict:
        return {
            "identifier": self.identifier,
            "topic": self.topic,
            "text": self.text,
            "source_sections": list(self.source_sections),
            "embedding": list(self.embedding),
        }


class SemanticSegmenter:
    """Group extracted document sections into topical segments."""

    def __init__(self, max_chunk_size: int = 2) -> None:
        self._max_chunk_size = max_chunk_size

    def segment(self, sections: Iterable[DocumentSection]) -> list[SemanticSegment]:
        ordered_sections = list(sections)
        if not ordered_sections:
            return []

        topic_buckets: dict[str, list[DocumentSection]] = defaultdict(list)
        topic_order: list[str] = []
        for section in ordered_sections:
            tokens = _tokenize(section.text)
            topic = _derive_topic(tokens) or section.identifier.split(":", 1)[0]
            if topic not in topic_buckets:
                topic_order.append(topic)
            topic_buckets[topic].append(section)

        segments: list[SemanticSegment] = []
        counter = 0
        for topic in topic_order:
            bucket = topic_buckets[topic]
            for chunk in _chunk(bucket, self._max_chunk_size):
                counter += 1
                text = "\n\n".join(section.text.strip() for section in chunk if section.text.strip())
                if not text:
                    continue
                source_ids = [section.identifier for section in chunk]
                embedding = _build_embedding(chunk)
                segments.append(
                    SemanticSegment(
                        identifier=f"segment-{counter}",
                        topic=topic,
                        text=text,
                        source_sections=source_ids,
                        embedding=embedding,
                    )
                )
        return segments


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]


def _derive_topic(tokens: List[str]) -> str:
    filtered = [token for token in tokens if len(token) > 4]
    candidates = filtered or tokens
    if not candidates:
        return "misc"
    counts = Counter(candidates)
    topic, _ = counts.most_common(1)[0]
    return topic


def _chunk(items: list[DocumentSection], size: int) -> Iterable[list[DocumentSection]]:
    current: list[DocumentSection] = []
    for item in items:
        current.append(item)
        if len(current) >= size:
            yield current
            current = []
    if current:
        yield current


def _build_embedding(sections: list[DocumentSection]) -> list[float]:
    tokens = Counter()
    length = 0
    for section in sections:
        tokens.update(_tokenize(section.text))
        length += len(section.text)
    unique_terms = len(tokens)
    magnitude = math.sqrt(sum(count * count for count in tokens.values())) or 1.0
    return [round(length / 1000.0, 4), round(unique_terms / magnitude, 4)]
