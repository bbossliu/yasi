import { motion } from 'framer-motion'

export function ScanOverlay({ text }: { text: string }) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-white p-6">
      <pre className="whitespace-pre-wrap font-mono text-sm text-slate-500">{text}</pre>
      <motion.div
        className="absolute inset-x-0 h-16 bg-gradient-to-b from-transparent via-indigo-300/40 to-transparent"
        initial={{ top: '-10%' }}
        animate={{ top: '110%' }}
        transition={{ duration: 2.2, repeat: Infinity, ease: 'linear' }}
      />
      <div className="mt-4 text-center text-sm text-indigo-500">AI 考官正在逐句批改，请稍候…</div>
    </div>
  )
}
