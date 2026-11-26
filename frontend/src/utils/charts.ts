// https://echarts.apache.org/handbook/en/basics/import/
import { use } from 'echarts/core'
import { BarChart, LineChart, RadarChart } from 'echarts/charts'
import { AxisPointerComponent, GridComponent, LegendComponent, MarkLineComponent, RadarComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([BarChart, LineChart, RadarChart, AxisPointerComponent, GridComponent, LegendComponent,
  MarkLineComponent, RadarComponent, TitleComponent, TooltipComponent, CanvasRenderer])

export { init } from 'echarts/core'
export type { EChartsType as ECharts } from 'echarts/core'
export type { EChartsOption, SeriesOption } from 'echarts'
