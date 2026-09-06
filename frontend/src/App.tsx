import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { NavBar } from './components/NavBar'

function Placeholder({ name }: { name: string }) {
  return <div className="p-10 text-slate-400">{name}（待实现）</div>
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50 text-slate-800">
        <NavBar />
        <main className="mx-auto max-w-6xl p-6">
          <Routes>
            <Route path="/" element={<Placeholder name="仪表盘" />} />
            <Route path="/write" element={<Placeholder name="写作练习" />} />
            <Route path="/result/:id" element={<Placeholder name="批改结果" />} />
            <Route path="/history" element={<Placeholder name="历史记录" />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
