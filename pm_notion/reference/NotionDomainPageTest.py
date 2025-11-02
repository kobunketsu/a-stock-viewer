#测试Notion的页面相关
import notion_manager as no
import NotionDomainAPI as nd
import requests
import os

#own
page_databaseId = '91d3ee40215a484986516accd25683c2'
#XR
# page_databaseId = 'a29cb4fe1a95412d959aa377642497b8'
#gpt
# page_databaseId = '5d36f46cdf154a56be673ae273062fa8'
#prompt
# page_databaseId = '548e1b7002be44fdb8096f024fd871e6'

def loadDomainInfoPage(page,forceUpdate=False):
    
    domain = nd.getDomainNameFromPage(page)
    if not domain:
        print('domain empty')
        return
    print('domain {} started'.format(domain))
     
    tools = no.findSubBlocks(page, filter={
        'contains': ['Tool']
    })
    if len(tools) == 0:return

    dbs = no.findSubBlocks(tools[0], type='child_database')
    print('')

def loadDomainPages(databaseId, count):
    filter = {
        "and": [
            {
                "property": "完成购买",
                "select": {
                    "equals": '测试'
                }
            }
        ]         
    }

    pages = no.loadPages(databaseId, count, filter, loadContent=True)
    #检查域名
    for idx, page in enumerate(pages): 
        loadDomainInfoPage(page, forceUpdate=False)
        print('job {} in {} done'.format(str(idx), str(len(pages))))
    print('all jobs done')

def main():    

    loadDomainPages(page_databaseId, 0)


if __name__ == '__main__':
    main()