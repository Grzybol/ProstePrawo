# Guidelines wdrożeniowe pipeline'u

## Checklista przygotowania środowiska

- [ ] Utwórz katalog bazowy `/data` z uprawnieniami zapisu dla serwisu.
- [ ] Zapewnij automatyczne zakładanie struktury `/data/{user_id}/{doc_id}/` (`raw`, `preprocessed`, `secure`, `simplified`, `exports`).
- [ ] Skonfiguruj per-user store lokalnego LLM w `/data/llm_store/{user_id}` (cache, pamięć konwersacji, embeddingi).
- [ ] Zweryfikuj dostępność lokalnego repozytorium modeli (`models/`) oraz politykę czyszczenia cache.

## Checklista pipeline'u runtime

- [ ] Włącz globalny semafor limitujący zapytania do OpenAI (`MAX_OPENAI_CONCURRENCY`).
- [ ] Zaimplementuj per-user semafor/sekwencer zapobiegający kolizjom aktualizacji kontekstu.
- [ ] Zaimplementuj mapowanie PII i przechowuj je w `secure/pii_map.json` z ograniczonym dostępem.
- [ ] Rejestrowanie retry i fallbacków do lokalnego modelu dla `run_parallel_simplify`.
- [ ] Emitowanie progresywnych eventów (`DocumentQueued`, `SegmentSimplified`, `Validation*`, `ExportsUpdated`).
- [ ] Walidacja segmentów z logiką `needs_review` oraz ścieżką feedbacku użytkownika.
- [ ] Aktualizacja kontekstu lokalnego LLM po zatwierdzeniu segmentów (embeddingi, pamięć, cache promptów).

## Checklista Q&A i eksportu

- [ ] Publikuj zatwierdzone segmenty do indeksu RAG (Elastic/FAISS) z filtrami per użytkownik.
- [ ] Zapewnij dostęp modułu Q&A do aktualnego snapshotu kontekstu i historii feedbacku.
- [ ] Generuj eksporty (PDF/DOCX/Markdown) na podstawie `simplified/` i zapisuj je w `exports/` wraz z metadanymi rewizji.
- [ ] Wysyłaj event `ExportsUpdated` po każdej zmianie, aby frontend odświeżał listę plików.
