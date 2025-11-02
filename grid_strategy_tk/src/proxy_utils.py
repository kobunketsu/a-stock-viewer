import socket

import requests
import socks


def setup_proxy(host="127.0.0.1", port=1080):
    """
    设置SOCKS5代理
    @param host: 代理服务器地址
    @param port: 代理服务器端口
    @return: 是否设置成功
    """
    try:
        socks.set_default_proxy(socks.SOCKS5, host, port)
        socket.socket = socks.socksocket
        
        # 验证代理设置
        try:
            # 获取IP信息
            response = requests.get('http://ip-api.com/json/', timeout=5)
            if response.status_code == 200:
                ip_data = response.json()
                if ip_data['status'] == 'success':
                    print(f"代理设置成功:")
                    print(f"IP: {ip_data['query']}")
                    print(f"位置: {ip_data['country']} {ip_data['regionName']} {ip_data['city']}")
                    print(f"ISP: {ip_data['isp']}")
                    return True
                else:
                    print("获取IP地理位置信息失败")
            else:
                print(f"代理验证失败，HTTP状态码: {response.status_code}")
        except Exception as e:
            print(f"代理验证请求失败: {e}")
            
    except Exception as e:
        print(f"设置SOCKS5代理失败: {e}")
    
    return False

def verify_proxy():
    """
    验证当前代理是否可用
    @return: 是否可用
    """
    try:
        response = requests.get('http://ip-api.com/json/', timeout=5)
        return response.status_code == 200
    except:
        return False

def get_current_ip():
    """
    获取当前IP信息
    @return: IP信息字典，获取失败返回None
    """
    try:
        response = requests.get('http://ip-api.com/json/', timeout=5)
        if response.status_code == 200:
            ip_data = response.json()
            if ip_data['status'] == 'success':
                return {
                    'ip': ip_data['query'],
                    'country': ip_data['country'],
                    'region': ip_data['regionName'],
                    'city': ip_data['city'],
                    'isp': ip_data['isp']
                }
    except:
        pass
    return None 