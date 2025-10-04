import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { API_BASE_URL } from '../config';
import SectionViewer from '../components/SectionViewer';
import QaModal from '../components/QaModal';
import CostOverviewPanel from '../components/CostOverviewPanel';
import type {
  DocumentMetadataPublic,
  SectionSimplification,
  SimplifiedResponse
} from '../types';

function ReaderPage() {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const [metadata, setMetadata] = useState<DocumentMetadataPublic | null>(null);
  const [sections, setSections] = useState<SectionSimplification[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sideBySide, setSideBySide] = useState(true);
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [showQa, setShowQa] = useState(false);

  useEffect(() => {
    if (!documentId) {
      return;
    }
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const [metaResponse, simplifiedResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/documents/${documentId}`),
          fetch(`${API_BASE_URL}/documents/${documentId}/simplified`)
        ]);
        if (metaResponse.status === 404) {
          setError('Nie znaleziono dokumentu.');
          setIsLoading(false);
          return;
        }
        if (!metaResponse.ok || !simplifiedResponse.ok) {
          throw new Error('Nie udało się pobrać danych dokumentu.');
        }
        const metaJson: DocumentMetadataPublic = await metaResponse.json();
        const simplifiedJson: SimplifiedResponse = await simplifiedResponse.json();
        setMetadata(metaJson);
        setSections(simplifiedJson.sections);
        setActiveSection(simplifiedJson.sections[0]?.identifier ?? null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Wystąpił nieznany błąd.');
      } finally {
        setIsLoading(false);
      }
    };

    void fetchData();
  }, [documentId]);

  useEffect(() => {
    if (activeSection) {
      const element = document.querySelector(`[data-section-id="${CSS.escape(activeSection)}"]`);
      element?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [activeSection]);

  const ready = metadata?.status === 'ready';

  const insights = useMemo(() => {
    if (!metadata) {
      return [];
    }
    return [
      { label: 'Obowiązki', data: metadata.obligations },
      { label: 'Kary', data: metadata.penalties },
      { label: 'Terminy', data: metadata.deadlines },
      { label: 'Ryzyka', data: metadata.risks }
    ];
  }, [metadata]);

  if (!documentId) {
    return <p>Brak identyfikatora dokumentu.</p>;
  }

  return (
    <div className="reader-page">
      <header className="reader-header">
        <div>
          <button type="button" onClick={() => navigate(-1)}>
            ← Wróć
          </button>
          <h1>{metadata?.title ?? 'Dokument'}</h1>
          <p>Status: {metadata?.status ?? 'ładowanie...'}</p>
        </div>
        <div className="reader-tools">
          <label>
            <input type="checkbox" checked={sideBySide} onChange={(event) => setSideBySide(event.target.checked)} />
            Widok równoległy
          </label>
          <button type="button" onClick={() => setShowQa(true)} disabled={!ready}>
            Q&amp;A
          </button>
          <Link to={`/documents/${documentId}/export`} className={`button ${ready ? '' : 'disabled'}`}>
            Eksport
          </Link>
        </div>
      </header>
      {isLoading && <p>Ładowanie dokumentu...</p>}
      {error && <p className="error-message">{error}</p>}
      {!isLoading && !error && (
        <>
          <SectionViewer
            sections={sections}
            activeIdentifier={activeSection}
            sideBySide={sideBySide}
            onSelect={setActiveSection}
          />
          <aside className="reader-insights">
            <CostOverviewPanel usage={metadata?.token_usage} isReady={ready} />
            <h2>Najważniejsze informacje</h2>
            {insights.map((group) => (
              <div key={group.label}>
                <h3>{group.label}</h3>
                {group.data.length > 0 ? (
                  <ul>
                    {group.data.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>Brak danych.</p>
                )}
              </div>
            ))}
          </aside>
        </>
      )}
      {showQa && (
        <QaModal
          documentId={documentId}
          onClose={() => setShowQa(false)}
          onHighlightSource={(identifier) => setActiveSection(identifier)}
        />
      )}
    </div>
  );
}

export default ReaderPage;
