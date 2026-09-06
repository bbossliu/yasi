import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listEssays } from '../api/client'
import type { EssayOut } from '../api/types'
import { useEcharts } from '../hooks/useEcharts'

export default function HistoryPage() {
  const [essays, setEssays] = useState<EssayOut[]>([])

  useEffect(() => {
    listEssays().then(setEssays).catch(() => setEssays([]))
  }, [])

  const graded = essays.filter((e) => e.total_band !== null)
  const ref = useEcharts({
    xAxis: {
      type: 'category',
      data: [...graded].reverse().map((e) => new Date(e.created_at).toLocaleDateString()),
    },
    yAxis: { type: 'value', min: 4, max: 9 },
    series: [{
      type: 'line',
      smooth: true,
      data: [...graded].reverse().map((e) => e.total_band),
      itemStyle: { color: '#4f46e5' },
      markLine: {
        silent: true,
        data: [{ yAxis: 6.5, label: { formatter: '目标 6.5' } }],
        lineStyle: { color: '#f59e0b', type: 'dashed' },
      },
    }],
    tooltip: { trigger: 'axis' },
  })

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="mb-2 font-semibold">成绩曲线</div>
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
                  <Link to={`/result/${e.id}`} className="text-indigo-600 hover:underline">
                    {e.prompt_title}
                  </Link>
                </td>
                <td className="px-4 py-2">{e.word_count}</td>
                <td className="px-4 py-2">{Math.round(e.duration_sec / 60)} 分钟</td>
                <td className="px-4 py-2 font-semibold">
                  {e.total_band !== null ? e.total_band.toFixed(1) : '—'}
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
