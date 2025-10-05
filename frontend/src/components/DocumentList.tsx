import { Link } from 'react-router-dom';
import type { DocumentListItem } from '../types';

interface DocumentListProps {
  documents: DocumentListItem[];
  isLoading: boolean;
  onRefresh: () => void;
}

function DocumentList({ documents, isLoading, onRefresh }: DocumentListProps) {
  const formatNumber = (value: number | undefined | null) =>
    typeof value === 'number' && Number.isFinite(value)
      ? value.toLocaleString('pl-PL')
      : '—';

  const formatCurrency = (value: number | undefined | null) =>
    typeof value === 'number' && Number.isFinite(value)
      ? value.toLocaleString('pl-PL', { style: 'currency', currency: 'USD' })
      : '—';

  return (
    <section className="panel">
      <header className="panel-header">
        <h2>Twoje dokumenty</h2>
        <button type="button" onClick={onRefresh} disabled={isLoading}>
          Odśwież
        </button>
      </header>
      {isLoading && <p>Wczytywanie listy dokumentów...</p>}
      {!isLoading && documents.length === 0 && <p>Brak dokumentów. Prześlij plik aby rozpocząć analizę.</p>}
      <ul className="document-list">
        {documents.map((document) => (
          <li key={document.doc_id} className={`document-item status-${document.status}`}>
            <div className="document-info">
              <div>
                <p className="document-title">{document.title}</p>
                <p className="document-meta">
                  Utworzono: {new Date(document.created_at).toLocaleString('pl-PL')} • Status: {document.status}
                </p>
              </div>
              {document.status === 'ready' && document.token_usage && (
                <dl className="document-usage">
                  <div>
                    <dt>Prompt tokens</dt>
                    <dd>{formatNumber(document.token_usage.prompt_tokens)}</dd>
                  </div>
                  <div>
                    <dt>Completion tokens</dt>
                    <dd>{formatNumber(document.token_usage.completion_tokens)}</dd>
                  </div>
                  <div>
                    <dt>Łącznie tokenów</dt>
                    <dd>{formatNumber(document.token_usage.total_tokens)}</dd>
                  </div>
                  <div>
                    <dt>Koszt</dt>
                    <dd>{formatCurrency(document.token_usage.cost_usd)}</dd>
                  </div>
                </dl>
              )}
            </div>
            <div className="document-actions">
              <Link to={`/documents/${document.doc_id}`}>Otwórz</Link>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default DocumentList;
