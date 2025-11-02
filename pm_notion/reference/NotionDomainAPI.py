import notion_manager as no
import json
import requests

#获取域名数据库id
def getDomainDatabaseId(database_title):
    database_id = no.searchDatabaseId(database_title)
    if not database_id:
        print(f"No database found with title '{database_title}'")    
        return None
    return database_id

#获取所有域名数据库id    
def getAllDomainDatabaseId():
    return

#pages中是否包含域名页
def getDomainPage(pages, domain):
    for page in pages:
        thedomain = no.getPropTitleFromPage(page, '域名')
        if not thedomain:
            continue
        if thedomain.lower() == domain.lower():
            return page
    return None

#创建域名记录
def createDomainPage (pageProp, databaseId, headers=no.headers) :
    createUrl = 'https://api.notion.com/v1/pages'
    newPageData = {    
        "parent": {
            "database_id": databaseId 
        },
        "properties": {
            "域名": {
                "title": [
                    {
                        "text": {
                            "content": pageProp['域名']
                        }
                    }
                ]     
            },                     
        }
    }
    data = json. dumps(newPageData)
    response = requests.request ("POST", createUrl, headers=headers, data=data)
    pageData = response.json()
    print(f"create domain page {pageProp['域名']} status {response.status_code}")
    return pageData

#更新域名记录
def updateDomainPage(pageId, pageData, headers=no.headers) :
    no.validatePage(pageData)

    domain = getDomainNameFromPage(pageData)
    updateUrl = f"https://api.notion.com/v1/pages/{pageId}"
    updateData = pageData
    data = json.dumps (updateData)
    response = requests. request ("PATCH", updateUrl, headers=headers, data=data)    
    print ('{} update status {} {}'.format(domain, str(response.status_code), response.reason))
    # print(response.text)

#加载指定域名的页面
def loadDomainPage(domain, databaseId=no.databaseId, count=0, filter=None, sorts=None, loadContent=False):
    filter = {
            "property": "域名",
            "rich_text": {
                "contains": domain
            }        
        }    
    pages = no.loadPages(databaseId, 0, filter, sorts, loadContent)
    if len(pages) == 0:
        print('page for {} none'.format(domain))
        return None
    return pages[0]

#加载获得域名页
def loadOwnedDomainPages(databaseId=no.databaseId, count=0, filter=None, sorts=None, loadContent=False):
    finalFilter = None    
    if not filter: finalFilter = ownFilter
    else:
        ownFilter['and'].extend(filter['and'])
        finalFilter = ownFilter

    return no.loadPages(databaseId, count, finalFilter, sorts, loadContent)

#获得域名名称
def getDomainNameFromPage(page) -> str:
    return no.getPropTitleFromPage(page,'域名')

testFilter = {
        "and": [
            {
                "property": "完成购买",
                "select": {
                    "equals": '测试'
                }
            }
        ]         
    }

ownFilter = {
        "and": [
            {
                "property": "完成购买",
                "select": {
                    "equals": '测试'
                }
            }
        ]         
    }

def filterAndFilter(filter1, filter2):
    filter1['and'].extend(filter2['and'])
#特定域名
def filterShowDomains(domains):
    filter = {'or':[]}
    for domain in domains:
        filter['or'].append({
            "property": "域名",
            "title": {
                "contains": domain
            }
        })
    return filter


