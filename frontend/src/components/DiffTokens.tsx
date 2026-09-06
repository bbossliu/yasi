import type { DiffToken } from '../api/types'

/** 词级 diff 渲染：ok 正常 / missing 红虚线下划线 / wrong 红底显示原文+你的词 / extra 删除线 */
export function DiffTokens({ tokens }: { tokens: DiffToken[] }) {
  return (
    <span className="leading-7">
      {tokens.map((t, i) => {
        if (t.type === 'ok') return <span key={i}>{t.ref} </span>
        if (t.type === 'missing') {
          return (
            <span key={i} className="border-b-2 border-dashed border-red-400 text-red-500">
              {t.ref}{' '}
            </span>
          )
        }
        if (t.type === 'wrong') {
          return (
            <span key={i} className="rounded bg-red-100 px-0.5 text-red-600" title={`你写的是: ${t.hyp}`}>
              {t.ref} <s className="text-red-400">{t.hyp}</s>{' '}
            </span>
          )
        }
        return (
          <span key={i} className="text-slate-400 line-through">
            {t.hyp}{' '}
          </span>
        )
      })}
    </span>
  )
}
