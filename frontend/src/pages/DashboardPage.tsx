import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { listErrors, listEssays } from '../api/client'
import type { EssayOut, ErrorItemOut } from '../api/types'

const TARGET_BAND = 6.5

export default function DashboardPage() {
  const [essays, setEssays] = useState<EssayOut[]>([])
  const [errors, setErrors] = useState<ErrorItemOut[]>([])

  useEffect(() => {
    listEssays().then(setEssays).catch(() => undefined)
    listErrors().then(setErrors).catch(() => undefined)
  }, [])

  const latest = essays.find((e) => e.total_band !== null)
  const topErrors = useMemo(() => {
    const counts = new Map<string, number>()
    for (const e of errors) counts.set(e.error_type, (counts.get(e.error_type) ?? 0) + 1)
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5)
  }, [errors])

  const progress = latest?.total_band ? Math.min(latest.total_band / TARGET_BAND, 1) : 0

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
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
          <div className="text-sm text-slate-400">累计练习</div>
          <div className="mt-1 text-3xl font-bold">{essays.length} 篇</div>
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
        能力树、口语 / 听力 / 词汇模块将在 V2-V4 解锁
      </div>
    </div>
  )
}
