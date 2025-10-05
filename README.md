# ProstePrawo

**ProstePrawo** to mobilny i webowy asystent, który tłumaczy język prawniczy na zrozumiały polski. System importuje akty prawne, umowy czy regulaminy, anonimizuje wrażliwe dane i udostępnia uproszczone wersje tekstów wraz z modułem pytań i odpowiedzi.

## Główne możliwości

- **Uproszczenie treści** – tłumaczenie artykułów, paragrafów i punktów na jasny język przy zachowaniu znaczenia i odwołań do jednostek redakcyjnych.
- **Q&A z odwołaniami** – odpowiedzi na pytania zadane w języku naturalnym wraz z cytatami do konkretnych artykułów/paragrafów.
- **Streszczenia i checklisty** – automatyczne listy obowiązków, ryzyk, kar oraz terminów wynikających z dokumentu.
- **Eksport** – generowanie raportów (PDF/DOCX/Markdown) i widoku „oryginał ↔ uproszczony”.
- **Tryb prywatności** – cały oryginalny dokument pozostaje lokalnie, a do modeli chmurowych wysyłany jest wyłącznie zanonimizowany tekst.

## Architektura (MVP → PRO)

Monolityczna aplikacja FastAPI z wbudowanym frontendem (React + Vite) obejmuje następujące warstwy logiczne:

1. **Ingestion** – import plików PDF, obrazów, DOCX oraz stron HTML; segmentacja na artykuły/§/ustępy/punkty.
2. **Sanitizer/PII** – anonimizacja danych wrażliwych (PESEL, NIP, adresy, kwoty, nazwy własne) przed przekazaniem tekstu do modeli.
3. **Indexing & RAG** – chunkowanie po jednostkach redakcyjnych, embeddingi, pełnotekstowe wyszukiwanie oraz zapis metadanych (sygnatura, Dz.U., daty obowiązywania).
4. **Inference** – uproszczenia w języku potocznym, moduł Q&A oraz generatory streszczeń i checklist.
5. **Eksport** – generowanie raportów w różnych formatach, widok porównawczy oraz API do pobrań.
6. **Audit & Observability** – logowanie (tylko tekst zanonimizowany), wersjonowanie dokumentów i ślady zapytań.

Szczegółowe diagramy i decyzje architektoniczne znajdują się w `docs/architecture.md`.

## Aktualny flow przetwarzania

1. **Upload** – plik trafia do katalogu `/data/{user_id}/{doc_id}/raw` wraz z metadanymi sesji.
2. **Preprocess** – normalizacja tekstu, OCR i wykrywanie struktury; wersja robocza przechowywana jest w `/data/{user_id}/{doc_id}/preprocessed`.
3. **Local LLM bootstrap** – inicjalizacja kontekstu użytkownika z pamięci w `/data/llm_store/{user_id}` oraz wczytanie cache modeli.
4. **Segmentation** – dzielenie na jednostki redakcyjne i tworzenie chunków roboczych (`segments.json`).
5. **Sanitize** – anonimizacja PII z mapowaniem zapisanym w `/data/{user_id}/{doc_id}/secure/pii_map.json`.
6. **Parallel OpenAI Simplify** – równoległe upraszczanie segmentów z użyciem funkcji `run_parallel_simplify`, z wynikami tymczasowymi w `/data/{user_id}/{doc_id}/simplified`.
7. **Validation/Feedback** – kontrola jakości i walidacja reguł (np. długość, kompletność cytatów), z komentarzami użytkownika w `feedback.json`.
8. **Local LLM update** – aktualizacja pamięci kontekstowej i embeddingów w magazynie per użytkownik (`/data/llm_store/{user_id}`) na podstawie zatwierdzonych segmentów.
9. **Live Q&A/Export** – wystawienie upraszczonego dokumentu do modułu zapytań i eksportów (PDF/DOCX/Markdown) z artefaktami w `/data/{user_id}/{doc_id}/exports`.

## Stos technologiczny

- **Backend:** Python 3.12, FastAPI, structlog/loguru, SQLite (MVP) / MariaDB, WeasyPrint.
- **OCR i ekstrakcja:** ocrmypdf, Tesseract (pol+eng), PyMuPDF, pdfplumber, python-docx.
- **Sanityzacja PII:** Presidio + niestandardowe rozpoznawacze PL.
- **RAG i wyszukiwanie:** Elasticsearch 8.x (BM25 + k-NN), FAISS (fallback), onnxruntime (embeddingi i reranker).
- **Modele LLM:** OpenAI (GPT-4.1/4o-mini) po anonimizacji oraz lokalne modele (Llama 3.1 8B, bge-m3/e5-small) w trybie „local-only”.
- **Frontend:** React + Vite (TypeScript), Tailwind CSS, shadcn/ui, pdf.js.

## Struktura repozytorium

```
backend/
  app/
    api/        # definicje tras FastAPI
    core/       # konfiguracja i komponenty globalne
    models/     # modele Pydantic i encje domenowe
    services/   # serwisy biznesowe (pipeline, RAG, itp.)
  requirements.txt
docs/
  architecture.md
README.md
roadmap.md (plan rozwoju)
```

## Uruchomienie backendu (MVP)

1. Utwórz środowisko wirtualne i zainstaluj zależności:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Skonfiguruj zmienne środowiskowe (np. `OPENAI_API_KEY`, ścieżki do Elasticsearch/FAISS) i katalog na pliki (`/data`).
   Możesz skopiować plik `.example.env` do `.env` i uzupełnić wartości zgodnie ze swoją konfiguracją.

3. Uruchom serwer deweloperski:
   ```bash
   uvicorn app.main:app --reload
   ```

4. Otwórz dokumentację interaktywną: [http://localhost:8000/docs](http://localhost:8000/docs).

## Uruchomienie w Dockerze

1. Zbuduj obraz oraz uruchom kontenery za pomocą Docker Compose:
   ```bash
   docker compose build
   docker compose up
   ```

2. W razie potrzeby ustaw zmienne środowiskowe (np. `OPENAI_API_KEY`) w pliku `.env` w katalogu głównym
   (najłatwiej skopiować `.example.env`) lub przekazuj je przy wywołaniu `docker compose`.

3. Domyślnie wolumen `./data` montowany jest do `/app/data` wewnątrz kontenera. Umożliwia to zachowanie wgrywanych dokumentów pomiędzy restartami. Dostosuj ścieżki lub usuń wolumen w `docker-compose.yml`, jeśli nie jest potrzebny.

## Dalszy rozwój

- Postępy i plan prac znajdziesz w pliku [`roadmap.md`](./roadmap.md).
- Sugestie i usprawnienia architektoniczne zapisuj w `docs/architecture.md`.

## Licencja

Licencja projektu zostanie określona na późniejszym etapie.
