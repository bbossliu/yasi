import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import type { Annotation } from '../api/types'

export function AnnotationList({ annotations }: { annotations: Annotation[] }) {
  const [visibleCount, setVisibleCount] = useState(0)

  useEffect(() => {
    setVisibleCount(0)
    if (annotations.length === 0) return
    const timer = setInterval(() => {
      setVisibleCount((n) => {
        if (n >= annotations.length) {
          clearInterval(timer)
          return n
        }
        return n + 1
      })
    }, 600)
    return () => clearInterval(timer)
  }, [annotations])

  return (
    <div className="space-y-3">
      {annotations.slice(0, visibleCount).map((a, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-xl border border-slate-200 bg-white p-4 text-sm"
        >
          <div className="mb-1 flex items-center gap-2">
            <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-600">
              {a.error_type ?? '批注'}
            </span>
            <span className="text-xs text-slate-400">第 {a.sentence_index + 1} 句</span>
          </div>
          <div className="text-slate-500 line-through">{a.original}</div>
          <div className="mt-1 text-slate-700">{a.issue}</div>
          <div className="mt-1 text-emerald-700">✎ {a.suggestion}</div>
        </motion.div>
      ))}
      {visibleCount < annotations.length && (
        <div className="text-center text-xs text-slate-400">AI 正在输出批注…</div>
      )}
    </div>
  )
}
