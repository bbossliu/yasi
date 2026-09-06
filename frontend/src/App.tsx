import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import DashboardPage from './pages/DashboardPage'
import HistoryPage from './pages/HistoryPage'
import ResultPage from './pages/ResultPage'
import SpeakingPage from './pages/SpeakingPage'
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
            <Route path="/speaking" element={<SpeakingPage />} />
            <Route
              path="/speaking/session/:id"
              element={<div className="p-10 text-slate-400">练习室（下一任务实现）</div>}
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
