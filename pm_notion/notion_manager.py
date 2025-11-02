from email import header
import requests, json, copy
# from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import pandas as pd
import time
import sys
import _class
import _date
import _system as s
import os
from datetime import datetime

token = os.getenv("NOTION_TOKEN", "")

headers = {
      "Authorization": "Bearer " + token,
      "Content-Type" : "application/json",
      "Notion-Version": "2022-06-28"
}

databaseId = '91d3ee40215a484986516accd25683c2'

def _cmd():
    return sys._getframe().f_code.co_name

#获取database id
def requestObjectDataWithTitle(database_title, payload):
    url = "https://api.notion.com/v1/search"
    response = requests.post(url, json=payload, headers=headers)
    return response.json()

#用对象的标题搜索对象
def searchObjectWithTitle(type, title, filter=None, sorts=None):
    allPages = []

    has_more = True
    pagingIdx = 0
    data = {
        'page_size': 100
    } 

    if filter:
        data['filter'] = filter

    if sorts:
        data['sorts'] = sorts

    while has_more:
        pagingIdx = pagingIdx + 1
        print('seaching next at paging' + str(pagingIdx))  
        jsonData = requestObjectDataWithTitle(title, payload=data)
        results = jsonData['results']
        for result in results:
            if not result['object'] == type:continue
            if type == 'database':
                if result['title'][0]['text']['content'] == title:
                    return result
        data = {
            'start_cursor': jsonData['next_cursor'],
            'page_size': 100,
        }
        has_more = jsonData['has_more']
    s.printTaskDone
    
#数据库名称搜索数据库id
def searchDatabaseId(database_title, filter=None, sorts=None):
    db = searchObjectWithTitle('database', database_title, filter, sorts)    
    return db['id'] if db else None


#获取数据的结构，没有隐藏的属性
def dumpDatabaseStructure(databaseId, params, headers):    
    readUrl = f"https://api.notion.com/v1/databases/{databaseId}"
      
    res = requests.request("GET", readUrl, params=params, headers=headers) 
    data = res.json()
    # print(res.status_code)
    # print(res.text)
    numRes =  len(res['results'])
    print('loaded'+str(numRes)+'domains')

    with open('./datahead.json', 'w', encoding='utf8') as f:
        json.dump(data, f, ensure_ascii=False)
#获取数据的数值

def readDatabase(databaseId, headers, data=None):   
    readUrl = f"https://api.notion.com/v1/databases/{databaseId}/query"     
    # data = {
    #     'page_size': 100,
    # }       
    res = requests.post(readUrl, json=data, headers=headers)    
    jsondata = res.json()

    # with open('./database.json', 'w', encoding='utf8') as f:
    #     json.dump(jsondata, f, ensure_ascii=False)
    
    return jsondata
#将所有数据copy本地
def dumpAllPages(databaseId, headers):
    alldatabase = {'results':[]}
    has_more = True
    pageidx = 0
    data = {
        'page_size': 100,
    }
    while has_more:
        pageidx = pageidx + 1
        print('read next page ' + str(pageidx))  
        database = readDatabase(databaseId, headers=headers, data=data)        
        alldatabase['results'] += database['results']            
        data = {
            'start_cursor': database['next_cursor'],
            'page_size': 100,
        }
        has_more = database['has_more']

    with open('./database.json', 'w', encoding='utf8') as f:
        json.dump(alldatabase, f, ensure_ascii=False)    
    return

#加载页面内所有数据库页
@s.run_start_end_message()
def loadPages(databaseId=databaseId, count=0, filter=None, sorts=None,loadContent=False):
    if not databaseId:
        s.printError('loadPages database id not found')
        return
    allPages = []

    has_more = True
    pageidx = 0
    data = None
    if filter:
        data = {
            'page_size': 100,
            'filter' : filter,        
        }
    else:
        data = {
            'page_size': 100
        }        

    if sorts:
        data['sorts'] = sorts

    while has_more:
        pageidx = pageidx + 1
        if count > 0 and pageidx > count:  
            break
    
        print('read next pages at paging' + str(pageidx))  
        database = readDatabase(databaseId, headers=headers, data=data)        
        for page in database['results']:
            #加载页面内容
            if loadContent:
                page['content'] = readBlock(page, headers)

            allPages.append(page)
        data = {
            'start_cursor': database['next_cursor'],
            'page_size': 100,
        }
        has_more = database['has_more']
    s.printTaskDone
    return allPages

#单独加载页面数据库页
def loadPageContent(page):
    page['content'] = readBlock(page, headers)
    return page

#数据库创建页，创建的结果用于appendPage
#可使用模版
def createBlankPage(databaseId):
    data = readDatabase(databaseId)
    print('')

#数据库追加页
def appendPage (page, headers=headers) :
    createUrl = 'https://api.notion.com/v1/pages'

    data = json. dumps (page)
    # print (str(uploadData))
    time.sleep(5)
    requests.DEFULT_RETRIES = 5
    s = requests.session
    s.keep_alive = False    
    response = requests.request ("POST", createUrl, headers=headers, data=data)
    response.close()
    print(str(response.status_code) + response.text)

def updatePages(pages, headers=headers) :
    print('updateNotionPages')
    cnt = len(pages)
    idx = 0
    for page in pages:
        pageId = page['id']        
        updatePage(pageId, page)
        idx += 1
        print('updateNotionPage {} of {}'.format(idx, cnt))
        #prevent connection peer
        time.sleep(1)

def validatePage(pageData):
    if not 'properties' in pageData.keys(): 
        return pageData
    srcProps = pageData['properties']
    props = copy.deepcopy(srcProps)
    # copy_keys = list(props.keys())
    for key in props:
        if not srcProps[key]:continue
        if srcProps[key]['type'] == 'rollup': 
            srcProps.pop(key)    
        elif srcProps[key]['type'] == 'formula': 
            srcProps.pop(key)    
    pageData['properties'] = srcProps
    return pageData

#更新域名记录
def updatePage(pageId, pageData, headers=headers) :
    #移除不需要上传的属性
    pageData = validatePage(pageData)
    
    updateUrl = f"https://api.notion.com/v1/pages/{pageId}"    
    data = json.dumps (pageData)
    time.sleep(5)
    requests.DEFULT_RETRIES = 5
    s = requests.session
    s.keep_alive = False    
    response = requests. request ("PATCH", updateUrl, headers=headers, data=data)    
    response.close()

    print ('page {} update response {}'.format(pageId, str(response.status_code), response.reason))
    if response.status_code == 400:
        print('try to fix')

headers = {
      "Authorization": "Bearer " + token,
      "Content-Type" : "application/json",
      "Notion-Version": "2022-06-28"
}

#获取数据的数值
def readDatabase(databaseId, headers, data=None):   
    readUrl = f"https://api.notion.com/v1/databases/{databaseId}/query"     
    # data = {
    #     'page_size': 100,
    # }       
    res = requests.post(readUrl, json=data, headers=headers)    
    jsondata = res.json()

    # with open('./database.json', 'w', encoding='utf8') as f:
    #     json.dump(jsondata, f, ensure_ascii=False)
    
    return jsondata

#获取数据的结构，没有隐藏的属性
def dumpDatabaseStructure(databaseId, params, headers):    
    readUrl = f"https://api.notion.com/v1/databases/{databaseId}"
      
    res = requests.request("GET", readUrl, params=params, headers=headers) 
    data = res.json()
    # print(res.status_code)
    # print(res.text)
    numRes =  len(res['results'])
    print('loaded'+str(numRes)+'domains')

    with open('./datahead.json', 'w', encoding='utf8') as f:
        json.dump(data, f, ensure_ascii=False)
        
def dumpAllPages(databaseId, headers):
    alldatabase = {'results':[]}
    has_more = True
    pageidx = 0
    data = {
        'page_size': 100,
    }
    while has_more:
        pageidx = pageidx + 1
        print('read next page ' + str(pageidx))  
        database = readDatabase(databaseId, headers=headers, data=data)        
        alldatabase['results'] += database['results']            
        data = {
            'start_cursor': database['next_cursor'],
            'page_size': 100,
        }
        has_more = database['has_more']

    with open('./database.json', 'w', encoding='utf8') as f:
        json.dump(alldatabase, f, ensure_ascii=False)    
    return

#清除所有满足条件的页面
def removeAllPages(databaseId, filterCallback=None, headers=headers):
    for page in loadPages(databaseId, 0):
        if not filterCallback:
            page['archived'] = True
            updatePage(page['id'], page, headers)
            return
        if filterCallback(page):
            #满足过滤条件的删除
            page['archived'] = True
            updatePage(page['id'], page, headers)

    s.printTaskDone    

#对页面进行属性排序
def sortPages(pages, property, reverse=False):
    if len(pages) == 0:return pages
    type = pages[0]['properties'][property]['type']
    if type == 'number':
        return sorted(pages, key=lambda x: float(x['properties'].get(property, {}).get('number', 0.0)) if x['properties'].get(property, {}).get('number') is not None else 0.0, reverse=reverse)
    if type == 'checkbox':
        return sorted(pages, key=lambda x: float(x['properties'].get(property, {}).get(type, False)) if x['properties'].get(property, {}).get(type) is not None else False, reverse=reverse)        

#获取页面内容数据块
#需要循环加载
def readBlock(block, headers, recursive=True):
    if 'type' in block.keys() and block['type'] == 'child_database':            
    #没有子层级，查看数据类型        
        #加载数据库内容
        # subBlock['content'] = readDatabase(subBlock['id'], headers)
        #加载数据库内容,直接把pages数组挂在content下？
        #子数据库是否要加载内容？
        return loadPages(block['id'], loadContent=False)

    # blockid = block_id.replace('-', '')
    readUrl = f"https://api.notion.com/v1/blocks/{block['id']}/children?page_size=100"    
    res = requests.get(readUrl, headers=headers)
    #content中包含块属性        
    jsonData = res.json()
    # print('readBlock:\n {}'.format(jsonData))
        #results中有子层级
    subBlocks = jsonData['results']

    #不获取内容的子层级
    if not recursive: return subBlocks

    for subBlock in subBlocks:      
        #递归读取子block内容
        subBlock['content'] = readBlock(subBlock, headers, recursive)

    return subBlocks

#找到特定类型的block
def findSubBlocks(block, type=None, filter=None, excludeTemplate=True):
    #不支持在子数据库中查找
    if 'type' in block.keys() and block['type'] == 'child_database': return None
    if 'content' not in block.keys(): return None
    blocks = []
    for subBlock in block['content']:
        #跳过模版的的block
        if 'type' in subBlock.keys() and subBlock['type'] == 'template' and excludeTemplate:
            print('skip template') 
            continue

        if not type or ('type' in subBlock.keys() and subBlock['type'] == type):
            #加入符合类型
            if not filter:
                blocks.append(subBlock)
            else:
                blockType = subBlock['type']
                if 'contains' in filter.keys() and blockText(subBlock[blockType]) in filter['contains']:
                    blocks.append(subBlock)

        #递归搜索子block
        value = findSubBlocks(subBlock, type, filter, excludeTemplate)
        if value:
            blocks.extend(value)
    return blocks

#获得页面主Key标题
def getPropTitleFromPage(page,name) -> str:
    #提取xlsx需要的字段
    pageId = page['id']
    #域名
    titles = page['properties'][name]['title']
    if len(titles) == 0:
        return None
    domain = titles[0]['text']['content'].lower()
    return domain
       
def newPage(mainKey, title, databaseId):
    page = {
        "parent": {
            "database_id": databaseId 
        },
        'properties' : {
            mainKey : newTitle(title)
        }
    }
    return page
#创建属性
def createPropForPage(page, property, type='title'):
    #property不存在, 创建属性
    prop = {
        'type' : type
    }    
    if type == 'number':
        prop = newNumber()  
    elif type == 'select':
        prop = newSelect()
    elif type == 'checkbox':
        prop = newCheckbox()    
    elif type == 'rich_text':
        prop = newRichText()
    elif type == 'title':
        prop = newTitle()
    page['properties'][property] = prop

def hasPropForPage(page, property):
    return property in page['properties'].keys()

#设置页面属性数值，不同类型
def setPropValueForPage(page, property, value, color=None):
    if not hasPropForPage(page, property):
        print('{} property {} nil'.format(_cmd(),property))
        return
        
    prop = page['properties'][property]
    if not prop:
        print('property not found'.format(property))
        return False
    if prop['type'] == 'select':
        if not prop['select']:
            prop['select'] = {
                'name': value,
                'color': color                    
            }
            return
        prop['select']['name'] = value
    elif prop['type'] == 'date':
        prop = newDate(value)
    elif prop['type'] == 'url':
        prop['url'] = value
    elif prop['type'] == 'number':
        prop['number'] = value
    elif prop['type'] == 'title':
        prop = newTitle(value)
    elif prop['type'] == 'rich_text':
        prop = newRichText(value)
    elif prop['type'] == 'checkbox':        
        prop['checkbox'] = value    
    page['properties'][property] = prop

#用字典设置页面所有属性数值
def setPropValuesForPage(page, propertyInfos):
    for propertyInfo in propertyInfos:
        propName = propertyInfo['name']
        type = propertyInfo['type']
        value = None
        color = None
        if type == 'select':
            value = propertyInfo[type]['name']
            color = propertyInfo[type]['color']
        else:
            value = propertyInfo['value']

        if not hasPropForPage(page, propName):
            createPropForPage(page, propName, type)
        setPropValueForPage(page, propName, value, color)
    return page
        
#获取页面属性数值，不同类型
def getPropValueForPage(page,property):
    prop = page['properties'][property]
    if not prop:
        print('property not found'.format(property))
        return False
    if prop['type'] == 'select':
        if not prop['select']: return None
        return prop['select']['name']
    if prop['type'] == 'date':
        if not prop['date']: return None
        return prop['date']['start']
    if prop['type'] == 'url':
        return prop['url']
    if prop['type'] == 'number':
        return prop['number']
    if prop['type'] == 'title':
        return prop['title'][0]['plain_text']        
    if prop['type'] == 'rich_text':
        if not prop['rich_text']: return None
        return prop['rich_text'][0]['plain_text']  
    if prop['type'] == 'checkbox':
        return prop['checkbox']
    if prop['type'] == 'relation':
        return prop['relation']

#获得关联属性对应数据库中的主键
def getRelationDBPropValueForPage(page, property, databaseId, databasePageKey):
    srcPages = getPropValueForPage(page, property)
    relationPages = loadPages(databaseId)
    propValue = []
    for srcPage in srcPages:
        for relationPage in relationPages:
            if relationPage['id'] == srcPage['id']:
                propValue.append(getPropTitleFromPage(relationPage, databasePageKey))
    
    return propValue

#添加一个默认类型属性
def newSelect(name=None, color=None):
    return {
        'type' : 'select',
        'select' : {}
    }
        
def newDate(value):
    # parse the datetime string into a datetime object
    date = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d") if value else None
    return {
        'type' : 'date',
        'date' : {
            'start' : date
        }   
    }
         
def newTitle(title=None):
    return {
        'id': 'title', 
        'type': 'title', 
        'title': [
            {
                'type': 'text', 'text': {'content': title, 'link': None}, 'plain_text': title, 'href': None
            }	
        ]
    } 
def newRichText(title=None):
    return {
        'type': 'rich_text', 
        'rich_text': [
            {
                'type': 'text', 'text': {'content': title, 'link': None}, 'plain_text': title, 'href': None
            }	
        ]
    }  

def newCheckbox(check=False):
    return {
        'type': 'checkbox', 
        'checkbox': check,
    }    
def newNumber(number = None):
    return {
        'type': 'number', 
        'number': number,
    }      

#快速从block取出文字
def blockText(block):
    if 'rich_text' in block.keys():
        if not block['rich_text']:return None
        return block['rich_text'][0]['plain_text']
    return None        

if __name__ == '__main__':
    print("Notion Manager - 通用API操作工具")
