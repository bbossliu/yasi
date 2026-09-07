import { useEffect, useRef, useState } from 'react'
import {
  createSpeakingSession, finishSpeakingSession, getEssay, getReviewQueue, getSpeakingTurn,
  listListeningMaterials, listPrompts, listSpeakingCards, submitDictation, submitEssay,
  submitReview, submitSpeakingTurn, getListeningMaterial, requestListeningAudio,
} from '../api/client'
import type { MatDetailOut, ReviewCardOut } from '../api/types'
import { WavRecorder } from '../lib/recorder'

export function ExamWritingStep({ onDone }: { onDone: (practiceId: number) => void }) {
  const [prompts, setPrompts] = useState<{ title: string; text: string }[]>([])
  const [selected, setSelected] = useState(0)
  const [content, setContent] = useState('')
  const [secondsLeft, setSecondsLeft] = useState(40 * 60)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const startRef = useRef(Date.now())

  useEffect(() => {
    listPrompts().then(setPrompts).catch(() => undefined)
  }, [])
  useEffect(() => {
    if (secondsLeft <= 0) return
    const t = setTimeout(() => setSecondsLeft(secondsLeft - 1), 1000)
    return () => clearTimeout(t)
  }, [secondsLeft])

  if (prompts.length === 0) return <div className="p-10 text-slate-400">加载中…</div>

  const submit = async () => {
    setBusy(true)
    try {
      const p = prompts[selected]
      const essay = await submitEssay({
        prompt_title: p.title, prompt_text: p.text, content,
        duration_sec: Math.round((Date.now() - startRef.current) / 1000),
      })
      // 等批改完成再进下一步（轮询，最多 30 次 × 2s）
      let detail = await getEssay(essay.id)
      let polls = 0
      while (detail.status === 'pending' && polls < 30) {
        await new Promise((r) => setTimeout(r, 2000))
        detail = await getEssay(essay.id)
        polls++
      }
      if (detail.status === 'pending') {
        setError('批改超时，请稍后重试')
        return
      }
      if (detail.status !== 'done') {
        setError('批改未完成，请重试')
        return
      }
      onDone(essay.id)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const mm = String(Math.floor(secondsLeft / 60)).padStart(2, '0')
  const ss = String(secondsLeft % 60).padStart(2, '0')
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <select className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
          value={selected} onChange={(e) => setSelected(Number(e.target.value))}>
          {prompts.map((p, i) => <option key={p.title} value={i}>{p.title}</option>)}
        </select>
        <span className={`font-mono text-lg ${secondsLeft < 300 ? 'text-red-500' : 'text-slate-600'}`}>
          ⏱ {mm}:{ss}
        </span>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
        {prompts[selected].text}
      </div>
      <textarea
        className="min-h-[300px] w-full rounded-xl border border-slate-300 p-4 font-mono text-sm"
        placeholder="Task 2 作文（250 词以上）…"
        value={content}
        onChange={(e) => setContent(e.target.value)}
      />
      {error && <div className="text-sm text-red-500">{error}</div>}
      <button onClick={submit} disabled={busy || content.trim().split(/\s+/).length < 30}
        className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white disabled:opacity-40">
        {busy ? '批改中…' : '提交并进入下一环节'}
      </button>
    </div>
  )
}

export function ExamSpeakingStep({ onDone }: { onDone: (practiceId: number) => void }) {
  const [card, setCard] = useState<{ id: number; topic: string } | null>(null)
  const [sessionId, setSessionId] = useState(0)
  const [question, setQuestion] = useState('')
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const recorderRef = useRef<WavRecorder | null>(null)

  useEffect(() => {
    (async () => {
      const cards = await listSpeakingCards(2)
      const pick = cards[Math.floor(Math.random() * cards.length)]
      setCard(pick)
      const sess = await createSpeakingSession(pick.id)
      setSessionId(sess.id)
      setQuestion(sess.question)
    })().catch((e) => setError(String(e)))
    return () => {
      if (recorderRef.current) {
        const r = recorderRef.current
        recorderRef.current = null
        void r.stop()
      }
    }
  }, [])

  const toggle = async () => {
    if (recording) {
      const recorder = recorderRef.current
      if (!recorder) return
      recorderRef.current = null
      setRecording(false)
      setBusy(true)
      try {
        const blob = await recorder.stop()
        const { practice_id } = await submitSpeakingTurn(sessionId, blob)
        let detail = await getSpeakingTurn(practice_id)
        let polls = 0
        while (detail.status === 'pending' && polls < 30) {
          await new Promise((r) => setTimeout(r, 2000))
          detail = await getSpeakingTurn(practice_id)
          polls++
        }
        if (detail.status !== 'done') {
          setError('评分未完成，请重新录音')
          setBusy(false)
          return
        }
        await finishSpeakingSession(sessionId)
        onDone(practice_id)
      } catch (e) {
        setError(String(e))
        setBusy(false)
      }
    } else {
      try {
        recorderRef.current = new WavRecorder()
        await recorderRef.current.start()
        setRecording(true)
      } catch {
        setError('无法访问麦克风')
      }
    }
  }

  if (!card) return <div className="p-10 text-slate-400">抽题中…</div>
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="text-xs text-slate-400">Part 2 Cue Card</div>
        <div className="mt-1 whitespace-pre-wrap font-medium">{question}</div>
      </div>
      {error && <div className="text-sm text-red-500">{error}</div>}
      <button onClick={toggle} disabled={busy}
        className={`w-full rounded-xl py-3 font-semibold text-white disabled:opacity-40 ${
          recording ? 'bg-red-500' : 'bg-indigo-600'}`}>
        {recording ? '■ 停止并提交' : busy ? '评分中…' : '● 开始陈述（约 2 分钟）'}
      </button>
    </div>
  )
}

export function ExamListeningStep({ onDone }: { onDone: (practiceId: number) => void }) {
  const [mat, setMat] = useState<MatDetailOut | null>(null)
  const [answers, setAnswers] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    (async () => {
      const mats = await listListeningMaterials()
      const ready = mats.filter((m) => m.ready_count > 0)
      const readyS4 = ready.filter((m) => m.section === 4)
      const pool = readyS4.length ? readyS4 : ready
      if (pool.length) {
        const pick = pool[Math.floor(Math.random() * pool.length)]
        const detail = await getListeningMaterial(pick.id)
        setMat(detail)
        setAnswers(detail.sentences.map(() => ''))
        return
      }
      const s4 = mats.filter((m) => m.section === 4)
      const pick = (s4.length ? s4 : mats)[Math.floor(Math.random() * (s4.length ? s4.length : mats.length))]
      await requestListeningAudio(pick.id)
      const detail = await getListeningMaterial(pick.id)
      setMat(detail)
      setAnswers(detail.sentences.map(() => ''))
    })().catch((e) => setError(String(e)))
  }, [])

  if (!mat) return <div className="p-10 text-slate-400">选题中…</div>

  const submit = async () => {
    setBusy(true)
    try {
      const result = await submitDictation(mat.id, answers)
      onDone(result.practice_id)
    } catch (e) {
      setError(String(e))
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="text-sm text-slate-500">
        精听听写：{mat.title}（{mat.sentences.length} 句，逐句播放并输入）
      </div>
      {mat.sentences.map((_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3">
          <button type="button"
            onClick={() => new Audio(`/api/listening/audio/${mat.id}/${i}.mp3`).play().catch(() => undefined)}
            className="shrink-0 rounded-lg bg-indigo-50 px-3 py-1 text-sm text-indigo-600">
            ▶ {i + 1}
          </button>
          <input
            className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
            value={answers[i]}
            onChange={(e) => {
              const next = [...answers]
              next[i] = e.target.value
              setAnswers(next)
            }}
          />
        </div>
      ))}
      {error && <div className="text-sm text-red-500">{error}</div>}
      <button onClick={submit} disabled={busy}
        className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white disabled:opacity-40">
        {busy ? '比对中…' : '提交听写'}
      </button>
    </div>
  )
}

export function ExamVocabStep({ onDone }: { onDone: (practiceId: number) => void }) {
  const [queue, setQueue] = useState<ReviewCardOut[]>([])
  const [flipped, setFlipped] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getReviewQueue(20).then((q) => setQueue(q.cards)).catch((e) => setError(String(e)))
  }, [])

  const current = queue[0]

  const rate = async (quality: 1 | 3 | 5) => {
    await submitReview(current.word_id, quality)
    setQueue((q) => q.slice(1))
    setFlipped(false)
  }

  if (error) return <div className="text-sm text-red-500">{error}</div>
  if (queue.length === 0 && !current) {
    // 队列空：词汇环节记为已完成——用一个 listening 之外的标记：直接调 onDone 是不行的（需要 practice_id）。
    // 词汇快测不产生 practice；用最近一次 listening/写作 practice？——见 plan 注：词汇环节不计 practice_id，complete 只需要写/口/听三科。
    return <VocabDone onDone={onDone} />
  }
  if (!current) return <VocabDone onDone={onDone} />

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div className="text-center text-sm text-slate-400">剩 {queue.length} 张</div>
      <div onClick={() => setFlipped(!flipped)}
        className="cursor-pointer rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
        {!flipped ? (
          <div className="text-3xl font-bold">{current.text}</div>
        ) : (
          <div className="space-y-2">
            <div className="text-2xl font-bold">{current.text}</div>
            <div className="text-slate-700">{current.meaning}</div>
            <div className="text-sm italic text-slate-500">{current.example_sentence}</div>
          </div>
        )}
      </div>
      {flipped && (
        <div className="grid grid-cols-3 gap-3">
          <button onClick={() => rate(1)} className="rounded-xl bg-red-500 py-3 font-semibold text-white">不认识</button>
          <button onClick={() => rate(3)} className="rounded-xl bg-amber-500 py-3 font-semibold text-white">模糊</button>
          <button onClick={() => rate(5)} className="rounded-xl bg-emerald-600 py-3 font-semibold text-white">认识</button>
        </div>
      )}
    </div>
  )
}

function VocabDone({ onDone }: { onDone: (practiceId: number) => void }) {
  return (
    <div className="space-y-4 text-center">
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-emerald-700">
        词汇快测完成
      </div>
      <button onClick={() => onDone(-1)}  // -1 = 占位，complete 端只用写/口/听三科
        className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white">
        完成模考，查看综评
      </button>
    </div>
  )
}
