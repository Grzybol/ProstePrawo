import type { TokenUsageMetrics } from '../types';

interface CostOverviewPanelProps {
  usage?: TokenUsageMetrics;
  isReady: boolean;
}

const defaultUsage: TokenUsageMetrics = {
  prompt_tokens: 0,
  completion_tokens: 0,
  total_tokens: 0,
  cost_usd: 0
};

const CostOverviewPanel = ({ usage, isReady }: CostOverviewPanelProps) => {
  const metrics = usage ?? defaultUsage;
  const formattedCost = metrics.cost_usd.toLocaleString('pl-PL', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 4,
    maximumFractionDigits: 6
  });

  const cards = [
    { label: 'Tokeny promptu', value: metrics.prompt_tokens.toLocaleString('pl-PL') },
    { label: 'Tokeny odpowiedzi', value: metrics.completion_tokens.toLocaleString('pl-PL') },
    { label: 'Tokeny łącznie', value: metrics.total_tokens.toLocaleString('pl-PL') },
    { label: 'Szacowany koszt', value: formattedCost }
  ];

  return (
    <section className="cost-overview panel">
      <div className="cost-overview-header">
        <h2>Zużycie tokenów</h2>
        <span className={`cost-overview-badge ${isReady ? 'ready' : 'pending'}`}>
          {isReady ? 'Aktualne' : 'W trakcie'}
        </span>
      </div>
      <p className="cost-overview-subtitle">
        Monitoruj liczbę tokenów oraz orientacyjny koszt przetwarzania dokumentu przez OpenAI.
      </p>
      <div className="cost-overview-grid">
        {cards.map((card) => (
          <div key={card.label} className="cost-card">
            <span className="cost-card-value">{card.value}</span>
            <span className="cost-card-label">{card.label}</span>
          </div>
        ))}
      </div>
      {!isReady && (
        <p className="cost-overview-hint">Metryki pojawią się po zakończeniu przetwarzania dokumentu.</p>
      )}
    </section>
  );
};

export default CostOverviewPanel;
