# ProstePrawo

Mobilny i webowy asystent, który importuje akty prawne, umowy czy regulaminy i tłumaczy je na język zrozumiały dla przeciętnej osoby.

## Struktura repozytorium

```
backend/
  app/
    api/        # definicje tras FastAPI
    core/       # konfiguracja i komponenty globalne
    models/     # modele Pydantic i encje domenowe
    services/   # serwisy biznesowe (pipeline, RAG, itp.)
  requirements.txt
```

Dodatkowe materiały architektoniczne znajdują się w `docs/architecture.md`.

## Uruchomienie backendu (MVP)

1. Utwórz środowisko wirtualne i zainstaluj zależności:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Uruchom serwer deweloperski:
   ```bash
   uvicorn app.main:app --reload
   ```

3. Otwórz dokumentację interaktywną: [http://localhost:8000/docs](http://localhost:8000/docs).

## Kolejne kroki

- Zaimplementowanie rzeczywistego pipeline'u (OCR, sanitizacja, indeksacja, RAG).
- Dołączenie frontendu React (Vite + Tailwind + shadcn/ui) serwowanego jako statyczne pliki.
- Konfiguracja ElasticSearch/FAISS oraz lokalnego trybu "air-gap".
- Automatyzacja eksportu (PDF/DOCX/Markdown) i logowania zdarzeń.
