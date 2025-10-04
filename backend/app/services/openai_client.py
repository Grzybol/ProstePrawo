"""Thin wrapper around the official OpenAI client used by the pipeline."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Iterable

from openai import AuthenticationError, OpenAI

from ..core.config import get_settings
from .indexing import RetrievedChunk
from .ingestion import DocumentSection


logger = logging.getLogger(__name__)


class OpenAIClientError(RuntimeError):
    """Raised when the OpenAI client fails to generate a valid response."""


class OpenAIClient:
    """High-level helper exposing domain specific prompts."""

    def __init__(self, client: OpenAI | None = None) -> None:
        settings = get_settings()
        if client is None:
            api_key = settings.openai_api_key
            if not api_key:
                raise RuntimeError(
                    "OpenAI API key is missing. Set OPENAI_API_KEY or PROSTE_PRAWO_OPENAI_API_KEY."
                )
            client_kwargs = {"api_key": api_key}
            openai_project = settings.openai_project
            if openai_project:
                client_kwargs["project"] = openai_project
            self._client = OpenAI(**client_kwargs)
        else:
            self._client = client
        self._model = settings.openai_model

    def summarise(self, text: str) -> str:
        logger.debug("Requesting OpenAI summary (%d chars)", len(text))
        messages = [
            {
                "role": "system",
                "content": (
                    "Jesteś prawniczym asystentem, który tworzy krótkie streszczenia "
                    "z zanonimizowanych dokumentów. Odpowiadaj zwięźle w języku polskim."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Streszcz poniższy tekst w maksymalnie 3 zdaniach. "
                    "Tekst:\n\n" + text
                ),
            },
        ]
        summary = self._complete(messages, max_tokens=300)
        logger.debug("Received OpenAI summary response (%d chars)", len(summary))
        return summary

    def extract_items(self, text: str, category: str) -> list[str]:
        logger.debug("Requesting OpenAI extraction for '%s' (%d chars)", category, len(text))
        messages = [
            {
                "role": "system",
                "content": (
                    "Jesteś prawniczym asystentem pomagającym sporządzić listy punktów "
                    "na podstawie zanonimizowanych dokumentów. Zwracaj odpowiedź jako JSON."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Przeczytaj tekst i wypisz {category} jako listę krótkich zdań. "
                    "Zwróć czystą tablicę JSON, np. [\"Pozycja\"]. "
                    "Tekst:\n\n{body}".format(category=category, body=text)
                ),
            },
        ]
        data = self._complete_json(messages, max_tokens=400)
        logger.debug(
            "Received OpenAI extraction response for '%s': %s",
            category,
            data,
        )
        if not isinstance(data, list):
            raise OpenAIClientError("Nieprawidłowy format odpowiedzi dla listy elementów.")
        cleaned: list[str] = []
        for item in data:
            if not isinstance(item, str):
                continue
            value = item.strip()
            if value:
                cleaned.append(value)
        return cleaned

    def simplify_sections(self, sections: Iterable[DocumentSection]) -> list[dict[str, str]]:
        payload = [
            {
                "identifier": section.identifier,
                "text": section.text,
            }
            for section in sections
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "Jesteś asystentem, który tłumaczy zapisy prawne na prosty język. "
                    "Zwracaj wynik jako tablicę JSON z polami identifier, plain_language i "
                    "source_excerpt. Używaj języka polskiego."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Uprość każdą z sekcji dokumentu. Wejście w formacie JSON:\n\n"
                    + json.dumps(payload, ensure_ascii=False)
                ),
            },
        ]
        logger.debug("Requesting OpenAI simplification for %d sections", len(payload))
        data = self._complete_json(messages, max_tokens=1200)
        if isinstance(data, list):
            logger.debug("Received OpenAI simplification response with %d items", len(data))
        else:
            logger.debug(
                "Received OpenAI simplification response of type %s", type(data).__name__
            )
        if not isinstance(data, list):
            raise OpenAIClientError("Oczekiwano tablicy z uproszczeniami sekcji.")
        results: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            identifier = str(item.get("identifier", "")).strip()
            plain = str(item.get("plain_language", "")).strip()
            excerpt = str(item.get("source_excerpt", "")).strip()
            if identifier and plain:
                results.append(
                    {
                        "identifier": identifier,
                        "plain_language": plain,
                        "source_excerpt": excerpt,
                    }
                )
        if not results:
            raise OpenAIClientError("Brak poprawnych uproszczeń w odpowiedzi LLM.")
        return results

    def answer_question(
        self, question: str, retrieved_chunks: Iterable[RetrievedChunk]
    ) -> dict[str, Any]:
        context = [
            {
                "identifier": chunk.identifier,
                "text": chunk.text,
            }
            for chunk in retrieved_chunks
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "Jesteś prawniczym asystentem odpowiadającym na pytania na podstawie "
                    "zebranych fragmentów dokumentu. Jeśli brakuje danych, jasno to powiedz."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Odpowiedz na pytanie użytkownika korzystając wyłącznie z kontekstu. "
                    "Zwróć JSON o strukturze {\"answer\": str, \"sources\": [str]}. "
                    "Kontekst:\n\n"
                    + json.dumps(context, ensure_ascii=False)
                    + "\n\nPytanie:\n"
                    + question
                ),
            },
        ]
        logger.debug(
            "Requesting OpenAI answer (question length: %d, context items: %d)",
            len(question),
            len(context),
        )
        data = self._complete_json(messages, max_tokens=600)
        logger.debug("Received OpenAI answer response: %s", data)
        if not isinstance(data, dict):
            raise OpenAIClientError("Niepoprawny format odpowiedzi dla Q&A.")
        answer = str(data.get("answer", "")).strip()
        sources_data = data.get("sources", [])
        if isinstance(sources_data, list):
            sources = [str(item).strip() for item in sources_data if str(item).strip()]
        else:
            sources = []
        if not answer:
            raise OpenAIClientError("Brak treści odpowiedzi Q&A.")
        return {"answer": answer, "sources": sources}

    def _complete(self, messages: list[dict[str, str]], *, max_tokens: int = 512, temperature: float = 0.2) -> str:
        try:
            logger.debug(
                "Calling OpenAI chat completion (model=%s, max_tokens=%d, temperature=%.2f)",
                self._model,
                max_tokens,
                temperature,
            )
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except AuthenticationError as exc:  # pragma: no cover - network failure path
            logger.warning("OpenAI authentication failed: %s", exc)
            raise OpenAIClientError("Nie udało się uwierzytelnić w OpenAI API.") from exc
        except Exception as exc:  # pragma: no cover - network failure path
            logger.exception("OpenAI chat completion failed")
            raise OpenAIClientError("Nie udało się wywołać OpenAI API.") from exc
        choices = getattr(response, "choices", None)
        if not choices:
            logger.error("OpenAI response did not include choices")
            raise OpenAIClientError("OpenAI nie zwróciło żadnych wyników.")
        message = choices[0].message
        content = getattr(message, "content", None)
        if not content:
            logger.error("OpenAI response message missing content")
            raise OpenAIClientError("Odpowiedź OpenAI nie zawiera treści.")
        return str(content).strip()

    def _complete_json(self, messages: list[dict[str, str]], *, max_tokens: int = 512) -> Any:
        content = self._complete(messages, max_tokens=max_tokens)
        try:
            parsed = json.loads(content)
            return parsed
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode OpenAI JSON response: %s", content, exc_info=True)
            raise OpenAIClientError("Nie udało się zinterpretować odpowiedzi jako JSON.") from exc


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAIClient:
    """Return a cached :class:`OpenAIClient` instance."""

    return OpenAIClient()

