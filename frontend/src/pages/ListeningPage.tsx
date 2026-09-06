import { useEffect, useRef, useState } from 'react'
import {
  getListeningMaterial, listListeningMaterials, requestListeningAudio,
  submitAttribution, submitDictation, submitShadowing,
} from '../api/client'
import type {
  DictationResultOut, MatDetailOut, MatListOut, ShadowingResult,
} from '../api/types'
import { DiffTokens } from '../components/DiffTokens'
import { WavRecorder } from '../lib/recorder'

const REASONS = ['连读', '词汇', '口音', '注意力'] as const
const SPEEDS = [0.75, 1, 1.25] as const

type Mode = 'transcript' | 'dictation' | 'shadowing'

export default function ListeningPage() {
  const [materials, setMaterials] = useState<MatListOut[]>([])
  const [selected, setSelected] = useState<MatDetailOut | null>(null)
  const [mode, setMode] = useState<Mode>('transcript')
  const [error, setError] = useState('')

  useEffect(() => {
    listListeningMaterials().then(setMaterials).catch((e) => setError(String(e)))
  }, [])

  const open = async (id: number) => {
    const detail = await getListeningMaterial(id)
    setSelected(detail)
    setMode('transcript')
    // 触发后台逐句音频生成（幂等；已就绪则立即 ready）
    requestListeningAudio(id).catch(() => undefined)
  }

  if (selected) {
    return <PracticeView mat={selected} mode={mode} setMode={setMode}
      onBack={() => setSelected(null)} />
  }

  const sections = [2, 3, 4]
  return (
    <div className="space-y-6">
      {error && <div className="text-sm text-red-500">{error}</div>}
      {sections.map((sec) => (
        <div key={sec}>
          <h3 className="mb-2 font-semibold text-slate-600">Section {sec}</h3>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {materials.filter((m) => m.section === sec).map((m) => (
              <button key={m.id} onClick={() => open(m.id)}
                className="rounded-xl border border-slate-200 bg-white p-4 text-left hover:border-indigo-300">
                <div className="font-medium text-slate-700">{m.title}</div>
                <div className="mt-1 text-xs text-slate-400">
                  {m.sentence_count} 句 · 音频就绪 {m.ready_count}/{m.sentence_count}
                </div>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function PracticeView({ mat, mode, setMode, onBack }: {
  mat: MatDetailOut
  mode: Mode
  setMode: (m: Mode) => void
  onBack: () => void
}) {
  const [speed, setSpeed] = useState<number>(1)
  const [loopIdx, setLoopIdx] = useState<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const play = (idx: number) => {
    audioRef.current?.pause()
    const audio = new Audio(`/api/listening/audio/${mat.id}/${idx}.mp3`)
    audio.playbackRate = speed
    audio.onended = () => setLoopIdx((cur) => (cur === idx ? null : cur))
    audio.onerror = () => setLoopIdx(null)
    audio.play().catch(() => undefined)
    audioRef.current = audio
  }

  const toggleLoop = (idx: number) => {
    if (loopIdx === idx) {
      audioRef.current?.pause()
      setLoopIdx(null)
      return
    }
    audioRef.current?.pause()
    const audio = new Audio(`/api/listening/audio/${mat.id}/${idx}.mp3`)
    audio.playbackRate = speed
    audio.loop = true
    audio.play().catch(() => undefined)
    audioRef.current = audio
    setLoopIdx(idx)
  }

  useEffect(() => () => audioRef.current?.pause(), [])

  const MODES: { key: Mode; label: string }[] = [
    { key: 'transcript', label: '字幕对照' },
    { key: 'dictation', label: '精听听写' },
    { key: 'shadowing', label: '影子跟读' },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <button onClick={onBack} className="mr-3 text-sm text-slate-400 hover:text-slate-600">
            ← 返回
          </button>
          <span className="font-semibold">{mat.title}</span>
          <span className="ml-2 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
            Section {mat.section}
          </span>
        </div>
        <div className="flex gap-1">
          {SPEEDS.map((s) => (
            <button key={s} onClick={() => setSpeed(s)}
              className={`rounded px-2 py-1 text-xs ${
                speed === s ? 'bg-indigo-600 text-white' : 'bg-white border border-slate-200'
              }`}>
              {s}x
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-2">
        {MODES.map((m) => (
          <button key={m.key} onClick={() => setMode(m.key)}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              mode === m.key ? 'bg-indigo-600 text-white' : 'bg-white border border-slate-200 text-slate-600'
            }`}>
            {m.label}
          </button>
        ))}
      </div>

      {mode === 'transcript' && (
        <div className="space-y-2">
          {mat.sentences.map((s, i) => (
            <div key={i}
              className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-3">
              <button onClick={() => toggleLoop(i)} title="单句循环"
                className={`shrink-0 rounded-lg px-3 py-1 text-sm ${
                  loopIdx === i ? 'bg-indigo-600 text-white' : 'bg-indigo-50 text-indigo-600'
                }`}>
                {loopIdx === i ? '⏸ 停止' : '▶ 循环'}
              </button>
              <span className="text-sm text-slate-700">{s}</span>
            </div>
          ))}
          <p className="text-xs text-slate-400">
            音频由 AI 语音生成；显示"音频不存在"时请稍后重试（后台生成中）。
          </p>
        </div>
      )}

      {mode === 'dictation' && <DictationMode mat={mat} play={play} />}
      {mode === 'shadowing' && <ShadowingMode mat={mat} />}
    </div>
  )
}

function DictationMode({ mat, play }: {
  mat: MatDetailOut
  play: (idx: number) => void
}) {
  const [answers, setAnswers] = useState<string[]>(mat.sentences.map(() => ''))
  const [result, setResult] = useState<DictationResultOut | null>(null)
  const [attributed, setAttributed] = useState<Set<number>>(new Set())
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setBusy(true)
    try {
      setResult(await submitDictation(mat.id, answers))
    } finally {
      setBusy(false)
    }
  }

  const attribute = async (idx: number, reason: string) => {
    if (!result) return
    await submitAttribution(result.practice_id, idx, reason)
    setAttributed((prev) => new Set(prev).add(idx))
  }

  return (
    <div className="space-y-3">
      {mat.sentences.map((_s, i) => (
        <div key={i} className="rounded-xl border border-slate-200 bg-white p-3">
          <div className="flex items-center gap-3">
            <button onClick={() => play(i)}
              className="shrink-0 rounded-lg bg-indigo-50 px-3 py-1 text-sm text-indigo-600">
              ▶ 第 {i + 1} 句
            </button>
            <input
              className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-indigo-400 focus:outline-none"
              placeholder="听写这一句…"
              value={answers[i]}
              onChange={(e) => {
                const next = [...answers]
                next[i] = e.target.value
                setAnswers(next)
              }}
              disabled={result !== null}
            />
          </div>
          {result && (
            <div className="mt-2 border-t border-slate-100 pt-2">
              <DiffTokens tokens={result.per_sentence[i].diff.tokens} />
              {!result.per_sentence[i].correct && (
                <div className="mt-2 flex items-center gap-2 text-xs">
                  <span className="text-slate-400">归因：</span>
                  {attributed.has(i) ? (
                    <span className="text-emerald-600">已记录 ✓</span>
                  ) : (
                    REASONS.map((r) => (
                      <button key={r} onClick={() => attribute(i, r)}
                        className="rounded border border-slate-200 px-2 py-0.5 text-slate-500 hover:border-indigo-300">
                        {r}
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
      {!result ? (
        <button onClick={submit} disabled={busy}
          className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white disabled:opacity-40">
          {busy ? '比对中…' : '提交比对'}
        </button>
      ) : (
        <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-center">
          <span className="text-sm text-slate-500">本篇正确率</span>
          <div className="text-3xl font-bold text-indigo-600">{result.accuracy}%</div>
        </div>
      )}
    </div>
  )
}

function ShadowingMode({ mat }: { mat: MatDetailOut }) {
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ShadowingResult | null>(null)
  const [error, setError] = useState('')
  const recorderRef = useRef<WavRecorder | null>(null)

  useEffect(() => () => {
    if (recorderRef.current) {
      const r = recorderRef.current
      recorderRef.current = null
      void r.stop()
    }
  }, [])

  const toggle = async () => {
    if (recording) {
      const recorder = recorderRef.current
      if (!recorder) return
      recorderRef.current = null
      setRecording(false)
      setBusy(true)
      setError('')
      try {
        const blob = await recorder.stop()
        setResult(await submitShadowing(mat.id, blob))
      } catch (e) {
        setError(String(e))
      } finally {
        setBusy(false)
      }
    } else {
      try {
        recorderRef.current = new WavRecorder()
        await recorderRef.current.start()
        setRecording(true)
        setResult(null)
      } catch {
        setError('无法访问麦克风，请检查浏览器权限')
      }
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
        <div className="mb-2 font-semibold">原文（{mat.sentences.length} 句）</div>
        {mat.sentences.map((s, i) => <p key={i} className="leading-7">{s}</p>)}
      </div>
      <button onClick={toggle} disabled={busy}
        className={`w-full rounded-xl py-3 font-semibold text-white disabled:opacity-40 ${
          recording ? 'bg-red-500' : 'bg-indigo-600'
        }`}>
        {recording ? '■ 停止并比对' : busy ? '转写比对中…' : '● 开始跟读录音'}
      </button>
      {error && <div className="text-sm text-red-500">{error}</div>}
      {result && (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-sm font-semibold">跟读比对</span>
            {result.is_mock && (
              <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">演示数据</span>
            )}
          </div>
          <div className="mb-2 text-sm text-slate-500">你的转写：{result.transcript}</div>
          <DiffTokens tokens={result.diff.tokens} />
        </div>
      )}
    </div>
  )
}
