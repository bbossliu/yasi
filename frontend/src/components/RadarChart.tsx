import { useEcharts } from '../hooks/useEcharts'
import type { BandScores } from '../api/types'

export function RadarChart({ bands }: { bands: BandScores }) {
  const ref = useEcharts({
    radar: {
      indicator: [
        { name: '任务回应 TR', max: 9 },
        { name: '连贯衔接 CC', max: 9 },
        { name: '词汇资源 LR', max: 9 },
        { name: '语法 GRA', max: 9 },
      ],
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: [bands.task_response, bands.coherence, bands.lexical, bands.grammar],
            name: '本次得分',
            areaStyle: { opacity: 0.25 },
            itemStyle: { color: '#4f46e5' },
          },
        ],
      },
    ],
    animationDuration: 1200,
  })
  return <div ref={ref} className="h-72 w-full" />
}
