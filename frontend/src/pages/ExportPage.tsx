import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { API_BASE_URL } from '../config';

const EXPORT_FORMATS = [
  { value: 'markdown', label: 'Markdown (.md)', mime: 'text/markdown' },
  { value: 'pdf', label: 'PDF (.pdf)', mime: 'application/pdf' },
  { value: 'docx', label: 'Word (.docx)', mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }
];

function ExportPage() {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const [format, setFormat] = useState('markdown');
  const [restorePii, setRestorePii] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = 'Eksport dokumentu – ProstePrawo';
    return () => {
      document.title = 'ProstePrawo';
    };
  }, []);

  const handleExport = async () => {
    if (!documentId) {
      return;
    }
    setIsDownloading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ format, restore_pii: restorePii ? 'true' : 'false' });
      const response = await fetch(`${API_BASE_URL}/documents/${documentId}/export?${params.toString()}`);
      if (!response.ok) {
        const details = await response.text();
        throw new Error(details || 'Nie udało się wygenerować eksportu.');
      }
      const disposition = response.headers.get('content-disposition');
      const extension = format === 'markdown' ? 'md' : format;
      const filename = disposition?.match(/filename="?([^";]+)"?/)?.[1] ?? `export-${documentId}.${extension}`;
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nieznany błąd eksportu.');
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="export-page">
      <header className="export-header">
        <button type="button" onClick={() => navigate(-1)}>
          ← Wróć do dokumentu
        </button>
        <h1>Eksport dokumentu</h1>
      </header>
      <section className="panel">
        <h2>Format pliku</h2>
        <div className="export-options">
          {EXPORT_FORMATS.map((option) => (
            <label key={option.value}>
              <input
                type="radio"
                name="export-format"
                value={option.value}
                checked={format === option.value}
                onChange={(event) => setFormat(event.target.value)}
              />
              {option.label}
            </label>
          ))}
        </div>
        <label className="restore-toggle">
          <input type="checkbox" checked={restorePii} onChange={(event) => setRestorePii(event.target.checked)} />
          Przywróć PII w eksporcie (tylko lokalnie)
        </label>
        <p className="hint">
          Zaznaczenie tej opcji spowoduje próbę odtworzenia zanonimizowanych danych w wygenerowanym pliku. Wymaga
          dostępności mapy PII zapisanej podczas przetwarzania dokumentu.
        </p>
        <button type="button" onClick={handleExport} disabled={isDownloading}>
          {isDownloading ? 'Generowanie...' : 'Generuj plik'}
        </button>
        {error && <p className="error-message">{error}</p>}
      </section>
    </div>
  );
}

export default ExportPage;
