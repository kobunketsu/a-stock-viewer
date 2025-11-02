#下载所有page的首页图到本地目录，并进行适当的处理
import notion_manager as no
import NotionDomainAPI as nd
import NamebrightInfoDownload as namebright
import NotionDomainPageKeywordRelationAutoBind as ndpw
import BrandpaInfoDownload as brandpa
import requests
import os
import _array
import _system as s
#更新域名页是否被注册
def updateDomainInfoPage(page,forceUpdate=False):
    
    domain = nd.getDomainNameFromPage(page)
    if not domain:
        print('domain empty')
        return
    print('domain {} started'.format(domain))
    #拥有的不需要查询
    if no.getPropValueForPage(page, '完成购买') == '已拥有': return
    #被注册认定已经设定过注册时间
    if no.getPropValueForPage(page, '完成购买') == '被注册' and (not forceUpdate): return

    #打开nameBright查询注册情况
    domainInfo = namebright.checkDomain(domain)
    if not domainInfo: return
    uploadDomainInfoPage(domainInfo, page)

#上传域名是否被注册信息到page，如果page空，则创建page
def uploadDomainInfoPage(domainInfo, page=None,forceUpdate=False):
    if not page:
        return
    #更新关注 → 注册
    if domainInfo['available'] == False:
        no.setPropValueForPage(page, '完成购买', '被注册', color='red')
        #注册日期
        if 'creationDate' in domainInfo.keys() and domainInfo['creationDate']:
            no.setPropValueForPage(page,'注册时间', domainInfo['creationDate'])
    else:
        no.setPropValueForPage(page, '完成购买', '关注中', color='blue')

    #上传notion    
    no.updatePage(page['id'], page)

def uploadDomainInfos(databaseId, count, forceUpdate=False):
    if not databaseId: return
    pages = no.loadPages(databaseId=databaseId, count=count)
    #检查域名
    for idx, page in enumerate(pages): 
        updateDomainInfoPage(page, forceUpdate)
        print('job {} in {} done'.format(str(idx), str(len(pages))))
    print('all jobs done')

@s.run_start_end_message()
def exploreDomainLinks(keyName, sharelink, check_register=True, check_price=False, numThread=1):
    databaseId = sharelink.split("/")[-1].split("?")[0]
    exploreDomains(keyName,databaseId, check_register, check_price, numThread)


#探索主要名字可能的域名
@s.run_start_end_message()
def exploreDomains(keyName, databaseId=None, check_register=True, check_price=False, numThread=1):
    #从域名前缀，后缀，缀词网页流量中获取所有高质量的缀词
    trafficPages = no.loadPages('c98bbddcd8124b7895f1d85433235479')#no.searchDatabaseId('域名缀词网页指标'))
    prefixPages = no.loadPages('76dd6d7c9719434da8e94fefa5abc122')#no.searchDatabaseId('域名前缀(双词)交易价格 '))
    suffixPages = no.loadPages('1ba46c25f96c4eeb9e0ec614b36d505d')#no.searchDatabaseId('域名后缀(双词)交易价格'))
    # trafficPages = no.loadPages(no.searchDatabaseId('域名缀词网页指标'))
    # prefixPages = no.loadPages(no.searchDatabaseId('域名前缀(双词)交易价格 '))
    # suffixPages = no.loadPages(no.searchDatabaseId('域名后缀(双词)交易价格'))    
    #h
    tn = _array.removeNone([no.getPropTitleFromPage(page, '关键词') for page in trafficPages])
    prefixes = _array.removeNone([no.getPropTitleFromPage(page, '关键词') for page in prefixPages])
    prefixes.extend(tn)
    prefixes = list(set(prefixes))
    suffixes = _array.removeNone([no.getPropTitleFromPage(page, '关键词') for page in suffixPages])
    suffixes.extend(tn)
    suffixes = list(set(suffixes))

    # databaseId = no.searchDatabaseId(databaseName)
    pages = no.loadPages(databaseId)
    #提前一次性加载网页流量信息
    trafficPages = ndpw.loadTrafficPages()

    domains = [keyName+suffix+'.com' for suffix in suffixes]
    domains.extend([prefix+keyName+'.com' for prefix in prefixes])    
    #将缀词和主词组成域名
    if check_register:
        def checkCallback(domainInfo):
            if not domainInfo: return
            domain = domainInfo['domain']
            #尝试获取页，没有的情况下创建页
            page = nd.getDomainPage(pages, domain)
            if not page:
                pageInfo = {
                    '域名' : domain
                }
                page = nd.createDomainPage(pageInfo, databaseId)
            #更新页信息
            uploadDomainInfoPage(domainInfo, page)
            #绑定流量
            ndpw.autoBindDatabaseTrafficProps(keyName, pages=[page], trafficPages=trafficPages)        
        #nameBright查询域名注册情况，标记是否被注册   
        namebright.checkDomains_multi(domains, numThread=numThread, iterCallback=checkCallback)

    #brandpa估值
    #todo:remove already priced
    if check_price:
        domain_availables = []
        for domain in domains:
            page = nd.getDomainPage(pages, domain)
            if not page:continue
            #跳过有价格
            brandpa_price = no.getPropValueForPage(page, '💰🔮brandpa估价')
            if brandpa_price and not brandpa_price == '':continue
            if no.getPropValueForPage(page, '完成购买') == '关注中':
                domain_availables.append(domain)

        def priceCallback(domainInfo):
            if not domainInfo: return
            domain = domainInfo['domain']
            #尝试获取页，没有的情况下创建页
            page = nd.getDomainPage(pages, domain)
            if not page:
                pageInfo = {
                    '域名' : domain
                }
                page = nd.createDomainPage(pageInfo, databaseId)
            #更新页信息
            uploadDomainPricePage(domainInfo, page)            
        brandpa.checkDomains_multi(domain_availables, numThread=numThread, iterCallback=priceCallback)

def uploadDomainPricePage(domainInfo, page=None,forceUpdate=False):
    if not page:
        return
    #更新关注 → 注册
    price = domainInfo['price']
    if not price or price == '':
        s.printError(f"{domainInfo['domain']} price empty")
        return
    no.setPropValueForPage(page, '💰🔮brandpa估价', int(price))

    #上传notion    
    no.updatePage(page['id'], page)

def main():    
    namebright.initDriver()
    
    uploadDomainInfos(nd.getDomainDatabaseId('Text域名'), 0)


if __name__ == '__main__':
    # main()
    exploreDomains('mem', databaseId='2efbd92cefbf47d39e7aa330b12d09c7', check_register=False, check_price=True)