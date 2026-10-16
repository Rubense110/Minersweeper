import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import RunPage from './pages/RunPage'
import ResultsPage from './pages/ResultsPage'
import HistoryPage from './pages/HistoryPage'
import ExplorationPage from './pages/ExplorationPage'

export default function App() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <h1>MinerSweeper</h1>
        </div>
        <nav className="topnav" aria-label="Main navigation">
          <NavLink className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')} to="/exploration">Exploración</NavLink>
          <NavLink className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')} to="/run">
            New Experiment
          </NavLink>
          <NavLink className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')} to="/history">
            History
          </NavLink>
        </nav>
      </header>

      <Routes>
        <Route path="/" element={<Navigate to="/run" replace />} />
        <Route path="/run" element={<RunPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/exploration" element={<ExplorationPage />} />
        <Route path="/exploration/:explorationId" element={<ExplorationPage />} />
        <Route path="/experiments/:experimentId/exploration" element={<ExplorationPage />} />
        <Route path="/results/:jobId" element={<ResultsPage />} />
        <Route path="*" element={<Navigate to="/run" replace />} />
      </Routes>
    </div>
  )
}
