import type { Annotation } from '../api/types'

/** 原文列：被批注的句子按 original 字符串匹配标红；右列为 AI 改写版。 */
export function DiffView({ original, rewrite, annotations }: {
  original: string
  rewrite: string
  annotations: Annotation[]
}) {
  const flagged = annotations.map((a) => a.original)
  const sentences = original.match(/[^.!?]+[.!?]+(\s|$)/g) ?? [original]

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="mb-2 text-sm font-semibold text-slate-500">你的原文</div>
        <p className="text-sm leading-7">
          {sentences.map((s, i) => {
            const isFlagged = flagged.some((f) => s.trim().startsWith(f.trim().slice(0, 30)))
            return (
              <span key={i} className={isFlagged ? 'rounded bg-red-100 px-0.5' : undefined}>
                {s}
              </span>
            )
          })}
        </p>
      </div>
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
        <div className="mb-2 text-sm font-semibold text-emerald-600">AI 改写版（7.5 分水平）</div>
        <p className="text-sm leading-7 text-slate-700">{rewrite}</p>
      </div>
    </div>
  )
}
