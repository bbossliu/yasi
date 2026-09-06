import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createSpeakingSession, listSpeakingCards } from '../api/client'
import type { SpeakingCardOut } from '../api/types'

const PARTS = [
  { part: 1, name: 'Part 1 日常问答', desc: '4 个日常话题小问题，每题回答 20-30 秒' },
  { part: 2, name: 'Part 2 个人陈述', desc: 'Cue Card：准备 1 分钟，陈述 2 分钟' },
  { part: 3, name: 'Part 3 深度讨论', desc: 'AI 考官根据你的回答连续追问' },
]

export default function SpeakingPage() {
  const [part, setPart] = useState(1)
  const [cards, setCards] = useState<SpeakingCardOut[]>([])
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    setCards([])
    listSpeakingCards(part).then(setCards).catch((e) => setError(String(e)))
  }, [part])

  const start = async (card: SpeakingCardOut) => {
    if (starting) return
    setStarting(true)
    setError('')
    try {
      const session = await createSpeakingSession(card.id)
      navigate(`/speaking/session/${session.id}`, { state: { session } })
    } catch (e) {
      setError(String(e))
      setStarting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {PARTS.map((p) => (
          <button
            key={p.part}
            onClick={() => setPart(p.part)}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              part === p.part ? 'bg-indigo-600 text-white' : 'bg-white text-slate-600 border border-slate-200'
            }`}
          >
            {p.name}
          </button>
        ))}
      </div>
      <p className="text-sm text-slate-400">{PARTS[part - 1].desc}</p>
      {error && <div className="text-sm text-red-500">{error}</div>}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {cards.map((card) => (
          <button
            key={card.id}
            onClick={() => start(card)}
            disabled={starting}
            className="rounded-xl border border-slate-200 bg-white p-5 text-left hover:border-indigo-300 hover:shadow-sm disabled:opacity-50"
          >
            <div className="font-semibold text-slate-700">{card.topic}</div>
            <div className="mt-1 text-xs text-slate-400">
              {card.season} 季度题库 ·{' '}
              {card.part === 2 ? `${card.payload.cues?.length ?? 0} 个提示点` : `${card.payload.questions?.length ?? 0} 个问题`}
            </div>
          </button>
        ))}
      </div>
      {cards.length === 0 && !error && (
        <div className="py-10 text-center text-sm text-slate-400">加载话题卡中…</div>
      )}
    </div>
  )
}
