import pytest
from unittest.mock import Mock
from company_search.stock_research import query_kimi

def test_query_kimi_success(mocker):
    # 模拟成功响应
    mock_client = mocker.patch('company_search.stock_research.client')
    mock_completion = Mock()
    mock_completion.choices[0].message.content = "测试响应内容"
    mock_client.chat.completions.create.return_value = mock_completion

    result = query_kimi("测试提示词")
    assert result == "测试响应内容"
    mock_client.chat.completions.create.assert_called_once()

def test_query_kimi_retry(mocker):
    # 模拟失败重试
    mock_client = mocker.patch('company_search.stock_research.client')
    mock_client.chat.completions.create.side_effect = Exception("模拟错误")
    
    with pytest.raises(Exception):
        query_kimi("测试提示词")
    
    assert mock_client.chat.completions.create.call_count == 3 