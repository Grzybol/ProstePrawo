const {
  useState,
  useEffect,
  useMemo,
  useCallback,
  useRef
} = React;
const {
  BrowserRouter,
  Routes,
  Route,
  Link,
  NavLink,
  useLocation,
  useNavigate,
  useParams
} = ReactRouterDOM;
const Fragment = React.Fragment;
const e = React.createElement;

const API_BASE_URL = (() => {
  const globalOverride = typeof window !== 'undefined' && window.__API_BASE_URL__ ? String(window.__API_BASE_URL__) : null;
  const metaValue = document.querySelector('meta[name="api-base-url"]')?.content?.trim();
  const fallback = 'http://localhost:8000/api';
  const base = globalOverride || metaValue || fallback;
  return base.endsWith('/') ? base.slice(0, -1) : base;
})();

function UploadZone({ onUploadComplete }) {
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  const uploadFiles = useCallback(
    async (files) => {
      if (!files || files.length === 0) {
        return;
      }
      const file = files[0];
      const formData = new FormData();
      formData.append('file', file);
      setIsUploading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/documents/`, {
          method: 'POST',
          body: formData,
          credentials: 'include'
        });
        if (!response.ok) {
          const message = await response.text();
          throw new Error(message || 'Nie udało się przesłać pliku.');
        }
        onUploadComplete();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Nieznany błąd przesyłania.');
      } finally {
        setIsUploading(false);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      }
    },
    [onUploadComplete]
  );

  const handleDrop = useCallback(
    async (event) => {
      event.preventDefault();
      setIsDragging(false);
      await uploadFiles(event.dataTransfer?.files ?? null);
    },
    [uploadFiles]
  );

  const handleSelectFile = useCallback(async () => {
    await uploadFiles(fileInputRef.current?.files ?? null);
  }, [uploadFiles]);

  const acceptedTypes = ['.pdf', '.txt', '.md', '.docx'];

  return e(
    'div',
    { className: 'upload-zone' },
    e(
      'div',
      {
        className: `drop-area ${isDragging ? 'dragging' : ''}`,
        onDragOver: (event) => {
          event.preventDefault();
          setIsDragging(true);
        },
        onDragLeave: () => setIsDragging(false),
        onDrop: handleDrop
      },
      e('p', null, 'Przeciągnij dokument tutaj lub wybierz z dysku.'),
      e(
        'button',
        {
          type: 'button',
          onClick: () => fileInputRef.current?.click(),
          disabled: isUploading
        },
        isUploading ? 'Przesyłanie...' : 'Wybierz plik'
      ),
      e('p', { className: 'hint' }, `Obsługiwane formaty: ${acceptedTypes.join(', ')}`),
      e('input', {
        ref: fileInputRef,
        type: 'file',
        accept: acceptedTypes.join(','),
        hidden: true,
        onChange: handleSelectFile
      })
    ),
    error ? e('p', { className: 'error-message' }, error) : null
  );
}

function DocumentList({ documents, isLoading, onRefresh }) {
  const formatNumber = (value) =>
    typeof value === 'number' && Number.isFinite(value)
      ? value.toLocaleString('pl-PL')
      : '—';

  const formatCurrency = (value) =>
    typeof value === 'number' && Number.isFinite(value)
      ? value.toLocaleString('pl-PL', { style: 'currency', currency: 'USD' })
      : '—';

  return e(
    'section',
    { className: 'panel' },
    e(
      'header',
      { className: 'panel-header' },
      e('h2', null, 'Twoje dokumenty'),
      e(
        'button',
        { type: 'button', onClick: onRefresh, disabled: isLoading },
        'Odśwież'
      )
    ),
    isLoading ? e('p', null, 'Wczytywanie listy dokumentów...') : null,
    !isLoading && documents.length === 0
      ? e('p', null, 'Brak dokumentów. Prześlij plik aby rozpocząć analizę.')
      : null,
    e(
      'ul',
      { className: 'document-list' },
      ...documents.map((document) =>
        e(
          'li',
          {
            key: document.doc_id,
            className: `document-item status-${document.status}`
          },
          e(
            'div',
            { className: 'document-info' },
            e(
              'div',
              null,
              e('p', { className: 'document-title' }, document.title),
              e(
                'p',
                { className: 'document-meta' },
                `Utworzono: ${new Date(document.created_at).toLocaleString('pl-PL')} • Status: ${document.status}`
              )
            ),
            document.status === 'ready' && document.token_usage
              ? e(
                  'dl',
                  { className: 'document-usage' },
                  e(
                    'div',
                    null,
                    e('dt', null, 'Prompt tokens'),
                    e('dd', null, formatNumber(document.token_usage.prompt_tokens))
                  ),
                  e(
                    'div',
                    null,
                    e('dt', null, 'Completion tokens'),
                    e('dd', null, formatNumber(document.token_usage.completion_tokens))
                  ),
                  e(
                    'div',
                    null,
                    e('dt', null, 'Łącznie tokenów'),
                    e('dd', null, formatNumber(document.token_usage.total_tokens))
                  ),
                  e(
                    'div',
                    null,
                    e('dt', null, 'Koszt'),
                    e('dd', null, formatCurrency(document.token_usage.cost_usd))
                  )
                )
              : null
          ),
          e(
            'div',
            { className: 'document-actions' },
            e(
              Link,
              { to: `/documents/${document.doc_id}` },
              'Otwórz'
            )
          )
        )
      )
    )
  );
}

function DashboardPage() {
  const [documents, setDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const loadDocuments = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/documents/`, {
        credentials: 'include'
      });
      if (!response.ok) {
        throw new Error('Nie udało się pobrać dokumentów.');
      }
      const data = await response.json();
      setDocuments(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  return e(
    'div',
    { className: 'dashboard' },
    e(
      'section',
      { className: 'panel' },
      e('h1', null, 'Panel dokumentów'),
      e(
        'p',
        null,
        'Prześlij dokument aby uruchomić przetwarzanie. Analiza odbywa się lokalnie w środowisku PoC, dlatego odświeżaj listę, aby obserwować status.'
      ),
      e(UploadZone, { onUploadComplete: loadDocuments })
    ),
    e(DocumentList, { documents, isLoading, onRefresh: loadDocuments })
  );
}

function SectionViewer({ sections, activeIdentifier, sideBySide, onSelect }) {
  if (!sections || sections.length === 0) {
    return e('p', null, 'Brak uproszczonych sekcji dla tego dokumentu.');
  }

  if (sideBySide) {
    return e(
      'div',
      { className: 'reader split' },
      e(
        'div',
        { className: 'reader-column' },
        e('h3', null, 'Oryginał'),
        e(
          'ul',
          { className: 'section-list' },
          ...sections.map((section) =>
            e(
              'li',
              {
                key: section.identifier,
                className: section.identifier === activeIdentifier ? 'active' : '',
                'data-section-id': section.identifier,
                onClick: () => onSelect(section.identifier)
              },
              e('header', null, e('strong', null, section.identifier)),
              e('p', null, section.source_text)
            )
          )
        )
      ),
      e(
        'div',
        { className: 'reader-column' },
        e('h3', null, 'W prostych słowach'),
        e(
          'ul',
          { className: 'section-list' },
          ...sections.map((section) =>
            e(
              'li',
              {
                key: `${section.identifier}-plain`,
                className: section.identifier === activeIdentifier ? 'active' : '',
                'data-section-id': section.identifier
              },
              e('header', null, e('strong', null, section.identifier)),
              e('p', null, section.plain_language)
            )
          )
        )
      )
    );
  }

  return e(
    'div',
    { className: 'reader single' },
    e(
      'div',
      { className: 'reader-column' },
      e('h3', null, 'W prostych słowach'),
      e(
        'ul',
        { className: 'section-list' },
        ...sections.map((section) =>
          e(
            'li',
            {
              key: `${section.identifier}-solo`,
              className: section.identifier === activeIdentifier ? 'active' : '',
              'data-section-id': section.identifier,
              onClick: () => onSelect(section.identifier)
            },
            e('header', null, e('strong', null, section.identifier)),
            e('p', null, section.plain_language),
            e(
              'details',
              null,
              e('summary', null, 'Fragment oryginału'),
              e('p', null, section.source_text)
            )
          )
        )
      )
    )
  );
}

function QaModal({ documentId, onClose, onHighlightSource }) {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setQuestion('Jakie mam obowiązki?');
  }, []);

  const sources = useMemo(() => {
    const text = answer?.answer ?? '';
    const marker = 'Źródła:';
    const index = text.indexOf(marker);
    if (index === -1) {
      return [];
    }
    return text
      .slice(index + marker.length)
      .split(/[.,]/)
      .map((part) => part.trim())
      .filter((item) => item.length > 0);
  }, [answer]);

  const askQuestion = useCallback(async () => {
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
      const data = await response.json();
      setAnswer(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nieznany błąd.');
    } finally {
      setIsLoading(false);
    }
  }, [documentId, question]);

  return e(
    'div',
    { className: 'modal-backdrop', role: 'dialog', 'aria-modal': 'true' },
    e(
      'div',
      { className: 'modal' },
      e(
        'header',
        { className: 'modal-header' },
        e('h2', null, 'Zapytaj dokument'),
        e(
          'button',
          {
            type: 'button',
            onClick: onClose,
            className: 'close-button',
            'aria-label': 'Zamknij'
          },
          '×'
        )
      ),
      e(
        'div',
        { className: 'modal-content' },
        e('label', { htmlFor: 'qa-question' }, 'Pytanie'),
        e('textarea', {
          id: 'qa-question',
          value: question,
          onChange: (event) => setQuestion(event.target.value),
          rows: 3,
          placeholder: 'Opisz czego chcesz się dowiedzieć...'
        }),
        e(
          'button',
          { type: 'button', onClick: askQuestion, disabled: isLoading },
          isLoading ? 'Szukanie...' : 'Szukaj odpowiedzi'
        ),
        error ? e('p', { className: 'error-message' }, error) : null,
        answer
          ? e(
              'div',
              { className: 'qa-answer' },
              e('p', null, answer.answer),
              sources.length > 0
                ? e(
                    'div',
                    { className: 'qa-sources' },
                    e('strong', null, 'Źródła:'),
                    e(
                      'ul',
                      null,
                      ...sources.map((source) =>
                        e(
                          'li',
                          { key: source },
                          e(
                            'button',
                            { type: 'button', onClick: () => onHighlightSource(source) },
                            source
                          )
                        )
                      )
                    )
                  )
                : null
            )
          : null
      )
    )
  );
}

function ReaderPage() {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const [metadata, setMetadata] = useState(null);
  const [sections, setSections] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sideBySide, setSideBySide] = useState(true);
  const [activeSection, setActiveSection] = useState(null);
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
          fetch(`${API_BASE_URL}/documents/${documentId}`, { credentials: 'include' }),
          fetch(`${API_BASE_URL}/documents/${documentId}/simplified`, { credentials: 'include' })
        ]);
        if (metaResponse.status === 404) {
          setError('Nie znaleziono dokumentu.');
          setIsLoading(false);
          return;
        }
        if (!metaResponse.ok || !simplifiedResponse.ok) {
          throw new Error('Nie udało się pobrać danych dokumentu.');
        }
        const metaJson = await metaResponse.json();
        const simplifiedJson = await simplifiedResponse.json();
        setMetadata(metaJson);
        const sectionList = Array.isArray(simplifiedJson.sections) ? simplifiedJson.sections : [];
        setSections(sectionList);
        setActiveSection(sectionList[0]?.identifier ?? null);
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
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  }, [activeSection]);

  const ready = metadata && metadata.status === 'ready';

  const insights = useMemo(() => {
    if (!metadata) {
      return [];
    }
    return [
      { label: 'Obowiązki', data: metadata.obligations ?? [] },
      { label: 'Kary', data: metadata.penalties ?? [] },
      { label: 'Terminy', data: metadata.deadlines ?? [] },
      { label: 'Ryzyka', data: metadata.risks ?? [] }
    ];
  }, [metadata]);

  if (!documentId) {
    return e('p', null, 'Brak identyfikatora dokumentu.');
  }

  return e(
    'div',
    { className: 'reader-page' },
    e(
      'header',
      { className: 'reader-header' },
      e(
        'div',
        null,
        e(
          'button',
          { type: 'button', onClick: () => navigate(-1) },
          '← Wróć'
        ),
        e('h1', null, metadata?.title ?? 'Dokument'),
        e('p', null, `Status: ${metadata?.status ?? 'ładowanie...'}`)
      ),
      e(
        'div',
        { className: 'reader-tools' },
        e(
          'label',
          null,
          e('input', {
            type: 'checkbox',
            checked: sideBySide,
            onChange: (event) => setSideBySide(event.target.checked)
          }),
          ' Widok równoległy'
        ),
        e(
          'button',
          { type: 'button', onClick: () => setShowQa(true), disabled: !ready },
          'Q&A'
        ),
        e(
          Link,
          { to: `/documents/${documentId}/export`, className: `button ${ready ? '' : 'disabled'}` },
          'Eksport'
        )
      )
    ),
    isLoading ? e('p', null, 'Ładowanie dokumentu...') : null,
    error ? e('p', { className: 'error-message' }, error) : null,
    !isLoading && !error
      ? e(
          Fragment,
          null,
          e(SectionViewer, {
            sections,
            activeIdentifier: activeSection,
            sideBySide,
            onSelect: setActiveSection
          }),
          e(
            'aside',
            { className: 'reader-insights' },
            e('h2', null, 'Najważniejsze informacje'),
            ...insights.map((group) =>
              e(
                'div',
                { key: group.label },
                e('h3', null, group.label),
                group.data.length > 0
                  ? e(
                      'ul',
                      null,
                      ...group.data.map((item) => e('li', { key: item }, item))
                    )
                  : e('p', null, 'Brak danych.')
              )
            )
          )
        )
      : null,
    showQa
      ? e(QaModal, {
          documentId,
          onClose: () => setShowQa(false),
          onHighlightSource: (identifier) => setActiveSection(identifier)
        })
      : null
  );
}

const EXPORT_FORMATS = [
  { value: 'markdown', label: 'Markdown (.md)', mime: 'text/markdown' },
  { value: 'pdf', label: 'PDF (.pdf)', mime: 'application/pdf' },
  {
    value: 'docx',
    label: 'Word (.docx)',
    mime: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  }
];

function ExportPage() {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const [format, setFormat] = useState('markdown');
  const [restorePii, setRestorePii] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = 'Eksport dokumentu – ProstePrawo';
    return () => {
      document.title = previousTitle;
    };
  }, []);

  const handleExport = useCallback(async () => {
    if (!documentId) {
      return;
    }
    setIsDownloading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        format,
        restore_pii: restorePii ? 'true' : 'false'
      });
      const response = await fetch(`${API_BASE_URL}/documents/${documentId}/export?${params.toString()}`, {
        credentials: 'include'
      });
      if (!response.ok) {
        const details = await response.text();
        throw new Error(details || 'Nie udało się wygenerować eksportu.');
      }
      const disposition = response.headers.get('content-disposition');
      const extension = format === 'markdown' ? 'md' : format;
      const fallbackName = `export-${documentId}.${extension}`;
      const filename = disposition?.match(/filename="?([^";]+)"?/i)?.[1] ?? fallbackName;
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
  }, [documentId, format, restorePii]);

  return e(
    'div',
    { className: 'export-page' },
    e(
      'header',
      { className: 'export-header' },
      e(
        'button',
        { type: 'button', onClick: () => navigate(-1) },
        '← Wróć do dokumentu'
      ),
      e('h1', null, 'Eksport dokumentu')
    ),
    e(
      'section',
      { className: 'panel' },
      e('h2', null, 'Format pliku'),
      e(
        'div',
        { className: 'export-options' },
        ...EXPORT_FORMATS.map((option) =>
          e(
            'label',
            { key: option.value },
            e('input', {
              type: 'radio',
              name: 'export-format',
              value: option.value,
              checked: format === option.value,
              onChange: (event) => setFormat(event.target.value)
            }),
            option.label
          )
        )
      ),
      e(
        'label',
        { className: 'restore-toggle' },
        e('input', {
          type: 'checkbox',
          checked: restorePii,
          onChange: (event) => setRestorePii(event.target.checked)
        }),
        ' Przywróć PII w eksporcie (tylko lokalnie)'
      ),
      e(
        'p',
        { className: 'hint' },
        'Zaznaczenie tej opcji spowoduje próbę odtworzenia zanonimizowanych danych w wygenerowanym pliku. Wymaga dostępności mapy PII zapisanej podczas przetwarzania dokumentu.'
      ),
      e(
        'button',
        { type: 'button', onClick: handleExport, disabled: isDownloading },
        isDownloading ? 'Generowanie...' : 'Generuj plik'
      ),
      error ? e('p', { className: 'error-message' }, error) : null
    )
  );
}

function App() {
  const location = useLocation();

  return e(
    'div',
    { className: 'app-shell' },
    e(
      'header',
      { className: 'app-header' },
      e(
        Link,
        { to: '/', className: 'app-logo' },
        'ProstePrawo'
      ),
      e(
        'nav',
        null,
        e(
          NavLink,
          {
            to: '/',
            className: ({ isActive }) => (isActive && location.pathname === '/' ? 'active' : '')
          },
          'Dashboard'
        )
      )
    ),
    e(
      'main',
      { className: 'app-main' },
      e(
        Routes,
        null,
        e(Route, { path: '/', element: e(DashboardPage) }),
        e(Route, { path: '/documents/:documentId', element: e(ReaderPage) }),
        e(Route, { path: '/documents/:documentId/export', element: e(ExportPage) })
      )
    )
  );
}

function bootstrap() {
  const container = document.getElementById('root');
  if (!container) {
    return;
  }
  const root = ReactDOM.createRoot(container);
  root.render(e(React.StrictMode, null, e(BrowserRouter, null, e(App))));
}

document.addEventListener('DOMContentLoaded', bootstrap);
