import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getClearance, getLatestExam, getTargetBand, listErrors, listEssays,
  listVocabTopics, setTargetBand,
} from '../api/client'
import type { ClearanceOut, EssayOut, ErrorItemOut, ExamOut } from '../api/types'

const TARGET_OPTIONS = [6.0, 6.5, 7.0, 7.5]

const MODULE_LABELS: Record<string, string> = {
  writing: '写作',
  speaking: '口语',
  listening: '听力',
  vocab: '词汇',
}
const MODULE_ORDER = ['writing', 'speaking', 'listening', 'vocab']

// 与后端 exam_scoring.py 保持一致的映射
function accuracyToBand(acc: number): number {
  if (acc < 40) return 4.5
  if (acc < 55) return 5.0
  if (acc < 70) return 5.5
  if (acc < 80) return 6.0
  if (acc < 90) return 6.5
  if (acc < 95) return 7.0
  return 7.5
}

function vocabRateToBand(rate: number): number {
  if (rate < 0.5) return 5.0
  if (rate < 0.7) return 5.5
  if (rate < 0.85) return 6.0
  if (rate < 0.95) return 6.5
  return 7.0
}

function overallRound(avg: number): number {
  const whole = Math.floor(avg)
  const frac = avg - whole
  if (frac < 0.25) return whole
  if (frac < 0.75) return whole + 0.5
  return whole + 1
}

interface EstimateSource {
  writing: number | null
  speaking: number | null
  listeningAcc: number | null
  vocabRate: number | null
}

function estimateBand(src: EstimateSource): number | null {
  const bands: number[] = []
  if (src.writing !== null) bands.push(src.writing)
  if (src.speaking !== null) bands.push(src.speaking)
  if (src.listeningAcc !== null) bands.push(accuracyToBand(src.listeningAcc))
  if (src.vocabRate !== null) bands.push(vocabRateToBand(src.vocabRate))
  if (bands.length === 0) return null
  return overallRound(bands.reduce((a, b) => a + b, 0) / bands.length)
}

export default function DashboardPage() {
  const [essays, setEssays] = useState<EssayOut[]>([])
  const [errors, setErrors] = useState<ErrorItemOut[]>([])
  const [vocab, setVocab] = useState({ mastered: 0, total: 0, due: 0 })
  const [clearance, setClearance] = useState<ClearanceOut[]>([])
  const [latestExam, setLatestExam] = useState<ExamOut | null>(null)
  const [target, setTarget] = useState(6.5)

  useEffect(() => {
    listEssays().then(setEssays).catch(() => undefined)
    listErrors().then(setErrors).catch(() => undefined)
    listVocabTopics().then((topics) => setVocab({
      mastered: topics.reduce((n, t) => n + t.mastered_count, 0),
      total: topics.reduce((n, t) => n + t.word_count, 0),
      due: topics.reduce((n, t) => n + t.due_count, 0),
    })).catch(() => undefined)
    getClearance().then(setClearance).catch(() => undefined)
    getLatestExam().then(setLatestExam).catch(() => undefined)
    getTargetBand().then((t) => setTarget(t.target_band)).catch(() => undefined)
  }, [])

  const latest = essays.find((e) => e.total_band !== null && e.module === 'writing')
  const latestSpeaking = essays.find((e) => e.total_band !== null && e.module === 'speaking')
  const latestListening = essays.find((e) => e.total_band !== null && e.module === 'listening')
  const topErrors = useMemo(() => {
    const counts = new Map<string, number>()
    for (const e of errors) counts.set(e.error_type, (counts.get(e.error_type) ?? 0) + 1)
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5)
  }, [errors])

  const vocabRate = vocab.total > 0 ? vocab.mastered / vocab.total : null
  const predicted = latestExam?.predicted_band ?? estimateBand({
    writing: latest?.total_band ?? null,
    speaking: latestSpeaking?.total_band ?? null,
    listeningAcc: latestListening?.total_band ?? null,
    vocabRate,
  })
  const examReady = predicted !== null && predicted >= target
  const progress = predicted !== null ? Math.min(predicted / target, 1) : 0

  const masteryOf = (module: string): number => {
    if (module === 'vocab') return vocabRate ?? 0
    return clearance.find((c) => c.module === module)?.mastery_rate ?? 0
  }

  const onTargetChange = (band: number) => {
    setTarget(band)
    setTargetBand(band).catch(() => undefined)
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-sm text-slate-400">当前预测分 → 目标分</div>
            <div className="mt-1 text-4xl font-bold text-indigo-600">
              {predicted !== null ? predicted.toFixed(1) : '—'}
              <span className="text-lg font-normal text-slate-400"> / {target.toFixed(1)}</span>
            </div>
            {latestExam === null && predicted !== null && (
              <div className="mt-1 text-xs text-slate-400">暂无模考，按各科最近成绩滚动估计</div>
            )}
          </div>
          <div className="flex items-center gap-3">
            {examReady && (
              <span className="rounded-full bg-emerald-100 px-3 py-1 text-sm font-medium text-emerald-700">
                可赴考
              </span>
            )}
            <label className="text-sm text-slate-500">
              目标分
              <select
                className="ml-2 rounded-lg border border-slate-300 px-2 py-1 text-sm"
                value={target}
                onChange={(e) => onTargetChange(Number(e.target.value))}
              >
                {TARGET_OPTIONS.map((b) => (
                  <option key={b} value={b}>{b.toFixed(1)}</option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <div className="mt-4 h-2 rounded-full bg-slate-100">
          <div
            className={`h-2 rounded-full transition-all ${examReady ? 'bg-emerald-500' : 'bg-indigo-500'}`}
            style={{ width: `${progress * 100}%` }}
          />
        </div>
        <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          {MODULE_ORDER.map((m) => {
            const rate = masteryOf(m)
            return (
              <div key={m}>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">{MODULE_LABELS[m]}掌握率</span>
                  <span className="text-slate-400">{Math.round(rate * 100)}%</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-slate-100">
                  <div
                    className="h-1.5 rounded-full bg-indigo-400 transition-all"
                    style={{ width: `${Math.min(rate, 1) * 100}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">写作最新分</div>
          <div className="mt-1 text-3xl font-bold text-indigo-600">
            {latest?.total_band?.toFixed(1) ?? '—'}
          </div>
          <Link to="/write" className="mt-3 inline-block text-sm text-indigo-600 hover:underline">
            开始新一篇 →
          </Link>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">口语最新分</div>
          <div className="mt-1 text-3xl font-bold text-emerald-600">
            {latestSpeaking?.total_band?.toFixed(1) ?? '—'}
          </div>
          <Link to="/speaking" className="mt-3 inline-block text-sm text-emerald-600 hover:underline">
            去练口语 →
          </Link>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">词汇掌握</div>
          <div className="mt-1 text-3xl font-bold text-amber-600">
            {vocab.mastered}/{vocab.total}
          </div>
          <div className="mt-1 text-sm text-slate-400">
            {vocab.due > 0 ? `${vocab.due} 词今日到期` : '今日无到期'}
          </div>
          <Link to="/vocab" className="mt-3 inline-block text-sm text-amber-600 hover:underline">
            去复习 →
          </Link>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">听力最新正确率</div>
          <div className="mt-1 text-3xl font-bold text-amber-600">
            {latestListening ? `${latestListening.total_band}%` : '—'}
          </div>
          <Link to="/listening" className="mt-3 inline-block text-sm text-amber-600 hover:underline">
            去精听 →
          </Link>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">累计练习</div>
          <div className="mt-1 text-3xl font-bold">{essays.length} 次</div>
          <Link to="/mock" className="mt-3 inline-block text-sm text-indigo-600 hover:underline">
            去全真模考 →
          </Link>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="text-sm text-slate-400">我的高频错误 TOP</div>
          {topErrors.length > 0 ? (
            <ul className="mt-2 space-y-1 text-sm">
              {topErrors.map(([type, count]) => (
                <li key={type} className="flex justify-between">
                  <span>{type}</span>
                  <span className="text-slate-400">{count} 次</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-2 text-sm text-slate-400">完成一次批改后生成</div>
          )}
        </div>
      </div>
    </div>
  )
}
