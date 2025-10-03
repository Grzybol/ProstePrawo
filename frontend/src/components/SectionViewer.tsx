import type { SectionSimplification } from '../types';

interface SectionViewerProps {
  sections: SectionSimplification[];
  activeIdentifier: string | null;
  sideBySide: boolean;
  onSelect: (identifier: string) => void;
}

function SectionViewer({ sections, activeIdentifier, sideBySide, onSelect }: SectionViewerProps) {
  if (sections.length === 0) {
    return <p>Brak uproszczonych sekcji dla tego dokumentu.</p>;
  }

  if (sideBySide) {
    return (
      <div className="reader split">
        <div className="reader-column">
          <h3>Oryginał</h3>
          <ul className="section-list">
            {sections.map((section) => (
              <li
                key={section.identifier}
                className={section.identifier === activeIdentifier ? 'active' : ''}
                data-section-id={section.identifier}
                onClick={() => onSelect(section.identifier)}
              >
                <header>
                  <strong>{section.identifier}</strong>
                </header>
                <p>{section.source_text}</p>
              </li>
            ))}
          </ul>
        </div>
        <div className="reader-column">
          <h3>W prostych słowach</h3>
          <ul className="section-list">
            {sections.map((section) => (
              <li
                key={`${section.identifier}-plain`}
                className={section.identifier === activeIdentifier ? 'active' : ''}
                data-section-id={section.identifier}
              >
                <header>
                  <strong>{section.identifier}</strong>
                </header>
                <p>{section.plain_language}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    );
  }

  return (
    <div className="reader single">
      <div className="reader-column">
        <h3>W prostych słowach</h3>
        <ul className="section-list">
          {sections.map((section) => (
            <li
              key={`${section.identifier}-solo`}
              className={section.identifier === activeIdentifier ? 'active' : ''}
              data-section-id={section.identifier}
              onClick={() => onSelect(section.identifier)}
            >
              <header>
                <strong>{section.identifier}</strong>
              </header>
              <p>{section.plain_language}</p>
              <details>
                <summary>Fragment oryginału</summary>
                <p>{section.source_text}</p>
              </details>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default SectionViewer;
