import akshare as ak

def test_stock_news():
    """测试获取个股新闻数据
    
    使用stock_news_em接口获取股票新闻,并打印新闻链接
    """
    try:
        # 获取平安银行(000001)的新闻数据
        df = ak.stock_news_em(symbol="000001")
        
        # 打印所有新闻的链接
        print("\n新闻链接列表:")
        print("-" * 50)
        for index, row in df.iterrows():
            print(f"新闻标题: {row['新闻标题']}")
            print(f"新闻链接: {row['新闻链接']}")
            print(f"发布时间: {row['发布时间']}")
            print("-" * 50)
            
        # 打印数据统计
        print(f"\n共获取到 {len(df)} 条新闻")
        
    except Exception as e:
        print(f"获取新闻数据失败: {str(e)}")

if __name__ == "__main__":
    test_stock_news() 