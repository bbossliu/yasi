const ACADEMIC_WORDS = new Set([
  'furthermore', 'moreover', 'nevertheless', 'consequently', 'therefore', 'whereas',
  'significant', 'substantial', 'considerable', 'crucial', 'essential', 'beneficial',
  'detrimental', 'controversial', 'inevitable', 'phenomenon', 'perspective', 'implication',
  'alleviate', 'facilitate', 'implement', 'demonstrate', 'emphasize', 'undertake',
  'comprehensive', 'sustainable', 'increasingly', 'predominantly', 'notably', 'arguably',
  'drawback', 'outweigh', 'cohesion', 'supervision', 'isolation', 'infrastructure',
])

export function countWords(content: string): number {
  return content.trim().split(/\s+/).filter(Boolean).length
}

export function estimateBand(content: string): string {
  const n = countWords(content)
  if (n === 0) return '—'
  if (n < 150) return '≤ 5.0（词数不足）'
  if (n < 200) return '4.5 - 5.5'
  if (n < 260) return '5.5 - 6.5'
  if (n <= 340) return '6.0 - 7.0'
  return '6.5 - 7.5'
}

export function advancedRatio(content: string): number {
  const words = content.toLowerCase().replace(/[^a-z\s]/g, '').split(/\s+/).filter(Boolean)
  if (words.length === 0) return 0
  const hits = words.filter((w) => ACADEMIC_WORDS.has(w)).length
  return hits / words.length
}

export function AnalysisBar({ content }: { content: string }) {
  const ratio = advancedRatio(content)
  return (
    <div className="w-56 shrink-0 space-y-4 rounded-xl border border-slate-200 bg-white p-4 text-sm">
      <div className="font-semibold text-slate-700">AI 实时分析</div>
      <div>
        <div className="text-slate-400">词数</div>
        <div className="text-2xl font-bold text-indigo-600">{countWords(content)}</div>
        <div className="text-xs text-slate-400">Task 2 要求 ≥ 250 词</div>
      </div>
      <div>
        <div className="text-slate-400">预估分数区间</div>
        <div className="text-lg font-semibold">{estimateBand(content)}</div>
        <div className="text-xs text-slate-400">基于词数与词汇的粗估，非 AI 评分</div>
      </div>
      <div>
        <div className="text-slate-400">学术词汇占比</div>
        <div className="text-lg font-semibold">{(ratio * 100).toFixed(1)}%</div>
      </div>
    </div>
  )
}
