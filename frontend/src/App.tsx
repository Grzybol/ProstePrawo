import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import ReaderPage from './pages/ReaderPage';
import ExportPage from './pages/ExportPage';
import TemplateGeneratorPage from './pages/TemplateGeneratorPage';

function App() {
  const location = useLocation();

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="app-logo">
          ProstePrawo
        </Link>
        <div className="app-header-actions">
          <nav className="app-nav">
            <NavLink to="/" className={({ isActive }) => (isActive && location.pathname === '/' ? 'active' : '')}>
              Analizuj dokument
            </NavLink>
          </nav>
          <NavLink
            to="/templates"
            className={({ isActive }) => `button header-primary-button${isActive ? ' active' : ''}`}
          >
            Generuj templatkę dokumentu
          </NavLink>
        </div>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/templates" element={<TemplateGeneratorPage />} />
          <Route path="/documents/:documentId" element={<ReaderPage />} />
          <Route path="/documents/:documentId/export" element={<ExportPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
