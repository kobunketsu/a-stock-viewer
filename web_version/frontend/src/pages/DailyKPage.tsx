import { useMemo, useState } from 'react'
import { Card, Form, Input, Button, Space, Typography, Row, Col } from 'antd'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import type { SeriesOption } from 'echarts'
import { useKLine } from '../api/kline'

const formatDate = (value: string) => dayjs(value).format('YYYY-MM-DD')

const mapNullable = (values: (number | null)[] | undefined, transform: (v: number) => number = (v) => v) =>
  values?.map((value) => (value === null || value === undefined ? null : transform(value))) ?? []

function DailyKPage() {
  const [code, setCode] = useState('600519')
  const [submittedCode, setSubmittedCode] = useState('600519')
  const { data, isLoading, isError } = useKLine(submittedCode, Boolean(submittedCode))

  const handleSubmit = (value: { code: string }) => {
    setSubmittedCode(value.code)
  }

  const categories = useMemo(() => data?.kline.map((item) => formatDate(item.timestamp)) ?? [], [data])

  const klineOption = useMemo(() => {
    if (!data) return {}
    const candleValues = data.kline.map((item) => [item.open, item.close, item.low, item.high])
    const legend: string[] = ['日K']

    const series: SeriesOption[] = [
      {
        name: '日K',
        type: 'candlestick',
        data: candleValues,
        itemStyle: {
          color: '#ff4d4f',
          color0: '#3f8600',
          borderColor: '#ff4d4f',
          borderColor0: '#3f8600'
        }
      }
    ]

    Object.entries(data.indicators.ma).forEach(([name, values]) => {
      legend.push(name.toUpperCase())
      series.push({
        name: name.toUpperCase(),
        type: 'line',
        data: mapNullable(values),
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 1.2 }
      })
    })

    const boll = data.indicators.bollinger
    legend.push('布林上轨', '布林中轨', '布林下轨')
    series.push(
      {
        name: '布林上轨',
        type: 'line',
        data: mapNullable(boll.upper),
        showSymbol: false,
        lineStyle: { type: 'dashed', color: '#ff69b4' }
      },
      {
        name: '布林中轨',
        type: 'line',
        data: mapNullable(boll.middle),
        showSymbol: false,
        lineStyle: { type: 'dotted', color: '#999999' }
      },
      {
        name: '布林下轨',
        type: 'line',
        data: mapNullable(boll.lower),
        showSymbol: false,
        lineStyle: { type: 'dashed', color: '#4169e1' }
      }
    )

    legend.push('平均成本')
    series.push({
      name: '平均成本',
      type: 'line',
      data: mapNullable(data.indicators.average_cost),
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 1.6, color: '#ff69b4' }
    })

    const cost70Low = mapNullable(data.chip_distribution.cost_70_low)
    const cost70High = mapNullable(data.chip_distribution.cost_70_high)
    const cost90Low = mapNullable(data.chip_distribution.cost_90_low)
    const cost90High = mapNullable(data.chip_distribution.cost_90_high)

    const buildSpan = (high: (number | null)[], low: (number | null)[]) =>
      high.map((value, idx) => {
        const lowValue = low[idx]
        if (value === null || lowValue === null || value === undefined || lowValue === undefined) return null
        return Number((value - lowValue).toFixed(3))
      })

    const cost70Span = buildSpan(cost70High, cost70Low)
    const cost90Span = buildSpan(cost90High, cost90Low)

    legend.push('70%成本上沿', '90%成本上沿')
    series.push(
      {
        name: '70%成本基线',
        type: 'line',
        stack: 'cost70',
        data: cost70Low,
        showSymbol: false,
        lineStyle: { opacity: 0 },
        areaStyle: { opacity: 0 },
        tooltip: { show: false }
      },
      {
        name: '70%成本区间',
        type: 'line',
        stack: 'cost70',
        data: cost70Span,
        showSymbol: false,
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(147, 112, 219, 0.25)' },
        tooltip: { show: false }
      },
      {
        name: '70%成本上沿',
        type: 'line',
        data: cost70High,
        showSymbol: false,
        lineStyle: { color: '#9370db', width: 1.2 }
      },
      {
        name: '90%成本基线',
        type: 'line',
        stack: 'cost90',
        data: cost90Low,
        showSymbol: false,
        lineStyle: { opacity: 0 },
        areaStyle: { opacity: 0 },
        tooltip: { show: false }
      },
      {
        name: '90%成本区间',
        type: 'line',
        stack: 'cost90',
        data: cost90Span,
        showSymbol: false,
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(255, 215, 0, 0.2)' },
        tooltip: { show: false }
      },
      {
        name: '90%成本上沿',
        type: 'line',
        data: cost90High,
        showSymbol: false,
        lineStyle: { color: '#ffd700', width: 1.2 }
      }
    )

    const selectedLegend: Record<string, boolean> = {}
    legend.forEach((name) => {
      selectedLegend[name] = true
    })

    return {
      animation: false,
      legend: {
        data: legend,
        selected: selectedLegend
      },
      tooltip: {
        trigger: 'axis'
      },
      axisPointer: {
        type: 'cross'
      },
      dataZoom: [
        { type: 'inside', minSpan: 10 },
        { type: 'slider' }
      ],
      xAxis: {
        type: 'category',
        data: categories,
        boundaryGap: false
      },
      yAxis: {
        scale: true
      },
      series
    }
  }, [data, categories])

  const volumeOption = useMemo(() => {
    if (!data) return {}
    const volumes = data.kline.map((item) => item.volume)
    const predicted = data.indicators.volume?.predicted ?? null
    const predictedSeries = categories.map((_, idx) => (idx === categories.length - 1 ? predicted : null))

    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: categories, boundaryGap: true },
      yAxis: {
        type: 'value',
        axisLabel: {
          formatter: (value: number) =>
            value >= 1e8 ? `${(value / 1e8).toFixed(1)}亿` : value >= 1e4 ? `${(value / 1e4).toFixed(0)}万` : `${value}`
        }
      },
      series: [
        {
          name: '成交量',
          type: 'bar',
          data: volumes,
          itemStyle: {
            color: (params: any) => (data.kline[params.dataIndex].close >= data.kline[params.dataIndex].open ? '#ff7875' : '#73d13d')
          }
        },
        {
          name: '预测量',
          type: 'line',
          data: predictedSeries,
          showSymbol: true,
          symbolSize: 8,
          lineStyle: { type: 'dashed', color: '#ffa940' },
          itemStyle: { color: '#ffa940' }
        }
      ]
    }
  }, [data, categories])

  const rsiOption = useMemo(() => {
    if (!data) return {}
    const rsi = data.indicators.rsi
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: { data: ['RSI6', 'RSI12', 'RSI24'] },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value', min: 0, max: 100 },
      series: [
        { name: 'RSI6', type: 'line', data: mapNullable(rsi.rsi6), showSymbol: false },
        { name: 'RSI12', type: 'line', data: mapNullable(rsi.rsi12), showSymbol: false },
        { name: 'RSI24', type: 'line', data: mapNullable(rsi.rsi24), showSymbol: false }
      ]
    }
  }, [data, categories])

  const costChangeOption = useMemo(() => {
    if (!data) return {}
    const cost = data.indicators.cost_change
    const daily = mapNullable(cost.daily_change)
    const cumulative = mapNullable(cost.cumulative_positive)
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: { data: ['成本涨幅', '累计正涨幅'] },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      series: [
        {
          name: '成本涨幅',
          type: 'bar',
          data: daily,
          itemStyle: {
            color: (params: any) => (params.value >= 0 ? '#ff6b6b' : '#2ecc71')
          }
        },
        {
          name: '累计正涨幅',
          type: 'line',
          data: cumulative,
          showSymbol: false,
          lineStyle: { width: 1.5, color: '#e74c3c' }
        }
      ]
    }
  }, [data, categories])

  const ma5DeviationOption = useMemo(() => {
    if (!data) return {}
    const deviation = data.indicators.ma5_deviation
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: { data: ['MA5上偏离', 'MA5下偏离'] },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      series: [
        {
          name: 'MA5上偏离',
          type: 'line',
          data: mapNullable(deviation.up),
          showSymbol: false,
          areaStyle: { color: 'rgba(255,107,107,0.25)' },
          lineStyle: { color: '#ff6b6b' }
        },
        {
          name: 'MA5下偏离',
          type: 'line',
          data: mapNullable(deviation.down),
          showSymbol: false,
          areaStyle: { color: 'rgba(46,204,113,0.25)' },
          lineStyle: { color: '#2ecc71' }
        }
      ]
    }
  }, [data, categories])

  const smartMoneyOption = useMemo(() => {
    if (!data) return {}
    const smart = data.indicators.smart_money
    const entity = mapNullable(smart.entity_change_3d, (value) => Number((value * 100).toFixed(2)))
    const profit = mapNullable(smart.smart_profit_3d, (value) => Number((value * 100).toFixed(2)))
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: { data: ['笨蛋线', '聪明线'] },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      series: [
        { name: '笨蛋线', type: 'line', data: entity, showSymbol: false, lineStyle: { width: 1.2 } },
        { name: '聪明线', type: 'line', data: profit, showSymbol: false, lineStyle: { width: 1.2 } }
      ]
    }
  }, [data, categories])

  const fundFlowOption = useMemo(() => {
    if (!data) return {}
    const flow = data.indicators.fund_flow
    if (!flow) return {}
    const divisor = flow.unit === 'shares' ? 1e4 : 1e6
    const unitLabel = flow.unit === 'shares' ? '万股' : '百万元'
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: { data: ['机构', '游资', '散户'] },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value', axisLabel: { formatter: (value: number) => `${value.toFixed(1)}${unitLabel}` } },
      series: [
        {
          name: '机构',
          type: 'line',
          step: 'middle',
          data: mapNullable(flow.institution, (value) => value / divisor),
          showSymbol: false
        },
        {
          name: '游资',
          type: 'line',
          step: 'middle',
          data: mapNullable(flow.hot_money, (value) => value / divisor),
          showSymbol: false
        },
        {
          name: '散户',
          type: 'line',
          step: 'middle',
          data: mapNullable(flow.retail, (value) => value / divisor),
          showSymbol: false
        }
      ]
    }
  }, [data, categories])

  const chipOption = useMemo(() => {
    if (!data) return {}
    return {
      animation: false,
      tooltip: { trigger: 'axis' },
      legend: { data: ['筹码集中度70%', '筹码集中度90%'] },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
      series: [
        {
          name: '筹码集中度70%',
          type: 'line',
          data: mapNullable(data.chip_distribution.concentration_70, (value) => Number((value * 100).toFixed(2))),
          showSymbol: false
        },
        {
          name: '筹码集中度90%',
          type: 'line',
          data: mapNullable(data.chip_distribution.concentration_90, (value) => Number((value * 100).toFixed(2))),
          showSymbol: false
        }
      ]
    }
  }, [data, categories])

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="股票选择">
        <Form layout="inline" onFinish={handleSubmit} initialValues={{ code }}>
          <Form.Item name="code" rules={[{ required: true, message: '请输入股票代码' }]}>
            <Input placeholder="请输入股票代码" style={{ width: 200 }} value={code} onChange={(e) => setCode(e.target.value)} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={isLoading}>
              查询
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title={`日K图：${data?.name ?? submittedCode}`} loading={isLoading}>
        {isError ? (
          <Typography.Text type="danger">数据加载失败</Typography.Text>
        ) : (
          <ReactECharts option={klineOption} style={{ height: 420 }} notMerge lazyUpdate />
        )}
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="成交量" loading={isLoading}>
            {isError ? <Typography.Text type="danger">数据加载失败</Typography.Text> : <ReactECharts option={volumeOption} style={{ height: 260 }} />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="RSI指标" loading={isLoading}>
            {isError ? <Typography.Text type="danger">数据加载失败</Typography.Text> : <ReactECharts option={rsiOption} style={{ height: 260 }} />}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="平均成本涨幅" loading={isLoading}>
            {isError ? <Typography.Text type="danger">数据加载失败</Typography.Text> : <ReactECharts option={costChangeOption} style={{ height: 260 }} />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="MA5偏离度" loading={isLoading}>
            {isError ? <Typography.Text type="danger">数据加载失败</Typography.Text> : <ReactECharts option={ma5DeviationOption} style={{ height: 260 }} />}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="3日盈利指标" loading={isLoading}>
            {isError ? <Typography.Text type="danger">数据加载失败</Typography.Text> : <ReactECharts option={smartMoneyOption} style={{ height: 260 }} />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="筹码集中度" loading={isLoading}>
            {isError ? <Typography.Text type="danger">数据加载失败</Typography.Text> : <ReactECharts option={chipOption} style={{ height: 260 }} />}
          </Card>
        </Col>
      </Row>

      <Card title="资金来源净额" loading={isLoading}>
        {isError ? <Typography.Text type="danger">数据加载失败</Typography.Text> : <ReactECharts option={fundFlowOption} style={{ height: 260 }} />}
      </Card>
    </Space>
  )
}

export default DailyKPage
