import { Link } from 'react-router-dom';
import type { DocumentListItem } from '../types';

interface DocumentListProps {
  documents: DocumentListItem[];
  isLoading: boolean;
  onRefresh: () => void;
}

function DocumentList({ documents, isLoading, onRefresh }: DocumentListProps) {
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
          <li key={document.document_id} className={`document-item status-${document.status}`}>
            <div>
              <p className="document-title">{document.title}</p>
              <p className="document-meta">
                Utworzono: {new Date(document.created_at).toLocaleString('pl-PL')} • Status: {document.status}
              </p>
            </div>
            <div className="document-actions">
              <Link to={`/documents/${document.document_id}`}>Otwórz</Link>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default DocumentList;
