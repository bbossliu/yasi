import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getEssay } from '../api/client'
import type { EssayDetail } from '../api/types'
import { AnnotationList } from '../components/AnnotationList'
import { DiffView } from '../components/DiffView'
import { RadarChart } from '../components/RadarChart'
import { ScanOverlay } from '../components/ScanOverlay'

export default function ResultPage() {
  const { id } = useParams<{ id: string }>()
  const [essay, setEssay] = useState<EssayDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!id) return
    let stopped = false
    const poll = async () => {
      try {
        const detail = await getEssay(Number(id))
        if (stopped) return
        setEssay(detail)
        if (detail.status === 'pending') {
          setTimeout(poll, 2000)
        }
      } catch (e) {
        if (!stopped) setError(String(e))
      }
    }
    poll()
    return () => { stopped = true }
  }, [id])

  if (error) return <div className="p-10 text-red-500">{error}</div>
  if (!essay) return <div className="p-10 text-slate-400">加载中…</div>

  if (essay.status === 'pending') {
    return <ScanOverlay text={essay.content} />
  }
  if (essay.status === 'needs_review' || !essay.feedback) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-amber-700">
        本次批改未能完成（AI 返回格式异常或服务不可用），请重新提交。原文已保存在历史记录中。
      </div>
    )
  }

  const fb = essay.feedback
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6">
        <div className="rounded-2xl bg-indigo-600 px-8 py-6 text-center text-white">
          <div className="text-sm opacity-80">综合评分</div>
          <div className="text-5xl font-bold">{fb.bands.overall.toFixed(1)}</div>
        </div>
        <div>
          <div className="font-semibold">{essay.prompt_title}</div>
          <div className="text-sm text-slate-400">
            {essay.word_count} 词 · 用时 {Math.round(essay.duration_sec / 60)} 分钟
          </div>
          {fb.is_mock && (
            <div className="mt-1 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">
              演示数据（未配置 DEEPSEEK_API_KEY）
            </div>
          )}
        </div>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <RadarChart bands={fb.bands} />
      </div>
      <div>
        <h3 className="mb-3 font-semibold">逐句批注（{fb.annotations.length} 条）</h3>
        <AnnotationList annotations={fb.annotations} />
      </div>
      <div>
        <h3 className="mb-3 font-semibold">原文 vs 改写版</h3>
        <DiffView original={essay.content} rewrite={fb.rewrite} annotations={fb.annotations} />
      </div>
    </div>
  )
}
