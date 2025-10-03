import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage';
import ReaderPage from './pages/ReaderPage';
import ExportPage from './pages/ExportPage';

function App() {
  const location = useLocation();

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="app-logo">
          ProstePrawo
        </Link>
        <nav>
          <NavLink to="/" className={({ isActive }) => (isActive && location.pathname === '/' ? 'active' : '')}>
            Dashboard
          </NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/documents/:documentId" element={<ReaderPage />} />
          <Route path="/documents/:documentId/export" element={<ExportPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
