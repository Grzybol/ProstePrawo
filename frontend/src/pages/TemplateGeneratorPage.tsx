import { FormEvent, useCallback, useMemo, useState } from 'react';
import { API_BASE_URL } from '../config';
import type { TemplateGenerationResponse } from '../types';

const DEFAULT_COUNTRY = 'PL';

function TemplateGeneratorPage() {
  const [prompt, setPrompt] = useState('');
  const [country, setCountry] = useState(DEFAULT_COUNTRY);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TemplateGenerationResponse | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  const isSubmitDisabled = useMemo(() => isSubmitting || prompt.trim().length < 3, [isSubmitting, prompt]);

  const parseErrorMessage = useCallback(async (response: Response) => {
    try {
      const data = await response.json();
      if (typeof data?.detail === 'string') {
        return data.detail;
      }
      if (Array.isArray(data?.detail)) {
        const messages = data.detail
          .map((item: unknown) => {
            if (item && typeof item === 'object' && 'msg' in item && typeof (item as { msg: unknown }).msg === 'string') {
              return (item as { msg: string }).msg;
            }
            return null;
          })
          .filter((item): item is string => Boolean(item));
        if (messages.length > 0) {
          return messages.join(' ');
        }
      }
    } catch (jsonError) {
      console.warn('Nie udało się zdekodować odpowiedzi serwera.', jsonError);
    }
    return 'Nie udało się wygenerować wzoru dokumentu. Spróbuj ponownie później.';
  }, []);

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (isSubmitDisabled) {
        return;
      }

      setIsSubmitting(true);
      setError(null);
      setCopyFeedback(null);

      try {
        const response = await fetch(`${API_BASE_URL}/templates/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          credentials: 'include',
          body: JSON.stringify({ prompt: prompt.trim(), country })
        });

        if (!response.ok) {
          throw new Error(await parseErrorMessage(response));
        }

        const data: TemplateGenerationResponse = await response.json();
        setResult(data);
      } catch (submissionError) {
        setResult(null);
        setError(submissionError instanceof Error ? submissionError.message : 'Wystąpił nieoczekiwany błąd.');
      } finally {
        setIsSubmitting(false);
      }
    },
    [country, isSubmitDisabled, parseErrorMessage, prompt]
  );

  const handleCopy = useCallback(async () => {
    if (!result?.template) {
      return;
    }
    try {
      await navigator.clipboard.writeText(result.template);
      setCopyFeedback('Skopiowano wzór dokumentu do schowka.');
    } catch (copyError) {
      console.error(copyError);
      setCopyFeedback('Nie udało się skopiować treści.');
    }
  }, [result]);

  return (
    <div className="template-generator">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h1>Generuj wzór dokumentu</h1>
            <p className="panel-subtitle">Opisz, jakiego dokumentu potrzebujesz, aby otrzymać wstępną templatkę do dalszej edycji.</p>
          </div>
        </div>
        <form className="template-form" onSubmit={handleSubmit}>
          <label className="form-field" htmlFor="template-prompt">
            Opis dokumentu
            <textarea
              id="template-prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Przykład: Umowa współpracy marketingowej pomiędzy agencją a freelancerem w Polsce."
              rows={8}
            />
          </label>
          <div className="template-form-row">
            <label className="select-field" htmlFor="template-country">
              Jurysdykcja
              <select id="template-country" value={country} onChange={(event) => setCountry(event.target.value)}>
                <option value="PL">Polska (PL)</option>
              </select>
            </label>
            <button type="submit" disabled={isSubmitDisabled}>
              {isSubmitting ? 'Generowanie...' : 'Wygeneruj wzór'}
            </button>
          </div>
          {error ? <p className="form-error">{error}</p> : null}
          <p className="form-hint">System obecnie obsługuje generowanie wzorów dla polskiej jurysdykcji.</p>
        </form>
      </section>

      {result ? (
        <section className="panel template-result">
          <div className="panel-header">
            <div>
              <h2>Twoja templatka dokumentu</h2>
              <p className="panel-subtitle">Skopiuj i dopasuj treść do swoich potrzeb, uzupełniając oznaczone pola.</p>
            </div>
            <button type="button" className="button-link" onClick={handleCopy}>
              Skopiuj treść
            </button>
          </div>
          {copyFeedback ? <p className="status-message">{copyFeedback}</p> : null}
          <article className="template-output">{result.template}</article>
          <div className="token-usage" aria-live="polite">
            <h3>Zużycie tokenów</h3>
            <div className="token-usage-grid">
              <div>
                <span className="token-usage-label">Prompt</span>
                <span className="token-usage-value">{result.token_usage.prompt_tokens}</span>
              </div>
              <div>
                <span className="token-usage-label">Odpowiedź</span>
                <span className="token-usage-value">{result.token_usage.completion_tokens}</span>
              </div>
              <div>
                <span className="token-usage-label">Łącznie</span>
                <span className="token-usage-value">{result.token_usage.total_tokens}</span>
              </div>
              <div>
                <span className="token-usage-label">Koszt (USD)</span>
                <span className="token-usage-value">{result.token_usage.cost_usd.toFixed(4)}</span>
              </div>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}

export default TemplateGeneratorPage;
