# Roadmap

Roadmap opisuje rozwój aplikacji „Prawo w prostych słowach” od MVP po bardziej zaawansowane funkcje. Statusy: 🟢 ukończone, 🟡 w toku, ⚪ zaplanowane.

## Faza 0 – Infrastruktura projektowa (Q3 2024)

| Status | Element | Opis |
|--------|---------|------|
| 🟢 | Repozytorium i dokumentacja | Utworzenie repozytorium, README, architektura wstępna. |
| 🟡 | Podstawowa konfiguracja CI/CD | Przygotowanie pipeline'u lint/test/deploy (GitHub Actions). |
| ⚪ | Monitoring jakości kodu | Integracja z narzędziami typu pre-commit, mypy, ruff. |

## Faza 1 – MVP pipeline dokumentów (Q4 2024)

| Status | Element | Opis |
|--------|---------|------|
| ⚪ | Ingestion PDF/DOCX/URL | Implementacja ekstrakcji tekstu (PyMuPDF, pdfplumber, python-docx, parser HTML). |
| ⚪ | OCR dla skanów | Integracja ocrmypdf + Tesseract (pol+eng) z kolejką przetwarzania. |
| ⚪ | Segmentacja strukturalna | Podział na artykuły/§/ustępy/punkty i zapis metadanych. |
| ⚪ | Sanitizer/PII | Wykorzystanie Presidio z polskimi rozpoznawaczami (PESEL, NIP, adresy, kwoty). |
| ⚪ | Lokalny magazyn dokumentów | Przechowywanie zaszyfrowanych oryginałów i zanonimizowanych wersji roboczych. |

## Faza 2 – RAG i inference (Q1 2025)

| Status | Element | Opis |
|--------|---------|------|
| ⚪ | Indeks pełnotekstowy + wektorowy | Elasticsearch 8.x (BM25, k-NN) + fallback FAISS. |
| ⚪ | Embeddingi ONNX | Wdrożenie bge-m3 / multilingual-e5-small na CPU. |
| ⚪ | Pipeline RAG | Retrieve-then-read dla Q&A z cytatami do artykułów. |
| ⚪ | Uproszczenia plain-language | Prompting LLM (OpenAI + tryb lokalny) z kontrolą jakości i testami regresyjnymi. |
| ⚪ | Checklisty obowiązków/kar | Generowanie list i streszczeń z mapowaniem do jednostek redakcyjnych. |

## Faza 3 – Frontend i UX (Q2 2025)

| Status | Element | Opis |
|--------|---------|------|
| ⚪ | Dashboard uploadu | Drag & drop, historia dokumentów, statusy przetwarzania. |
| ⚪ | Reader side-by-side | Widok oryginał ↔ uproszczony, nawigacja po art./§/ust. |
| ⚪ | Moduł Q&A | Interaktywny czat z odpowiedziami i cytatami. |
| ⚪ | Sekcja „Co to dla mnie oznacza?” | Wizualizacja obowiązków, kar, terminów, definicji. |
| ⚪ | Eksport raportów | Generowanie PDF/DOCX/Markdown z możliwością wyboru stylu. |

## Faza 4 – Bezpieczeństwo i tryb enterprise (Q3 2025)

| Status | Element | Opis |
|--------|---------|------|
| ⚪ | Tryb „local-only” | Konfiguracja pracy bez dostępu do sieci dla modułów inference. |
| ⚪ | Audyt i wersjonowanie | Logowanie zanonimizowane, śledzenie zapytań, wersje dokumentów. |
| ⚪ | Uprawnienia i multi-tenancy | Role użytkowników, separacja danych klientów biznesowych. |
| ⚪ | Compliance i SLA | Mechanizmy zgodności (baner, disclaimery), alerting, monitoring. |

## Faza 5 – Rozszerzenia produktowe (Q4 2025)

| Status | Element | Opis |
|--------|---------|------|
| ⚪ | Generator umów plain-language | Wsparcie prawnika w tworzeniu umów z wersją uproszczoną. |
| ⚪ | API partnerskie | Udostępnienie funkcji RAG i uproszczeń jako usługi SaaS. |
| ⚪ | Analiza porównawcza | Różnice pomiędzy wersjami aktów prawnych (diff + alerty). |
| ⚪ | Integracje DMS | Połączenia z zewnętrznymi repozytoriami dokumentów i SSO. |

## Notatki operacyjne

- Aktualizacje roadmapy należy wprowadzać równolegle z większymi zmianami funkcjonalnymi.
- Zadania dziel na issue w GitHubie i linkuj je w tabelach roadmapy.
- Wszelkie decyzje architektoniczne dokumentuj w `docs/architecture.md` (ADR-y lub sekcje tematyczne).
