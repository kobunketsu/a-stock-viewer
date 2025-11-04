import { useEffect, useRef, useState } from 'react'
import { Card, Form, Input, Button, Typography, Space } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useIntraday } from '../api/intraday'
import { useIntradayStream } from '../hooks/useIntradayStream'
import { useHotkeys } from '../hooks/useHotkeys'
import { useAudioAlert } from '../hooks/useAudioAlert'

function IntradayPage() {
  const [code, setCode] = useState('600519')
  const [submittedCode, setSubmittedCode] = useState('600519')
  const stream = useIntradayStream(submittedCode)
  const { data: fallbackData, isLoading: isPolling } = useIntraday(submittedCode, stream.status !== 'connected' && Boolean(submittedCode))
  const data = stream.status === 'connected' ? stream.data ?? [] : fallbackData ?? []
  const isLoading = isPolling && data.length === 0 && stream.status !== 'connected'
  const isError = stream.status === 'error' && !fallbackData
  const lastTimestamp = useRef<string | null>(null)
  const { play: playAlert } = useAudioAlert()

  useHotkeys([
    {
      combo: 'shift+I',
      handler: () => console.info('[hotkey] Shift+I -> refresh intraday (placeholder)'),
      description: '刷新分时数据'
    }
  ])

  useEffect(() => {
    if (stream.status !== 'connected' || data.length === 0) {
      return
    }
    const latest = data[data.length - 1]?.timestamp
    if (latest && latest !== lastTimestamp.current) {
      lastTimestamp.current = latest
      playAlert()
    }
  }, [data, stream.status, playAlert])

  const handleSubmit = (value: { code: string }) => {
    setSubmittedCode(value.code)
  }

  const chartOption = () => {
    if (!data || data.length === 0) return {}

    const categories = data.map((item) => item.timestamp.slice(11, 16))
    const priceSeries = data.map((item) => item.price)
    const volumeSeries = data.map((item) => item.volume)
    const rsiSeries = data.map((item) => item.rsi)

    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['价格', '成交量', 'RSI'] },
      grid: [
        { left: '5%', right: '5%', height: '55%' },
        { left: '5%', right: '5%', top: '62%', height: '18%' }
      ],
      xAxis: [
        {
          type: 'category',
          data: categories,
          boundaryGap: false
        },
        {
          type: 'category',
          data: categories,
          boundaryGap: false,
          gridIndex: 1,
          axisLabel: { show: false }
        }
      ],
      yAxis: [
        { type: 'value', scale: true },
        { type: 'value', gridIndex: 1, scale: true }
      ],
      dataZoom: [{ type: 'inside', xAxisIndex: [0, 1] }, { type: 'slider', xAxisIndex: [0, 1] }],
      series: [
        {
          name: '价格',
          type: 'line',
          data: priceSeries,
          smooth: true
        },
        {
          name: 'RSI',
          type: 'line',
          yAxisIndex: 0,
          data: rsiSeries,
          lineStyle: { type: 'dashed' }
        },
        {
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumeSeries,
          itemStyle: { color: '#91cc75' }
        }
      ]
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="股票选择">
        <Form layout="inline" onFinish={handleSubmit} initialValues={{ code }}>
          <Form.Item name="code" rules={[{ required: true, message: '请输入股票代码' }]}>
            <Input placeholder="请输入股票代码" value={code} onChange={(e) => setCode(e.target.value)} style={{ width: 200 }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={isLoading}>
              查询
            </Button>
          </Form.Item>
        </Form>
      </Card>
      <Card
        title={`分时图：${submittedCode}`}
        loading={isLoading}
        extra={
          <Typography.Text type={stream.status === 'connected' ? 'success' : stream.status === 'error' ? 'danger' : 'warning'}>
            {stream.status === 'connected' ? '实时数据 (WS)' : stream.status === 'error' ? '实时通道异常，使用轮询' : '尝试建立实时通道'}
          </Typography.Text>
        }
      >
        {isError ? (
          <Typography.Text type="danger">数据加载失败</Typography.Text>
        ) : (
          <ReactECharts option={chartOption()} style={{ height: 420 }} />
        )}
      </Card>
    </Space>
  )
}

export default IntradayPage
