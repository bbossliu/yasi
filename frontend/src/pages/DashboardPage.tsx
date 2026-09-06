import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listErrors, listEssays, listVocabTopics } from '../api/client'
import type { EssayOut, ErrorItemOut } from '../api/types'

const TARGET_BAND = 6.5

export default function DashboardPage() {
  const [essays, setEssays] = useState<EssayOut[]>([])
  const [errors, setErrors] = useState<ErrorItemOut[]>([])
  const [vocab, setVocab] = useState({ mastered: 0, total: 0, due: 0 })

  useEffect(() => {
    listEssays().then(setEssays).catch(() => undefined)
    listErrors().then(setErrors).catch(() => undefined)
    listVocabTopics().then((topics) => setVocab({
      mastered: topics.reduce((n, t) => n + t.mastered_count, 0),
      total: topics.reduce((n, t) => n + t.word_count, 0),
      due: topics.reduce((n, t) => n + t.due_count, 0),
    })).catch(() => undefined)
  }, [])

  const latest = essays.find((e) => e.total_band !== null && e.module === 'writing')
  const latestSpeaking = essays.find((e) => e.total_band !== null && e.module === 'speaking')
  const topErrors = useMemo(() => {
    const counts = new Map<string, number>()
    for (const e of errors) counts.set(e.error_type, (counts.get(e.error_type) ?? 0) + 1)
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5)
  }, [errors])

  const progress = latest?.total_band ? Math.min(latest.total_band / TARGET_BAND, 1) : 0

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">当前预测分 → 目标分</div>
          <div className="mt-1 text-3xl font-bold text-indigo-600">
            {latest ? latest.total_band!.toFixed(1) : '—'}
            <span className="text-base font-normal text-slate-400"> / {TARGET_BAND}</span>
          </div>
          <div className="mt-3 h-2 rounded-full bg-slate-100">
            <div
              className="h-2 rounded-full bg-indigo-500 transition-all"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">口语最新分</div>
          <div className="mt-1 text-3xl font-bold text-emerald-600">
            {latestSpeaking?.total_band?.toFixed(1) ?? '—'}
          </div>
          <Link to="/speaking" className="mt-3 inline-block text-sm text-emerald-600 hover:underline">
            去练口语 →
          </Link>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">词汇掌握</div>
          <div className="mt-1 text-3xl font-bold text-amber-600">
            {vocab.mastered}/{vocab.total}
          </div>
          <div className="mt-1 text-sm text-slate-400">
            {vocab.due > 0 ? `${vocab.due} 词今日到期` : '今日无到期'}
          </div>
          <Link to="/vocab" className="mt-3 inline-block text-sm text-amber-600 hover:underline">
            去复习 →
          </Link>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">累计练习</div>
          <div className="mt-1 text-3xl font-bold">{essays.length} 次</div>
          <Link to="/write" className="mt-3 inline-block text-sm text-indigo-600 hover:underline">
            开始新一篇 →
          </Link>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">我的高频错误 TOP</div>
          {topErrors.length > 0 ? (
            <ul className="mt-2 space-y-1 text-sm">
              {topErrors.map(([type, count]) => (
                <li key={type} className="flex justify-between">
                  <span>{type}</span>
                  <span className="text-slate-400">{count} 次</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-2 text-sm text-slate-400">完成一次批改后生成</div>
          )}
        </div>
      </div>
      <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400">
        能力树、听力模块将在 V4 解锁
      </div>
    </div>
  )
}
