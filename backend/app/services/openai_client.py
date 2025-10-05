"""Thin wrapper around the official OpenAI client used by the pipeline."""
from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from typing import Any, Iterable

from openai import AuthenticationError, OpenAI

from ..core.config import get_settings
from .indexing import RetrievedChunk
from .ingestion import DocumentSection


logger = logging.getLogger(__name__)


def _normalise_json_content(content: str) -> str:
    """Return content stripped of common Markdown fences."""

    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines:
            # Drop opening fence such as ``` or ```json
            first_line = lines[0].strip()
            if first_line.startswith("```"):
                lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


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
                    "OpenAI API key is missing. Define OPENAI_API_KEY in the project .env file."
                )
            client_kwargs = {"api_key": api_key}
            openai_project = settings.openai_project
            if openai_project:
                client_kwargs["project"] = openai_project
            self._client = OpenAI(**client_kwargs)
        else:
            self._client = client
        self._model = settings.openai_model

    def _summarise_content_for_log(self, content: object) -> str:
        """Return a privacy-preserving summary of the model output."""

        text = str(content or "").strip()
        if not text:
            return "<empty>"
        normalised = _normalise_json_content(text)
        collapsed = " ".join(normalised.split())
        if not collapsed:
            return "<empty>"
        digest = hashlib.sha256(collapsed.encode("utf-8")).hexdigest()[:12]
        return f"{len(collapsed)} chars (sha256={digest})"

    def _estimate_prompt_tokens(self, messages: list[dict[str, str]]) -> int:
        """Estimate the number of tokens used by the prompt messages."""

        try:  # pragma: no cover - exercised when tiktoken is available
            import tiktoken

            try:
                encoding = tiktoken.encoding_for_model(self._model)
            except KeyError:
                encoding = tiktoken.get_encoding("cl100k_base")

            total = 0
            for message in messages:
                role = message.get("role", "")
                content = message.get("content", "")
                total += len(encoding.encode(role))
                total += len(encoding.encode(content))
                total += 3  # Per-message framing tokens
            return total + 3  # Priming tokens
        except Exception:  # pragma: no cover - deterministic fallback
            approximate_chars = sum(
                len(str(message.get("content", ""))) + len(str(message.get("role", "")))
                for message in messages
            )
            return max(1, approximate_chars // 4)

    def summarise(self, text: str) -> tuple[str, dict[str, int]]:
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
        summary, usage = self._complete(messages, max_tokens=300)
        logger.debug("Received OpenAI summary response (%d chars)", len(summary))
        return summary, usage

    def extract_items(self, text: str, category: str) -> tuple[list[str], dict[str, int]]:
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
        data, usage = self._complete_json(messages, max_tokens=400)
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
        return cleaned, usage

    def simplify_sections(
        self, sections: Iterable[DocumentSection]
    ) -> tuple[list[dict[str, str]], dict[str, int]]:
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
        prompt_tokens = self._estimate_prompt_tokens(messages)
        model_limit = self._model_token_limit()
        safety_margin = 512
        min_completion = 256
        raw_budget = max(model_limit - prompt_tokens, 0)
        if raw_budget <= min_completion:
            initial_max = max(raw_budget, 1)
        else:
            available = max(raw_budget - safety_margin, 0)
            if available >= min_completion:
                initial_max = available
            else:
                initial_max = raw_budget
        initial_max = min(int(initial_max), model_limit)
        logger.debug(
            "Calculated simplification token budget (prompt=%d, max_tokens=%d, model_limit=%d)",
            prompt_tokens,
            initial_max,
            model_limit,
        )
        data, usage = self._complete_json(messages, max_tokens=initial_max)
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
        return results, usage

    def answer_question(
        self, question: str, retrieved_chunks: Iterable[RetrievedChunk]
    ) -> tuple[dict[str, Any], dict[str, int]]:
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
        data, usage = self._complete_json(messages, max_tokens=600)
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
        return {"answer": answer, "sources": sources}, usage

    def _complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> tuple[str, dict[str, int]]:
        aggregated_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        attempt_max_tokens = max_tokens
        model_limit = self._model_token_limit()

        for attempt in range(3):
            try:
                logger.debug(
                    "Calling OpenAI chat completion (model=%s, max_tokens=%d, temperature=%.2f, attempt=%d)",
                    self._model,
                    attempt_max_tokens,
                    temperature,
                    attempt + 1,
                )
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=attempt_max_tokens,
                )
            except AuthenticationError as exc:  # pragma: no cover - network failure path
                logger.warning("OpenAI authentication failed: %s", exc)
                raise OpenAIClientError("Nie udało się uwierzytelnić w OpenAI API.") from exc
            except Exception as exc:  # pragma: no cover - network failure path
                logger.exception("OpenAI chat completion failed")
                raise OpenAIClientError("Nie udało się wywołać OpenAI API.") from exc

            usage_data = getattr(response, "usage", None)
            aggregated_usage["prompt_tokens"] += int(
                getattr(usage_data, "prompt_tokens", 0) or 0
            )
            aggregated_usage["completion_tokens"] += int(
                getattr(usage_data, "completion_tokens", 0) or 0
            )
            aggregated_usage["total_tokens"] += int(
                getattr(usage_data, "total_tokens", 0) or 0
            )

            choices = getattr(response, "choices", None)
            if not choices:
                logger.error("OpenAI response did not include choices")
                raise OpenAIClientError("OpenAI nie zwróciło żadnych wyników.")

            choice = choices[0]
            message = getattr(choice, "message", None)
            content = getattr(message, "content", None)
            finish_reason = getattr(choice, "finish_reason", None)

            if finish_reason == "length":
                logger.warning(
                    "OpenAI response truncated (finish_reason=length, attempt=%d, max_tokens=%d, content_summary=%s)",
                    attempt + 1,
                    attempt_max_tokens,
                    self._summarise_content_for_log(content),
                )
                if attempt_max_tokens >= model_limit:
                    logger.error(
                        "Reached model token limit (%d) after truncated response.",
                        model_limit,
                    )
                    raise OpenAIClientError(
                        "OpenAI zakończyło generowanie odpowiedzi przedwcześnie."
                    )
                attempt_max_tokens = min(attempt_max_tokens * 2, model_limit)
                continue

            if finish_reason and finish_reason != "stop":
                logger.error(
                    "OpenAI response ended with finish_reason=%s (attempt=%d, max_tokens=%d, content_summary=%s)",
                    finish_reason,
                    attempt + 1,
                    attempt_max_tokens,
                    self._summarise_content_for_log(content),
                )
                raise OpenAIClientError(
                    "OpenAI zakończyło generowanie odpowiedzi przedwcześnie."
                )

            if not content:
                logger.error("OpenAI response message missing content")
                raise OpenAIClientError("Odpowiedź OpenAI nie zawiera treści.")

            return str(content).strip(), aggregated_usage

        logger.error("Exceeded maximum retry attempts after truncated OpenAI responses")
        raise OpenAIClientError(
            "OpenAI zakończyło generowanie odpowiedzi przedwcześnie."
        )

    def _model_token_limit(self) -> int:
        model_limits = {
            "gpt-4o": 128_000,
            "gpt-4o-mini": 16_384,
            "gpt-4.1": 128_000,
            "gpt-4.1-mini": 128_000,
        }
        return model_limits.get(self._model, 16_384)

    def _complete_json(
        self, messages: list[dict[str, str]], *, max_tokens: int = 512
    ) -> tuple[Any, dict[str, int]]:
        content, usage = self._complete(messages, max_tokens=max_tokens)
        normalised = _normalise_json_content(content)
        try:
            parsed = json.loads(normalised)
            return parsed, usage
        except json.JSONDecodeError as exc:
            logger.error(
                "Failed to decode OpenAI JSON response. Raw content: %s\nNormalised content: %s",
                content,
                normalised,
                exc_info=True,
            )
            raise OpenAIClientError("Nie udało się zinterpretować odpowiedzi jako JSON.") from exc


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAIClient:
    """Return a cached :class:`OpenAIClient` instance."""

    return OpenAIClient()

