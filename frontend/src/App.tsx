import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import DashboardPage from './pages/DashboardPage'
import HistoryPage from './pages/HistoryPage'
import ResultPage from './pages/ResultPage'
import WritingPage from './pages/WritingPage'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50 text-slate-800">
        <NavBar />
        <main className="mx-auto max-w-6xl p-6">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/write" element={<WritingPage />} />
            <Route path="/result/:id" element={<ResultPage />} />
            <Route path="/history" element={<HistoryPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
