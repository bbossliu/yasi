import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'

export function useEcharts(option: EChartsOption) {
  const ref = useRef<HTMLDivElement>(null)
  const optionJson = JSON.stringify(option)
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chart.setOption(JSON.parse(optionJson))
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
    }
  }, [optionJson])
  return ref
}
