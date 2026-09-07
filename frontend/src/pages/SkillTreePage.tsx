import { useEffect, useState } from 'react'
import { evaluateSkills, getClearance, getSkillTree } from '../api/client'
import type { ClearanceOut, ModuleTree, SkillNodeOut } from '../api/types'

const MODULE_NAMES: Record<string, string> = {
  writing: '写作', speaking: '口语', listening: '听力', vocab: '词汇',
}

function dotClass(n: SkillNodeOut) {
  if (n.status === 'verified') return 'bg-emerald-500'
  if (n.status === 'learned') return 'bg-amber-400'
  return 'bg-slate-300'
}

export default function SkillTreePage() {
  const [tree, setTree] = useState<ModuleTree[]>([])
  const [clearance, setClearance] = useState<ClearanceOut[]>([])
  const [message, setMessage] = useState('')

  const load = () => {
    getSkillTree().then(setTree).catch(() => undefined)
    getClearance().then(setClearance).catch(() => undefined)
  }
  useEffect(load, [])

  const reevaluate = async () => {
    const r = await evaluateSkills()
    setMessage(r.updated > 0 ? `新点亮 ${r.updated} 个能力点 🎉` : '暂无新点亮的能力点，继续练习吧')
    load()
  }

  // 按 parent_id 计算缩进深度
  const renderNodes = (nodes: SkillNodeOut[]) => {
    const byId = new Map(nodes.map((n) => [n.id, n]))
    const depth = (n: SkillNodeOut): number =>
      n.parent_id && byId.has(n.parent_id) ? 1 + depth(byId.get(n.parent_id)!) : 0
    return [...nodes].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id).map((n) => (
      <div key={n.id} className="flex items-center gap-2 py-1"
        style={{ paddingLeft: `${depth(n) * 20}px` }}>
        <span className={`h-2.5 w-2.5 rounded-full ${dotClass(n)}`} />
        <span className={`text-sm ${n.status === 'verified' ? 'text-slate-800' : 'text-slate-500'}`}>
          {n.title}
        </span>
        {n.can_verify && (
          <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-600">
            达成条件，待点亮
          </span>
        )}
      </div>
    ))
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">能力树</h2>
        <button onClick={reevaluate}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white">
          重新评估点亮
        </button>
      </div>
      {message && <div className="rounded-lg bg-indigo-50 p-3 text-sm text-indigo-700">{message}</div>}
      <div className="flex gap-4 text-xs text-slate-400">
        <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-slate-300" />未学</span>
        <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-amber-400" />已学未验证</span>
        <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-emerald-500" />已验证掌握</span>
      </div>
      {clearance.map((c) => (
        <div key={c.module} className={`rounded-lg border p-3 text-sm ${
          c.cleared ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-slate-200 bg-white text-slate-500'
        }`}>
          {MODULE_NAMES[c.module]}模块{c.cleared ? '已通关 🎓' : '未通关'}：{c.detail}
          {c.mastery_rate > 0 && `（能力点掌握率 ${(c.mastery_rate * 100).toFixed(0)}%）`}
        </div>
      ))}
      {tree.map((mod) => (
        <div key={mod.module} className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="mb-2 font-semibold">{MODULE_NAMES[mod.module] ?? mod.module}</h3>
          {renderNodes(mod.nodes)}
        </div>
      ))}
    </div>
  )
}
