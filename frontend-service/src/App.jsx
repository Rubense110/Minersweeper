import { Navigate, Route, Routes } from 'react-router-dom'
import RunPage from './pages/RunPage'
import ResultsPage from './pages/ResultsPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RunPage />} />
      <Route path="/results/:jobId" element={<ResultsPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
