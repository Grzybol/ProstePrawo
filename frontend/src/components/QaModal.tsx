import { useEffect, useMemo, useState } from 'react';
import { API_BASE_URL } from '../config';
import type { QaResponse } from '../types';

interface QaModalProps {
  documentId: string;
  onClose: () => void;
  onHighlightSource: (identifier: string) => void;
}

function extractSources(answer: string): string[] {
  const marker = 'Źródła:';
  const index = answer.indexOf(marker);
  if (index === -1) {
    return [];
  }
  return answer
    .slice(index + marker.length)
    .split(/[.,]/)
    .map((part) => part.trim())
    .filter((item) => item.length > 0);
}

function QaModal({ documentId, onClose, onHighlightSource }: QaModalProps) {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<QaResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setQuestion('Jakie mam obowiązki?');
  }, []);

  const sources = useMemo(() => extractSources(answer?.answer ?? ''), [answer]);

  const askQuestion = async () => {
    if (!question.trim()) {
      setError('Zadaj pytanie, aby otrzymać odpowiedź.');
      return;
    }
    setIsLoading(true);
    setError(null);
    setAnswer(null);
    try {
      const params = new URLSearchParams({ question });
      const response = await fetch(`${API_BASE_URL}/documents/${documentId}/qa?${params.toString()}`, {
        credentials: 'include'
      });
      if (!response.ok) {
        throw new Error('Nie udało się pobrać odpowiedzi.');
      }
      const data: QaResponse = await response.json();
      setAnswer(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nieznany błąd.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal">
        <header className="modal-header">
          <h2>Zapytaj dokument</h2>
          <button type="button" onClick={onClose} className="close-button" aria-label="Zamknij">
            ×
          </button>
        </header>
        <div className="modal-content">
          <label htmlFor="qa-question">Pytanie</label>
          <textarea
            id="qa-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={3}
            placeholder="Opisz czego chcesz się dowiedzieć..."
          />
          <button type="button" onClick={askQuestion} disabled={isLoading}>
            {isLoading ? 'Szukanie...' : 'Szukaj odpowiedzi'}
          </button>
          {error && <p className="error-message">{error}</p>}
          {answer && (
            <div className="qa-answer">
              <p>{answer.answer}</p>
              {sources.length > 0 && (
                <div className="qa-sources">
                  <strong>Źródła:</strong>
                  <ul>
                    {sources.map((source) => (
                      <li key={source}>
                        <button type="button" onClick={() => onHighlightSource(source)}>
                          {source}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default QaModal;
