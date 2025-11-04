import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message
} from 'antd'
import {
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
  LineChartOutlined,
  PlusCircleOutlined
} from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import {
  WatchlistMeta,
  WatchlistSymbol,
  useAddSymbol,
  useCreateWatchlist,
  useDeleteWatchlist,
  useRemoveSymbol,
  useWatchlistSymbols,
  useWatchlists,
  searchSymbols
} from '../api/watchlists'
import { useHotkeys } from '../hooks/useHotkeys'

interface SearchOption {
  label: string
  value: string
  data: WatchlistSymbol
}

function WatchlistPage() {
  const queryClient = useQueryClient()
  const [currentList, setCurrentList] = useState<string>('默认')
  const [isCreateModalOpen, setCreateModalOpen] = useState(false)
  const [isAddModalOpen, setAddModalOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [searchOptions, setSearchOptions] = useState<SearchOption[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState<SearchOption | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])

  const { data: watchlists } = useWatchlists()
  const { mutateAsync: createWatchlist, isLoading: creatingList } = useCreateWatchlist()
  const { mutateAsync: deleteWatchlist, isLoading: deletingList } = useDeleteWatchlist()
  const { mutateAsync: addSymbol, isLoading: addingSymbol } = useAddSymbol()
  const { mutateAsync: removeSymbol, isLoading: removingSymbol } = useRemoveSymbol()

  const currentMeta: WatchlistMeta | undefined = useMemo(() => {
    return watchlists?.find((item) => item.name === currentList)
  }, [watchlists, currentList])

  useEffect(() => {
    if (!watchlists || watchlists.length === 0) return
    const exists = watchlists.find((item) => item.name === currentList)
    if (!exists) {
      const fallback = watchlists.find((item) => item.name === '默认') ?? watchlists[0]
      setCurrentList(fallback.name)
    }
  }, [watchlists, currentList])

  useEffect(() => {
    setSelectedRowKeys([])
  }, [currentMeta?.name])

  const symbolsQuery = useWatchlistSymbols(currentMeta?.name, true)
  const tableData = symbolsQuery.data ?? []

  const isSystemList = currentMeta?.type === 'system'

  const handleRefresh = () => {
    if (currentMeta) {
      queryClient.invalidateQueries({ queryKey: ['watchlists', currentMeta.name, 'symbols'] })
      symbolsQuery.refetch()
    }
  }

  const handleCreateList = async (values: { name: string; description?: string }) => {
    try {
      await createWatchlist(values)
      message.success('新建列表成功')
      setCreateModalOpen(false)
      setCurrentList(values.name)
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '新建列表失败')
    }
  }

  const handleDeleteList = async () => {
    if (!currentMeta || isSystemList) return
    try {
      await deleteWatchlist(currentMeta.name)
      message.success('已删除列表')
      setSelectedRowKeys([])
      // 刷新后让当前列表落到第一项
      const next = watchlists?.find((item) => item.name !== currentMeta.name)
      setCurrentList(next?.name ?? '默认')
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '删除失败')
    }
  }

  const handleAddSymbol = async () => {
    if (!currentMeta) return
    try {
      let target = selectedSymbol

      if (!target) {
        const keyword = searchTerm.trim()
        if (!keyword) {
          message.warning('请输入股票代码或名称')
          return
        }
        const results = await searchSymbols(keyword)
        if (!results.length) {
          message.warning('未找到匹配的股票')
          return
        }
        const chosen = results[0]
        target = {
          label: `${chosen.code} ${chosen.name}`,
          value: chosen.code,
          data: chosen
        }
      }

      await addSymbol({ list: currentMeta.name, code: target.value, name: target.data.name })
      message.success('已加入列表')
      setAddModalOpen(false)
      setSearchTerm('')
      setSelectedSymbol(null)
      setSearchOptions([])
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '添加失败')
    }
  }

  const handleDeleteSelected = async () => {
    if (!currentMeta || selectedRowKeys.length === 0) return
    try {
      await Promise.all(selectedRowKeys.map((key) => removeSymbol({ list: currentMeta.name, code: key })))
      message.success('已删除选中股票')
      setSelectedRowKeys([])
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '删除失败')
    }
  }

  useEffect(() => {
    if (!isAddModalOpen) {
      setSearchTerm('')
      setSearchOptions([])
      setSelectedSymbol(null)
      setSearchLoading(false)
      return
    }
    const keyword = searchTerm.trim()
    if (keyword.length < 2) {
      setSearchOptions([])
      setSearchLoading(false)
      return
    }
    const handler = window.setTimeout(async () => {
      try {
        setSearchLoading(true)
        const results = await searchSymbols(keyword)
        const mapped = results.map((item) => ({
          label: `${item.code} ${item.name}`,
          value: item.code,
          data: item
        }))
        setSearchOptions(mapped)
        if (mapped.length === 1) {
          setSelectedSymbol(mapped[0])
        } else if (selectedSymbol && !mapped.find((item) => item.value === selectedSymbol.value)) {
          setSelectedSymbol(null)
        }
      } catch (err: any) {
        console.error(err)
        message.error('搜索失败，请稍后重试')
      } finally {
        setSearchLoading(false)
      }
    }, 250)
    return () => window.clearTimeout(handler)
  }, [isAddModalOpen, searchTerm])

  const stats = useMemo(() => {
    if (!tableData || tableData.length === 0) {
      return { total: 0, up: 0, down: 0 }
    }
    let up = 0
    let down = 0
    tableData.forEach((item) => {
      const value = item.quote?.change_percent ?? 0
      if (value > 0) up += 1
      if (value < 0) down += 1
    })
    return { total: tableData.length, up, down }
  }, [tableData])

  const columns = useMemo(() => {
    return [
      {
        title: '代码',
        dataIndex: 'code',
        key: 'code',
        width: 100,
        render: (code: string) => <Typography.Text code>{code}</Typography.Text>
      },
      {
        title: '名称',
        dataIndex: 'name',
        key: 'name',
        width: 160
      },
      {
        title: '最新价',
        dataIndex: ['quote', 'last_price'],
        key: 'last_price',
        render: (_: unknown, record: WatchlistSymbol) => formatNumber(record.quote?.last_price)
      },
      {
        title: '涨跌幅',
        dataIndex: ['quote', 'change_percent'],
        key: 'change_percent',
        render: (_: unknown, record: WatchlistSymbol) => renderChange(record.quote?.change_percent)
      },
      {
        title: '消息',
        dataIndex: ['quote', 'message'],
        key: 'message',
        width: 220,
        render: (_: unknown, record: WatchlistSymbol) => record.quote?.message ?? '-'
      },
      {
        title: '信号',
        dataIndex: ['quote', 'signal_level'],
        key: 'signal_level',
        width: 100,
        render: (_: unknown, record: WatchlistSymbol) =>
          record.quote?.signal_level ? <Tag color="blue">{record.quote.signal_level}</Tag> : '-'
      }
    ]
  }, [tableData])

  useHotkeys([
    {
      combo: 'meta+r',
      handler: handleRefresh,
      description: '刷新自选列表'
    },
    {
      combo: 'meta+i',
      handler: () => message.info('信息列刷新功能开发中'),
      description: '刷新信息列'
    },
    {
      combo: 'meta+t',
      handler: () => message.info('趋势列刷新功能开发中'),
      description: '刷新趋势列'
    }
  ])

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} md={6}>
            <Typography.Text strong>列表</Typography.Text>
            <Select
              value={currentList}
              onChange={(value) => {
                setCurrentList(value)
                setSelectedRowKeys([])
              }}
              style={{ width: '100%', marginTop: 4 }}
              options={(watchlists ?? []).map((item) => ({
                label: `${item.name}${item.type === 'system' ? '（系统）' : ''}`,
                value: item.name
              }))}
            />
          </Col>
          <Col xs={24} md={18}>
            <Space wrap>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
                新建列表
              </Button>
              <Popconfirm
                title="确认删除"
                description="删除后不可恢复，确定删除该列表吗？"
                onConfirm={handleDeleteList}
                okButtonProps={{ loading: deletingList }}
                disabled={isSystemList}
              >
                <Button icon={<DeleteOutlined />} disabled={isSystemList} danger>
                  删除列表
                </Button>
              </Popconfirm>
              <Button
                icon={<PlusCircleOutlined />}
                onClick={() => setAddModalOpen(true)}
                disabled={isSystemList}
              >
                添加股票
              </Button>
              <Button
                icon={<DeleteOutlined />}
                onClick={handleDeleteSelected}
                disabled={isSystemList || selectedRowKeys.length === 0}
                loading={removingSymbol}
              >
                删除选中
              </Button>
              <Button icon={<ReloadOutlined />} loading={symbolsQuery.isLoading} onClick={handleRefresh}>
                刷新行情
              </Button>
              <Tooltip title="信息列刷新功能开发中">
                <Button icon={<InfoCircleOutlined />} disabled>
                  信息列(⌘I)
                </Button>
              </Tooltip>
              <Tooltip title="趋势列刷新功能开发中">
                <Button icon={<LineChartOutlined />} disabled>
                  趋势列(⌘T)
                </Button>
              </Tooltip>
            </Space>
          </Col>
        </Row>
      </Card>

      <Card
        title={`${currentList}（共 ${stats.total} 项，上涨 ${stats.up}，下跌 ${stats.down}）`}
        extra={
          <Typography.Text type={symbolsQuery.isError ? 'danger' : 'secondary'}>
            {symbolsQuery.isError ? '加载失败，请稍后重试' : '实时数据通过多源自动刷新'}
          </Typography.Text>
        }
      >
        <Table
          rowKey={(record) => record.code}
          loading={symbolsQuery.isLoading}
          columns={columns}
          dataSource={tableData}
          pagination={false}
          rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys.map((key) => String(key))) }}
          scroll={{ x: true }}
        />
      </Card>

      <Modal
        title="新建列表"
        open={isCreateModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={() => undefined}
        footer={null}
        destroyOnClose
      >
        <Form layout="vertical" onFinish={handleCreateList}>
          <Form.Item label="列表名称" name="name" rules={[{ required: true, message: '请输入列表名称' }]}> 
            <Input placeholder="例如：科技股" />
          </Form.Item>
          <Form.Item label="备注" name="description">
            <Input.TextArea rows={3} placeholder="可选" />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button onClick={() => setCreateModalOpen(false)}>取消</Button>
              <Button type="primary" htmlType="submit" loading={creatingList}>
                创建
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`添加股票到「${currentMeta?.name ?? ''}」`}
        open={isAddModalOpen}
        onCancel={() => setAddModalOpen(false)}
        onOk={handleAddSymbol}
        confirmLoading={addingSymbol}
        okButtonProps={{ disabled: isSystemList }}
        destroyOnClose
      >
        <Typography.Paragraph type="secondary">输入代码或名称，支持模糊搜索。</Typography.Paragraph>
        <Select
          showSearch
          placeholder="股票代码 / 名称"
          value={selectedSymbol?.value}
          onSearch={setSearchTerm}
          onChange={(value) => {
            const option = searchOptions.find((item) => item.value === value) || null
            setSelectedSymbol(option)
            if (option) {
              setSearchTerm(option.value)
            }
          }}
          filterOption={false}
          options={searchOptions}
          style={{ width: '100%' }}
          loading={searchLoading}
          allowClear
          onClear={() => setSelectedSymbol(null)}
          notFoundContent={searchTerm.trim().length < 2 ? '至少输入两个字符' : '未找到匹配股票'}
        />
        <Divider />
        {selectedSymbol && (
          <Typography.Paragraph>
            已选择：
            <Typography.Text strong>{selectedSymbol.label}</Typography.Text>
          </Typography.Paragraph>
        )}
      </Modal>
    </Space>
  )
}

function formatNumber(value?: number | null) {
  if (value === null || value === undefined) return '-'
  return value.toFixed(2)
}

function renderChange(value?: number | null) {
  if (value === null || value === undefined) return '-'
  const color = value > 0 ? 'danger' : value < 0 ? 'success' : undefined
  return (
    <Typography.Text type={color}>
      {value > 0 ? '+' : ''}
      {value.toFixed(2)}%
    </Typography.Text>
  )
}

export default WatchlistPage
