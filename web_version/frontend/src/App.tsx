import { Layout, Menu, Typography } from 'antd'
import { useState } from 'react'
import { StockOutlined, LineChartOutlined, ThunderboltOutlined } from '@ant-design/icons'
import WatchlistPage from './pages/WatchlistPage'
import DailyKPage from './pages/DailyKPage'
import IntradayPage from './pages/IntradayPage'

const { Header, Sider, Content } = Layout

const MENU_KEYS = {
  WATCHLIST: 'watchlist',
  DAILY_K: 'dailyK',
  INTRADAY: 'intraday'
} as const

type MenuKey = typeof MENU_KEYS[keyof typeof MENU_KEYS]

function App() {
  const [collapsed, setCollapsed] = useState(false)
  const [activeKey, setActiveKey] = useState<MenuKey>(MENU_KEYS.WATCHLIST)

  const renderContent = () => {
    switch (activeKey) {
      case MENU_KEYS.DAILY_K:
        return <DailyKPage />
      case MENU_KEYS.INTRADAY:
        return <IntradayPage />
      case MENU_KEYS.WATCHLIST:
      default:
        return <WatchlistPage />
    }
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} breakpoint="lg">
        <div className="logo">Grid Strategy</div>
        <Menu
          theme="dark"
          selectedKeys={[activeKey]}
          mode="inline"
          items={[
            {
              key: MENU_KEYS.WATCHLIST,
              icon: <StockOutlined />,
              label: '自选列表'
            },
            {
              key: MENU_KEYS.DAILY_K,
              icon: <LineChartOutlined />,
              label: '日K分析'
            },
            {
              key: MENU_KEYS.INTRADAY,
              icon: <ThunderboltOutlined />,
              label: '分时监控'
            }
          ]}
          onClick={({ key }) => setActiveKey(key as MenuKey)}
        />
      </Sider>
      <Layout>
        <Header className="site-header">
          <Typography.Title level={3} style={{ color: '#fff', margin: 0 }}>
            网格策略网页端（Milestone 2 Prototype）
          </Typography.Title>
        </Header>
        <Content style={{ margin: '16px' }}>
          <div className="site-content">{renderContent()}</div>
        </Content>
      </Layout>
    </Layout>
  )
}

export default App
