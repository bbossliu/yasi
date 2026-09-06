import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listEssays } from '../api/client'
import type { EssayOut } from '../api/types'
import { useEcharts } from '../hooks/useEcharts'

const CURVE_MODULES = [
  { key: 'writing', label: '写作' },
  { key: 'speaking', label: '口语' },
  { key: 'listening', label: '听力' },
] as const

type CurveModule = (typeof CURVE_MODULES)[number]['key']

export default function HistoryPage() {
  const [essays, setEssays] = useState<EssayOut[]>([])
  const [curveModule, setCurveModule] = useState<CurveModule>('writing')

  useEffect(() => {
    listEssays().then(setEssays).catch(() => setEssays([]))
  }, [])

  const isListening = curveModule === 'listening'
  const graded = essays.filter((e) => e.total_band !== null && e.module === curveModule)
  const ref = useEcharts({
    xAxis: {
      type: 'category',
      data: [...graded].reverse().map((e) => new Date(e.created_at).toLocaleDateString()),
    },
    yAxis: { type: 'value', min: isListening ? 0 : 4, max: isListening ? 100 : 9 },
    series: [{
      type: 'line',
      smooth: true,
      data: [...graded].reverse().map((e) => e.total_band),
      itemStyle: { color: '#4f46e5' },
      markLine: {
        silent: true,
        data: [{
          yAxis: isListening ? 90 : 6.5,
          label: { formatter: isListening ? '目标 90%' : '目标 6.5' },
        }],
        lineStyle: { color: '#f59e0b', type: 'dashed' },
      },
    }],
    tooltip: {
      trigger: 'axis',
      ...(isListening ? { valueFormatter: (v: unknown) => `${v}%` } : {}),
    },
  })

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="mb-2 flex items-center gap-2">
          <span className="font-semibold">成绩曲线</span>
          <div className="ml-auto flex gap-1">
            {CURVE_MODULES.map((m) => (
              <button
                key={m.key}
                onClick={() => setCurveModule(m.key)}
                className={`rounded-lg px-3 py-1 text-xs ${
                  curveModule === m.key
                    ? 'bg-indigo-600 text-white'
                    : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                }`}
              >{m.label}</button>
            ))}
          </div>
        </div>
        {graded.length > 0
          ? <div ref={ref} className="h-64 w-full" />
          : <div className="py-10 text-center text-sm text-slate-400">还没有已批改的记录</div>}
      </div>
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-500">
            <tr>
              <th className="px-4 py-2">题目</th>
              <th className="px-4 py-2">词数</th>
              <th className="px-4 py-2">用时</th>
              <th className="px-4 py-2">总分</th>
              <th className="px-4 py-2">状态</th>
            </tr>
          </thead>
          <tbody>
            {essays.map((e) => (
              <tr key={e.id} className="border-t border-slate-100">
                <td className="px-4 py-2">
                  <span className={`mr-2 rounded px-1.5 py-0.5 text-xs ${
                    e.module === 'speaking'
                      ? 'bg-emerald-100 text-emerald-700'
                      : e.module === 'listening'
                        ? 'bg-amber-100 text-amber-700'
                        : 'bg-indigo-100 text-indigo-700'
                  }`}>{{ speaking: '口语', listening: '听力' }[e.module] ?? '写作'}</span>
                  {e.module === 'writing' ? (
                    <Link to={`/result/${e.id}`} className="text-indigo-600 hover:underline">
                      {e.prompt_title}
                    </Link>
                  ) : (
                    e.prompt_title
                  )}
                </td>
                <td className="px-4 py-2">{e.word_count}</td>
                <td className="px-4 py-2">{Math.round(e.duration_sec / 60)} 分钟</td>
                <td className="px-4 py-2 font-semibold">
                  {e.total_band === null
                    ? '—'
                    : e.module === 'listening'
                      ? `${e.total_band}%`
                      : e.total_band.toFixed(1)}
                </td>
                <td className="px-4 py-2 text-slate-400">
                  {{ pending: '批改中', done: '已完成', needs_review: '需重试' }[e.status]}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
