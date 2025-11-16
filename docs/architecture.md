# Architektura ProstePrawo (asynchroniczny pipeline)

## Cel

System przetwarza dokumenty prawne w sposób w pełni asynchroniczny: od wgrywania plików, przez sanitację, uproszczenia i walidację,
aż po aktualizację kontekstu lokalnego LLM. Celem jest zapewnienie separacji użytkowników, odporności na błędy modeli chmurowych
oraz możliwości równoległego przetwarzania wielu dokumentów przy kontrolowanym zużyciu zasobów.

## Orkiestracja pipeline'u (`process_document`)

Funkcja `process_document` stanowi centralny punkt uruchamiany po uploadzie. Działa w oddzielnym workerze i wykonuje kroki:

1. **Rejestracja zadania** – zapis metadanych dokumentu w bazie i utworzenie folderów `/data/{user_id}/{doc_id}` (podkatalogi
   `raw`, `preprocessed`, `secure`, `simplified`, `exports`).
2. **Preprocessing** – normalizacja/OCR, segmentacja struktury (art./§/ust.) i zapis wyników w `preprocessed/segments.json`.
3. **Sanitacja** – anonimizacja PII z mapą odwzorowań w `secure/pii_map.json`; artefakty jawne są dostępne tylko w kontekście
   użytkownika.
4. **Inicjalizacja kontekstu LLM** – odczyt profilu użytkownika i stanu lokalnych modeli z `/data/llm_store/{user_id}`.
5. **Uruchomienie uproszczeń** – przekazanie zanonimizowanych segmentów do `run_parallel_simplify` wraz z semaforem limitującym
   zewnętrzne zapytania.
6. **Walidacja i zapisy** – odbiór wyników z kolejki, walidacja reguł i zapis zatwierdzonych wersji w `simplified/`.
7. **Aktualizacja pamięci** – synchroniczna aktualizacja embeddingów i kontekstu lokalnego LLM na podstawie zaakceptowanych
   segmentów.
8. **Publikacja eventu zakończenia** – wysłanie zdarzenia do kanału progresu (WebSocket/SSE) i przygotowanie eksportów.

`process_document` korzysta z menedżera transakcji/locków tak, aby równoczesne zadania tego samego użytkownika nie kolidowały ze
sobą, a inni użytkownicy mogli korzystać z klastra niezależnie.

## Równoległe upraszczanie (`run_parallel_simplify`)

Funkcja `run_parallel_simplify` dzieli listę segmentów na porcje dostosowane do ograniczeń tokenów i limitów API. Każdy segment
jest:

- przekazywany do lokalnej kolejki asyncio,
- wykonywany równolegle do maksymalnej liczby połączeń (`MAX_OPENAI_CONCURRENCY`) chronionej semaforem,
- buforowany w pamięci podręcznej na poziomie użytkownika (cache promptów/odpowiedzi) w `/data/llm_store/{user_id}/cache.db`.

W przypadku błędów API zadanie jest ponawiane z jitterem i, po przekroczeniu limitu prób, przekazywane do lokalnego modelu LLM.
Wyniki są emitowane jako strumień eventów (`SimplifyChunkReady`) pozwalający frontendowi aktualizować UI bez oczekiwania na cały
pipeline.

## Walidacja i feedback

Walidator działa jako kolejny etap asynchroniczny. Dla każdego segmentu sprawdza m.in. kompletność cytatów, zgodność długości,
redakcję oraz brak wycieków PII. Segmenty, które nie przejdą walidacji, są oznaczane statusem `needs_review` i oczekują na
feedback użytkownika. UI może przesłać poprawki lub zaakceptować wynik, co wyzwala ponowne uruchomienie uproszczeń dla danej
porcji. Wszelkie komentarze zapisywane są w `feedback.json`, a historia decyzji trafia do audytu.

## Progresywne eventy i kanały powiadomień

Backend publikuje zdarzenia na kanałach SSE/WebSocket per użytkownik. Główne typy eventów to:

- `DocumentQueued`, `DocumentProcessing`, `DocumentReady` – statusy pipeline'u,
- `SegmentSimplified` – częściowe wyniki z `run_parallel_simplify`,
- `ValidationFailed` / `ValidationPassed` – informacja dla UI o koniecznych działaniach,
- `ExportsUpdated` – powiadomienie o gotowych artefaktach eksportu.

Eventy są wersjonowane i buforowane per użytkownik, aby nowo podłączony klient mógł odtworzyć kontekst.

## Separacja użytkowników i magazyny danych

Każdy użytkownik posiada wydzielone przestrzenie:

- katalog roboczy `/data/{user_id}/{doc_id}` z pełnym cyklem życia dokumentu,
- magazyn pamięci LLM `/data/llm_store/{user_id}` zawierający historię konwersacji, cache promptów oraz embeddingi,
- osobne rekordy w bazie (PostgreSQL/MariaDB) z kontrolą uprawnień i audytem.

Dzięki temu pipeline może pracować w trybie multi-tenant przy zachowaniu izolacji danych.

## Cache modeli lokalnych i fallback

Lokalne modele (np. Llama 3.1 8B) są ładowane na żądanie do cache współdzielonego między zadaniami, lecz przestrzenie wektorowe
są aktualizowane per użytkownik. Menedżer modeli pilnuje, by w pamięci znajdowały się jedynie aktywne modele; pozostałe są
zapisane na dysku w `models/`. Przy braku odpowiedzi API pipeline korzysta z lokalnej instancji poprzez zunifikowany interfejs,
co umożliwia seamless fallback.

## Ograniczenia równoległości

- Globalny semafor limituje liczbę równoległych zapytań do dostawcy chmurowego.
- Per-user semaphore zapobiega nadmiernemu obciążeniu lokalnego cache'u i gwarantuje kolejność aktualizacji pamięci.
- Zadania walidacji i aktualizacji pamięci są wykonywane w ograniczonej puli workerów CPU, aby uniknąć blokowania event-loopu.

Monitorowanie (Prometheus + structlog) rejestruje wykorzystanie semaforów oraz czasy etapów, co pozwala dynamicznie dostrajać
parametry.

## Integracja z Q&A i eksportem

Po zatwierdzeniu segmentów `process_document` publikuje finalny snapshot w magazynie RAG (Elastic + FAISS) oraz aktualizuje
kontekst lokalnego LLM. Moduł Q&A korzysta z tych danych, stosując filtry użytkownika, a eksport (PDF/DOCX/Markdown) generuje
pliki na podstawie najnowszego stanu katalogu `exports/`. Każdy eksport jest wersjonowany i oznaczony identyfikatorem rewizji
spójnym z historią walidacji.
