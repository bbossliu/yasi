import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  getReviewQueue, getVocabForecast, listVocabTopics, listVocabWords, submitReview,
} from '../api/client'
import type { ForecastOut, ReviewCardOut, TopicOut, WordOut } from '../api/types'
import { useEcharts } from '../hooks/useEcharts'

export default function VocabPage() {
  const [topics, setTopics] = useState<TopicOut[]>([])
  const [selected, setSelected] = useState('')
  const [words, setWords] = useState<WordOut[]>([])
  const [reviewing, setReviewing] = useState(false)
  const [queue, setQueue] = useState<ReviewCardOut[]>([])
  const [dueTotal, setDueTotal] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    listVocabTopics().then((t) => {
      setTopics(t)
      if (t.length && !selected) setSelected(t[0].topic)
    }).catch((e) => setError(String(e)))
    getReviewQueue().then((q) => setDueTotal(q.due_total)).catch(() => undefined)
  }, [])

  useEffect(() => {
    if (!selected) return
    listVocabWords(selected).then(setWords).catch((e) => setError(String(e)))
  }, [selected])

  const startReview = async () => {
    const q = await getReviewQueue(20)
    if (q.cards.length === 0) {
      setError('词库已全部安排复习，暂无到期卡片')
      return
    }
    setQueue(q.cards)
    setReviewing(true)
  }

  if (reviewing) {
    return (
      <ReviewSession
        initialQueue={queue}
        onFinish={() => {
          setReviewing(false)
          listVocabTopics().then(setTopics)
          getReviewQueue().then((q) => setDueTotal(q.due_total))
        }}
      />
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap gap-2">
          {topics.map((t) => (
            <button
              key={t.topic}
              onClick={() => setSelected(t.topic)}
              className={`rounded-lg px-3 py-1.5 text-sm ${
                selected === t.topic
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white border border-slate-200 text-slate-600'
              }`}
            >
              {t.topic}
              <span className="ml-1 text-xs opacity-70">
                {t.mastered_count}/{t.word_count}
                {t.due_count > 0 && ` · ${t.due_count} 待复习`}
              </span>
            </button>
          ))}
        </div>
        <button
          onClick={startReview}
          className={`rounded-xl px-5 py-2 font-semibold text-white ${
            dueTotal > 0 ? 'bg-amber-500' : 'bg-indigo-600'
          }`}
        >
          开始复习{dueTotal > 0 ? `（${dueTotal} 到期）` : ''}
        </button>
      </div>
      {error && <div className="text-sm text-red-500">{error}</div>}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {words.map((w) => (
          <div key={w.id} className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex items-baseline gap-2">
              <span className="text-lg font-bold text-slate-800">{w.text}</span>
              <span className="text-xs text-slate-400">{w.pos}</span>
              {w.reps > 0 && (
                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700">
                  已复习 {w.reps} 次
                </span>
              )}
            </div>
            <div className="mt-0.5 text-sm text-slate-600">{w.meaning}</div>
            <div className="mt-1 text-xs italic text-slate-400">{w.example_sentence}</div>
            <div className="mt-2 flex flex-wrap gap-1">
              {w.paraphrase_chain.map((p) => (
                <span
                  key={p}
                  title={p}
                  className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600"
                >
                  {p}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ReviewSession({ initialQueue, onFinish }: {
  initialQueue: ReviewCardOut[]
  onFinish: () => void
}) {
  const [queue, setQueue] = useState(initialQueue)
  const [flipped, setFlipped] = useState(false)
  const [doneCount, setDoneCount] = useState(0)
  const [forecast, setForecast] = useState<ForecastOut[]>([])

  const current = queue[0]

  // 队列走完（完成页挂载）时拉取到期分布
  useEffect(() => {
    if (queue.length === 0) {
      getVocabForecast().then(setForecast).catch(() => undefined)
    }
  }, [queue.length])

  const rate = async (quality: 1 | 3 | 5) => {
    if (!current) return
    await submitReview(current.word_id, quality)
    setDoneCount((n) => n + 1)
    setQueue((q) => q.slice(1))
    setFlipped(false)
  }

  const chartRef = useEcharts({
    xAxis: { type: 'category', data: forecast.map((f) => f.date.slice(5)) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{ type: 'bar', data: forecast.map((f) => f.count), itemStyle: { color: '#4f46e5' } }],
    tooltip: {},
  })

  if (!current) {
    return (
      <div className="space-y-4">
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-8 text-center">
          <div className="text-2xl font-bold text-emerald-700">本轮完成！</div>
          <div className="mt-1 text-sm text-slate-500">共复习 {doneCount} 张卡片</div>
        </div>
        {forecast.length > 0 && (
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="mb-2 text-sm font-semibold">未来 7 天到期分布</div>
            <div ref={chartRef} className="h-48 w-full" />
          </div>
        )}
        <button onClick={onFinish}
          className="w-full rounded-xl bg-indigo-600 py-3 font-semibold text-white">
          返回词库
        </button>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div className="text-center text-sm text-slate-400">
        第 {doneCount + 1} / {doneCount + queue.length} 张
        {current.is_new && <span className="ml-2 rounded bg-sky-100 px-2 py-0.5 text-xs text-sky-700">新词</span>}
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={current.word_id + String(flipped)}
          initial={{ rotateY: 90, opacity: 0 }}
          animate={{ rotateY: 0, opacity: 1 }}
          exit={{ rotateY: -90, opacity: 0 }}
          transition={{ duration: 0.2 }}
          onClick={() => setFlipped(!flipped)}
          className="cursor-pointer rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm"
        >
          {!flipped ? (
            <>
              <div className="text-3xl font-bold text-slate-800">{current.text}</div>
              <div className="mt-1 text-sm text-slate-400">{current.pos}</div>
              <div className="mt-6 text-xs text-slate-300">点击卡片查看释义</div>
            </>
          ) : (
            <div className="space-y-3 text-left">
              <div className="text-center">
                <span className="text-2xl font-bold">{current.text}</span>
                <span className="ml-2 text-sm text-slate-400">{current.pos}</span>
              </div>
              <div className="text-slate-700">{current.meaning}</div>
              <div className="text-sm italic text-slate-500">{current.example_sentence}</div>
              <div className="flex flex-wrap gap-1">
                {current.paraphrase_chain.map((p) => (
                  <span key={p}
                    className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600">
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}
        </motion.div>
      </AnimatePresence>
      {flipped && (
        <div className="grid grid-cols-3 gap-3">
          <button onClick={() => rate(1)}
            className="rounded-xl bg-red-500 py-3 font-semibold text-white">不认识</button>
          <button onClick={() => rate(3)}
            className="rounded-xl bg-amber-500 py-3 font-semibold text-white">模糊</button>
          <button onClick={() => rate(5)}
            className="rounded-xl bg-emerald-600 py-3 font-semibold text-white">认识</button>
        </div>
      )}
    </div>
  )
}
