import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  completeMockExam, createMockExam, getExamEligibility, getTargetBand,
} from '../api/client'
import type { ExamOut } from '../api/types'
import {
  ExamListeningStep, ExamSpeakingStep, ExamVocabStep, ExamWritingStep,
} from '../components/ExamSteps'

const STEPS = ['写作（40 分钟）', '口语 Part 2', '听力精听', '词汇快测'] as const

export default function MockExamPage() {
  const [step, setStep] = useState(-1)  // -1 = 入口页
  const [eligible, setEligible] = useState<boolean | null>(null)
  const [missing, setMissing] = useState<Record<string, number>>({})
  const [examId, setExamId] = useState(0)
  const [practiceIds, setPracticeIds] = useState<number[]>([])
  const [result, setResult] = useState<ExamOut | null>(null)
  const [target, setTarget] = useState(6.5)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    getExamEligibility().then((e) => {
      setEligible(e.eligible)
      setMissing(e.missing)
    }).catch((e) => setError(String(e)))
    getTargetBand().then((t) => setTarget(t.target_band)).catch(() => undefined)
  }, [])

  const start = async () => {
    const e = await createMockExam()
    setExamId(e.exam_id)
    setStep(0)
  }

  const stepDone = (practiceId: number) => {
    const next = [...practiceIds, practiceId]
    setPracticeIds(next)
    if (step < 3) {
      setStep(step + 1)
    } else {
      completeMockExam(examId, next).then(setResult).catch((e) => setError(String(e)))
    }
  }

  if (result) {
    const passed = (result.predicted_band ?? 0) >= target
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <div className={`rounded-2xl p-8 text-center text-white ${passed ? 'bg-emerald-600' : 'bg-indigo-600'}`}>
          <div className="text-sm opacity-80">预测总分</div>
          <div className="text-6xl font-bold">{result.predicted_band?.toFixed(1)}</div>
          <div className="mt-2 text-lg">{passed ? '🎓 可赴考状态' : `目标 ${target}，继续加油`}</div>
        </div>
        <div className="grid grid-cols-4 gap-3 text-center">
          {Object.entries(result.scores).map(([mod, band]) => (
            <div key={mod} className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="text-xs text-slate-400">
                {{ writing: '写作', speaking: '口语', listening: '听力', vocab: '词汇' }[mod] ?? mod}
              </div>
              <div className="text-xl font-bold">{band.toFixed(1)}</div>
            </div>
          ))}
        </div>
        {typeof result.report === 'object' && (
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <h3 className="mb-2 font-semibold">薄弱点报告</h3>
            {(result.report.top_errors ?? []).length > 0 && (
              <div className="mb-3">
                <div className="text-sm text-slate-400">高频错误</div>
                {(result.report.top_errors ?? []).map((e) => (
                  <div key={e.type} className="flex justify-between text-sm">
                    <span>{e.type}</span><span className="text-slate-400">{e.count} 次</span>
                  </div>
                ))}
              </div>
            )}
            {(result.report.weak_nodes ?? []).length > 0 && (
              <div>
                <div className="text-sm text-slate-400">待回补能力点</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {(result.report.weak_nodes ?? []).map((n) => (
                    <span key={n.code}
                      className="rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-700">
                      {n.title}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        <button onClick={() => navigate('/')}
          className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white">
          回到仪表盘
        </button>
      </div>
    )
  }

  if (step === -1) {
    return (
      <div className="mx-auto max-w-xl space-y-4 text-center">
        <h2 className="text-2xl font-bold">全真模考</h2>
        <p className="text-sm text-slate-500">
          依次完成四个环节：{STEPS.join(' → ')}。完成后 AI 综评输出预测总分与薄弱点报告。
        </p>
        {eligible === false && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-left text-sm text-amber-700">
            <div className="font-semibold">尚未解锁模考</div>
            <div className="mt-1">需要先让所有能力点"学过一遍"（变黄）。当前缺口：</div>
            <ul className="mt-1 list-inside list-disc">
              {Object.entries(missing).map(([mod, n]) => (
                <li key={mod}>{mod}：{n} 个未学节点</li>
              ))}
            </ul>
            <div className="mt-2">去各模块任意练一次即可变黄。</div>
          </div>
        )}
        {eligible && (
          <button onClick={start}
            className="rounded-xl bg-indigo-600 px-8 py-3 text-lg font-semibold text-white">
            开始模考
          </button>
        )}
        {error && <div className="text-sm text-red-500">{error}</div>}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {STEPS.map((s, i) => (
          <span key={s} className={`rounded-lg px-3 py-1 text-xs ${
            i < step ? 'bg-emerald-100 text-emerald-700'
            : i === step ? 'bg-indigo-600 text-white'
            : 'bg-slate-100 text-slate-400'
          }`}>
            {i + 1}. {s}
          </span>
        ))}
      </div>
      {step === 0 && <ExamWritingStep onDone={stepDone} />}
      {step === 1 && <ExamSpeakingStep onDone={stepDone} />}
      {step === 2 && <ExamListeningStep onDone={stepDone} />}
      {step === 3 && <ExamVocabStep onDone={stepDone} />}
      {error && <div className="text-sm text-red-500">{error}</div>}
    </div>
  )
}
