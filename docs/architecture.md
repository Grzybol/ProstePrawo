# Architektura ProstePrawo (MVP)

## Cel

Monolityczna aplikacja FastAPI z serwowanym statycznie frontendem React ma uprościć cykl przetwarzania aktów prawnych od etapu wgrywania plików, przez anonimizację, indeksację i RAG, po generowanie uproszczonych streszczeń oraz interaktywnych odpowiedzi.

## Główne moduły backendu

1. **Ingestion** – obsługa uploadów, konwersji PDF/DOCX/obrazów do tekstu, rekonstrukcja struktury (art./§/ust.).
2. **Sanitizer/PII** – anonimizacja danych wrażliwych (PESEL, NIP, nazwy własne) z wykorzystaniem Presidio i reguł regex.
3. **Indexing & RAG** – chunkowanie według jednostek redakcyjnych, obliczanie embeddingów (bge-m3/e5-small ONNX), zapis w Elastic lub FAISS.
4. **Inference** – moduły wywołujące LLM (OpenAI domyślnie, Llama 3.1 lokalnie) do uproszczeń, Q&A i list obowiązków/kar.
5. **Eksport** – generowanie raportów PDF/DOCX/Markdown, widok „oryginał vs. uproszczony”.
6. **Audit & Observability** – logowanie zdarzeń zanonimizowanych, wersjonowanie dokumentów, przechowywanie promptów i odpowiedzi.

## Warstwy implementacji

- `app/api` – punkty końcowe FastAPI do zarządzania cyklem dokumentów oraz Q&A.
- `app/services` – usługi dziedzinowe: pipeline, ingest, sanitizer, rag, inference, export.
- `app/models` – modele Pydantic służące jako kontrakty API i encje domenowe.
- `app/core` – konfiguracja (Pydantic BaseSettings), inicjalizacja loggera i połączeń.

## Przepływ danych (happy path)

1. Użytkownik wgrywa plik → `/documents`.
2. Pipeline zapisuje plik w `data/{docId}/raw`, tworzy rekord metadanych i rozpoczyna asynchroniczne przetwarzanie.
3. Ingestion normalizuje tekst, identyfikuje strukturę, wykrywa język i sekcje.
4. Sanitizer zamienia wrażliwe dane na tagi (<PESEL_1>, <IMIE_2>), zapisuje mapowanie w zaszyfrowanym magazynie.
5. Indeksowanie tworzy wektory + indeks BM25, zapisuje metadane (sygnatura, numer Dz.U., okres obowiązywania) w SQL/Elastic.
6. Moduł Inference generuje uproszczenia, streszczenia i listy obowiązków/kar, zapisuje cytowane jednostki.
7. Użytkownik może pobrać eksport (PDF/DOCX/Markdown) lub zadać pytanie Q&A z cytatem.

## Tryb „Local-Only”

- Wyłącza wywołania sieciowe modeli (OpenAI), używa lokalnych ONNX/llama.cpp.
- Wszystkie artefakty pozostają na VPS (folder `data/`).

## Roadmapa rozszerzeń

1. **MVP**: upload, podstawowe przetwarzanie, mock Q&A (jak w kodzie), podstawowy frontend.
2. **v0.2**: realny pipeline z OCR, sanitizacją, Elastic + FAISS, generacja streszczeń.
3. **v0.3**: interaktywny widok „oryginał vs. uproszczony”, definicje, listy obowiązków.
4. **v0.4**: eksport dokumentów, audyt zdarzeń, logowanie do Elastic.
5. **v1.0**: pełna obsługa multi-user, SSO, szyfrowanie at-rest, wersjonowanie dokumentów.
