import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { finishSpeakingSession, getSpeakingTurn, submitSpeakingTurn } from '../api/client'
import type { SessionOut, SessionSummary, SpeakingFeedback } from '../api/types'
import { SpeakingFeedbackCard } from '../components/SpeakingFeedbackCard'
import { WavRecorder } from '../lib/recorder'

interface Msg {
  role: 'examiner' | 'user' | 'system'
  text: string
  ttsUrl?: string | null
  audioUrl?: string
  feedback?: SpeakingFeedback
}

const PART2_RECORD_SEC = 120
const DEFAULT_RECORD_SEC = 180
const PART2_PREP_SEC = 60

export default function PracticeRoom() {
  const location = useLocation()
  const navigate = useNavigate()
  const session = (location.state as { session?: SessionOut } | null)?.session

  const [messages, setMessages] = useState<Msg[]>([])
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [summary, setSummary] = useState<SessionSummary | null>(null)
  const [prepLeft, setPrepLeft] = useState<number | null>(null)
  const [error, setError] = useState('')
  const recorderRef = useRef<WavRecorder | null>(null)
  const recordTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!session) return
    setMessages([{ role: 'examiner', text: session.question, ttsUrl: session.tts_url }])
    if (session.part === 2) {
      setPrepLeft(PART2_PREP_SEC)
    }
  }, [session?.id])

  // Part 2 准备倒计时
  useEffect(() => {
    if (prepLeft === null || prepLeft <= 0) return
    const t = setTimeout(() => setPrepLeft(prepLeft - 1), 1000)
    return () => clearTimeout(t)
  }, [prepLeft])

  // 卸载时释放录音资源
  useEffect(() => {
    return () => {
      if (recordTimerRef.current) {
        clearTimeout(recordTimerRef.current)
        recordTimerRef.current = null
      }
      if (recorderRef.current) {
        void recorderRef.current.stop()
        recorderRef.current = null
      }
    }
  }, [])

  if (!session) {
    return (
      <div className="p-10 text-slate-400">
        会话信息缺失，请从
        <button className="text-indigo-600 hover:underline" onClick={() => navigate('/speaking')}>
          口语练习页
        </button>
        重新开始。
      </div>
    )
  }

  const startRecord = async () => {
    setError('')
    try {
      recorderRef.current = new WavRecorder()
      await recorderRef.current.start()
      setRecording(true)
      const maxSec = session.part === 2 ? PART2_RECORD_SEC : DEFAULT_RECORD_SEC
      recordTimerRef.current = setTimeout(() => stopRecord(), maxSec * 1000)
    } catch {
      setError('无法访问麦克风，请检查浏览器权限')
    }
  }

  const stopRecord = async () => {
    const recorder = recorderRef.current
    if (!recorder) return
    recorderRef.current = null
    if (recordTimerRef.current) {
      clearTimeout(recordTimerRef.current)
      recordTimerRef.current = null
    }
    setRecording(false)
    setBusy(true)
    try {
      const blob = await recorder.stop()
      const audioUrl = URL.createObjectURL(blob)
      const { practice_id } = await submitSpeakingTurn(session.id, blob)
      // 轮询该轮结果（最多 30 次 × 2s ≈ 60s）
      let detail = await getSpeakingTurn(practice_id)
      let polls = 0
      while (detail.status === 'pending' && polls < 30) {
        await new Promise((r) => setTimeout(r, 2000))
        detail = await getSpeakingTurn(practice_id)
        polls++
      }
      if (detail.status === 'pending') {
        setMessages((m) => [...m, { role: 'system', text: '评分超时，请重新回答。' }])
        return
      }
      if (detail.status === 'needs_review' || !detail.feedback) {
        setMessages((m) => [...m, { role: 'system', text: '本次转写/评分未完成，请重新回答该问题。' }])
        return
      }
      setMessages((m) => [
        ...m,
        {
          role: 'user',
          text: detail.transcript ?? '',
          audioUrl,
          feedback: detail.feedback ?? undefined,
        },
      ])
      if (detail.session_done) {
        setDone(true)
        setSummary(await finishSpeakingSession(session.id))
      } else if (detail.next_question) {
        setMessages((m) => [...m, {
          role: 'examiner', text: detail.next_question!, ttsUrl: detail.next_tts_url,
        }])
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const finishEarly = async () => {
    if (recorderRef.current) {
      if (recordTimerRef.current) {
        clearTimeout(recordTimerRef.current)
        recordTimerRef.current = null
      }
      const recorder = recorderRef.current
      recorderRef.current = null
      void recorder.stop()
      setRecording(false)
    }
    try {
      const summary = await finishSpeakingSession(session.id)
      setDone(true)
      setSummary(summary)
    } catch (e) {
      setError(String(e))
    }
  }

  const canRecord = !busy && !done && (session.part !== 2 || prepLeft === 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <span className="rounded bg-indigo-100 px-2 py-0.5 text-xs text-indigo-600">
            Part {session.part}
          </span>
          <span className="ml-2 font-semibold">{session.topic}</span>
        </div>
        {!done && (
          <button onClick={finishEarly} className="text-sm text-slate-400 hover:text-slate-600">
            结束会话
          </button>
        )}
      </div>

      {prepLeft !== null && prepLeft > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-center text-amber-700">
          准备时间：{prepLeft} 秒（Part 2 请先构思，倒计时结束后开始录音）
        </div>
      )}

      <div className="space-y-3">
        {messages.map((msg, i) => (
          <div key={i} className={msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            <div className={`max-w-[80%] rounded-2xl p-4 ${
              msg.role === 'examiner' ? 'bg-white border border-slate-200'
              : msg.role === 'user' ? 'bg-indigo-600 text-white'
              : 'bg-amber-50 border border-amber-200 text-amber-700 text-sm'
            }`}>
              {msg.role === 'examiner' && (
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-xs text-slate-400">AI 考官</span>
                  {msg.ttsUrl && (
                    <audio controls src={msg.ttsUrl} className="h-7 max-w-[220px]" />
                  )}
                </div>
              )}
              <div className="whitespace-pre-wrap text-sm">{msg.text}</div>
              {msg.audioUrl && <audio controls src={msg.audioUrl} className="mt-2 h-8" />}
              {msg.feedback && <SpeakingFeedbackCard feedback={msg.feedback} />}
            </div>
          </div>
        ))}
        {busy && <div className="text-center text-sm text-indigo-400">AI 考官正在听写并评分…</div>}
      </div>

      {error && <div className="text-sm text-red-500">{error}</div>}

      {!done ? (
        <button
          onClick={recording ? stopRecord : startRecord}
          disabled={!recording && !canRecord}
          className={`w-full rounded-xl py-3 font-semibold text-white disabled:opacity-40 ${
            recording ? 'bg-red-500' : 'bg-indigo-600'
          }`}
        >
          {recording ? '■ 停止并提交' : busy ? '评分中…' : '● 开始录音回答'}
        </button>
      ) : (
        summary && (
          <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
            <div className="text-sm text-slate-400">本次会话均分</div>
            <div className="text-4xl font-bold text-indigo-600">
              {summary.avg_band !== null ? summary.avg_band.toFixed(1) : '—'}
            </div>
            <div className="mt-2 text-sm text-slate-500">
              完成 {summary.turns.length} 轮问答
            </div>
            <button
              onClick={() => navigate('/speaking')}
              className="mt-4 rounded-lg bg-indigo-600 px-6 py-2 text-white"
            >
              返回再练
            </button>
          </div>
        )
      )}
    </div>
  )
}
