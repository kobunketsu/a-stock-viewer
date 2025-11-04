import { useState } from 'react'
import { Card, Form, Input, Button, Space, Typography, Row, Col } from 'antd'
import ReactECharts from 'echarts-for-react'
import dayjs from 'dayjs'
import { useKLine } from '../api/kline'

function DailyKPage() {
  const [code, setCode] = useState('600519')
  const [submittedCode, setSubmittedCode] = useState('600519')
  const { data, isLoading, isError } = useKLine(submittedCode, Boolean(submittedCode))

  const handleSubmit = (value: { code: string }) => {
    setSubmittedCode(value.code)
  }

  const klineOption = () => {
    if (!data) {
      return {}
    }
    const categories = data.kline.map((item) => dayjs(item.timestamp).format('YYYY-MM-DD'))
    const klineValues = data.kline.map((item) => [item.open, item.close, item.low, item.high])
    const volumeValues = data.kline.map((item) => item.volume)

    return {
      animation: false,
      tooltip: {
        trigger: 'axis'
      },
      axisPointer: {
        link: [{ xAxisIndex: 'all' }]
      },
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], minSpan: 10 },
        { type: 'slider', xAxisIndex: [0, 1], bottom: 0 }
      ],
      xAxis: [
        {
          type: 'category',
          data: categories,
          boundaryGap: false
        },
        {
          type: 'category',
          gridIndex: 1,
          data: categories,
          boundaryGap: false,
          axisLabel: { show: false }
        }
      ],
      yAxis: [
        { scale: true },
        { gridIndex: 1, scale: true }
      ],
      grid: [
        { left: '5%', right: '3%', height: '60%' },
        { left: '5%', right: '3%', top: '72%', height: '16%' }
      ],
      series: [
        {
          name: '日K',
          type: 'candlestick',
          data: klineValues
        },
        {
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: volumeValues
        }
      ]
    }
  }

  const chipOption = () => {
    if (!data) return {}
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['筹码集中度70%', '筹码集中度90%'] },
      xAxis: {
        type: 'category',
        data: data.chip_distribution.concentration_70.map((_, idx) => idx + 1)
      },
      yAxis: { type: 'value', min: 0, max: 1 },
      series: [
        {
          name: '筹码集中度70%',
          type: 'line',
          data: data.chip_distribution.concentration_70,
          smooth: true
        },
        {
          name: '筹码集中度90%',
          type: 'line',
          data: data.chip_distribution.concentration_90,
          smooth: true
        }
      ]
    }
  }

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

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card title={`日K图：${data?.name ?? submittedCode}`} loading={isLoading}>
            {isError ? (
              <Typography.Text type="danger">数据加载失败</Typography.Text>
            ) : (
              <ReactECharts option={klineOption()} style={{ height: 400 }} notMerge lazyUpdate />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="筹码集中度曲线" loading={isLoading}>
            {isError ? (
              <Typography.Text type="danger">数据加载失败</Typography.Text>
            ) : (
              <ReactECharts option={chipOption()} style={{ height: 400 }} />
            )}
          </Card>
        </Col>
      </Row>
    </Space>
  )
}

export default DailyKPage
