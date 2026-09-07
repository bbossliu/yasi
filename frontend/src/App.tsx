import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { NavBar } from './components/NavBar'
import DashboardPage from './pages/DashboardPage'
import HistoryPage from './pages/HistoryPage'
import ListeningPage from './pages/ListeningPage'
import MockExamPage from './pages/MockExamPage'
import PracticeRoom from './pages/PracticeRoom'
import ResultPage from './pages/ResultPage'
import SkillTreePage from './pages/SkillTreePage'
import SpeakingPage from './pages/SpeakingPage'
import VocabPage from './pages/VocabPage'
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
            <Route path="/listening" element={<ListeningPage />} />
            <Route path="/vocab" element={<VocabPage />} />
            <Route path="/skills" element={<SkillTreePage />} />
            <Route path="/mock" element={<MockExamPage />} />
            <Route path="/speaking/session/:id" element={<PracticeRoom />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
