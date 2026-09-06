import { useState } from 'react'
import type { SpeakingFeedback } from '../api/types'

const BAND_LABELS: [keyof SpeakingFeedback['bands'], string][] = [
  ['fluency', '流利度 FC'],
  ['lexical', '词汇 LR'],
  ['grammar', '语法 GRA'],
  ['pronunciation', '发音 P'],
]

export function SpeakingFeedbackCard({ feedback }: { feedback: SpeakingFeedback }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="mt-2 rounded-lg border border-indigo-100 bg-indigo-50/50 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-lg font-bold text-indigo-600">
          {feedback.bands.overall.toFixed(1)}
        </span>
        {BAND_LABELS.map(([key, label]) => (
          <span key={key} className="text-xs text-slate-500">
            {label} <b>{feedback.bands[key].toFixed(1)}</b>
          </span>
        ))}
        {feedback.is_mock && (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">演示数据</span>
        )}
      </div>
      <div className="mt-1 text-xs text-slate-400">发音分为间接评估，仅供参考</div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-2 text-xs text-indigo-600 hover:underline"
      >
        {expanded ? '收起批注 ▲' : `查看 ${feedback.annotations.length} 条批注与 7 分改写 ▼`}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {feedback.annotations.map((a, i) => (
            <div key={i} className="rounded bg-white p-2">
              <span className="mr-1 rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-600">
                {a.error_type ?? '批注'}
              </span>
              <span className="text-slate-500 line-through">{a.original}</span>
              <div className="mt-1 text-slate-700">{a.issue}</div>
              <div className="text-emerald-700">✎ {a.suggestion}</div>
            </div>
          ))}
          <div className="rounded border border-emerald-200 bg-emerald-50 p-2">
            <div className="text-xs font-semibold text-emerald-600">7 分改写版</div>
            <p className="mt-1 text-slate-700">{feedback.rewrite}</p>
          </div>
        </div>
      )}
    </div>
  )
}
