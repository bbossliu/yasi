import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getSample, listPrompts, submitEssay } from '../api/client'
import type { PromptOut } from '../api/types'
import { AnalysisBar, countWords } from '../components/AnalysisBar'

export default function WritingPage() {
  const [prompts, setPrompts] = useState<PromptOut[]>([])
  const [selected, setSelected] = useState(0)
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const startRef = useRef(Date.now())
  const navigate = useNavigate()

  useEffect(() => {
    listPrompts().then(setPrompts).catch((e) => setError(String(e)))
  }, [])

  const fillSample = async () => {
    const sample = await getSample()
    const idx = prompts.findIndex((p) => p.title === sample.title)
    if (idx >= 0) setSelected(idx)
    setContent(sample.content)
    startRef.current = Date.now()
  }

  const submit = async () => {
    if (countWords(content) === 0 || submitting) return
    setSubmitting(true)
    setError('')
    try {
      const prompt = prompts[selected]
      const essay = await submitEssay({
        prompt_title: prompt.title,
        prompt_text: prompt.text,
        content,
        duration_sec: Math.round((Date.now() - startRef.current) / 1000),
      })
      navigate(`/result/${essay.id}`)
    } catch (e) {
      setError(String(e))
      setSubmitting(false)
    }
  }

  if (prompts.length === 0) {
    return <div className="p-10 text-slate-400">加载题目中…</div>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <select
          className="rounded-lg border border-slate-300 px-3 py-2"
          value={selected}
          onChange={(e) => setSelected(Number(e.target.value))}
        >
          {prompts.map((p, i) => (
            <option key={p.title} value={i}>{p.title}</option>
          ))}
        </select>
        <button
          onClick={fillSample}
          className="rounded-lg border border-indigo-300 px-3 py-2 text-indigo-600 hover:bg-indigo-50"
        >
          试试这个（填充示例作文）
        </button>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
        {prompts[selected].text}
      </div>
      <div className="flex gap-4">
        <textarea
          className="min-h-[420px] flex-1 rounded-xl border border-slate-300 p-4 font-mono text-sm focus:border-indigo-400 focus:outline-none"
          placeholder="在这里写你的 Task 2 作文（250 词以上）…"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        <AnalysisBar content={content} />
      </div>
      {error && <div className="text-sm text-red-500">{error}</div>}
      {countWords(content) > 500 && (
        <div className="text-sm font-semibold text-red-500">
          已超过 500 词上限（当前 {countWords(content)} 词），请精简后再提交
        </div>
      )}
      <button
        onClick={submit}
        disabled={countWords(content) === 0 || countWords(content) > 500 || submitting}
        className="rounded-xl bg-indigo-600 px-6 py-3 font-semibold text-white disabled:opacity-40"
      >
        {submitting ? '提交中…' : '提交批改'}
      </button>
    </div>
  )
}
