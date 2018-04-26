# -*- coding: utf-8 -*-
# author: Yabin Zheng
# Email: sczhengyabin@hotmail.com

from __future__ import print_function
from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals
from __future__ import generators
from __future__ import with_statement

import re
from bs4 import BeautifulSoup
from concurrent import futures
import os
import sys
import time
import pandas as pd
import requests
import json
import shutil
from fake_useragent import UserAgent

############ 全局变量初始化 ##############
HEADERS = dict()
# 并发线程数
NUM_THREADS = 5
# 城市选择
city_dict = {
    "成都": "cd",
    "北京": "bj",
    "上海": "sh",
    "广州": "gz",
    "深圳": "sz",
    "南京": "nj",
    "合肥": "hf",
    "杭州": "hz", 
    "佛山": "fs",
}

# 是否打印HTTP错误
PRINT = False
# 伪造User-Agent库初始化
ua = UserAgent()

# 代理设置
PROXY_HOST = "proxy.abuyun.com"
PROXY_PORT = "9020"
PROXY_USERNAME = 'HR636P1V930DQ6UD'
PROXY_PASSWORD = 'AE1985062FC5B784'

# 百度地图API AK
BAIDU_AK = ""

def gen_proxies_from_cert(proxy_user, proxy_password):
    proxy_meta = "http://%(user)s:%(pass)s@%(host)s:%(port)s" % {
        "host" : PROXY_HOST,
        "port" : PROXY_PORT,
        "user" : proxy_user,
        "pass" : proxy_password
    }

    proxies = {
        "http"  : proxy_meta,
        "https" : proxy_meta
    }

    return proxies

abuyun_proxies = gen_proxies_from_cert(PROXY_USERNAME, PROXY_PASSWORD)

# 使用代理
# proxies = abuyun_proxies
# 不使用代理
proxies = None


""" HTTP GET 操作封装 """
def get_bs_obj_from_url(http_url):
    done = False
    exception_time = 0
    HEADERS["User-Agent"] = ua.random
    while not done:
        try:
            if PRINT:
                print("正在获取 {}".format(http_url))
            r = requests.get(http_url, headers=HEADERS, proxies=proxies)
            bs_obj = BeautifulSoup(r.text, "html.parser")
            done = True
        except Exception as e:
            if PRINT:
                print(e)
            exception_time += 1
            time.sleep(1)
            if exception_time > 10:
                return None
    return bs_obj

""" 判断一个字符串是否可以转成数字 """
def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


""" 获取城市的行政区域列表 """
def get_district_from_city(city):
    print("********** 获取城市的行政区域: {} **********".format(city))
    city_url = "http://{}.lianjia.com".format(city)
    http_url = city_url + "/xiaoqu"
    bs_obj = get_bs_obj_from_url(http_url)
    
    parent_div = bs_obj.find("div", {"data-role": "ershoufang"})
    a_list = parent_div.find_all("a")
    
    district_list = [a.attrs["href"].replace("/xiaoqu/", "")[:-1] 
                         for a in a_list
                         if a.attrs['href'].startswith("/xiaoqu")]
    
    print("########## 总共 {} 个行政区域 ##########".format(len(district_list)))
    
    return district_list


""" 获取一个行政区域的所有小区ID列表 """
def get_xiaoqu_from_district(city, district):
    xiaoqu_list = []
    http_url = "http://{}.lianjia.com/xiaoqu/{}".format(city, district)
    exception_time = 0
    done = False
    while not done:
        try:
            bs_obj = get_bs_obj_from_url(http_url)
            total_pages = int(json.loads(bs_obj.find("div", {"class": "page-box house-lst-page-box"}).attrs["page-data"])["totalPage"])
            total_xiaoqu_num = int(bs_obj.find("h2", {"class": "total fl"}).find("span").get_text())
            done = True
        except Exception as e:
            exception_time += 1
            if exception_time > 10:
                return xiaoqu_list

    with futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        future_list = []
        for page_no in range(1, total_pages + 1):
            future_list.append(executor.submit(get_xiaoqu_in_page, city, district, page_no))
        fail_list = []
        count = 0
        for future in futures.as_completed(future_list):
            page_no, xiaoqu_list_partial = future.result()
            if xiaoqu_list_partial is None or len(xiaoqu_list_partial) == 0:
                fail_list.append(page_no)
            else:
                xiaoqu_list += xiaoqu_list_partial
                count += 1
                sys.stdout.write("\r当前行政区域 {} 已完成: {}/{}".format(
                    district, count, total_pages))
        for page_no in fail_list:
            _, xiaoqu_list_partial = get_xiaoqu_in_page(city, district, page_no)
            if xiaoqu_list_partial is not None and len(xiaoqu_list_partial) > 0:
                xiaoqu_list += xiaoqu_list_partial
            count += 1
            sys.stdout.write("\r当前行政区域 {} 已完成: {}/{}".format(
                district, count, total_pages))
    print("")
    return xiaoqu_list


""" 获取一个行政区域某一页的小区列表 """
def get_xiaoqu_in_page(city, district, page_no):
    http_url = "http://{}.lianjia.com/xiaoqu/{}/pg{}".format(city, district, page_no)
    bs_obj = get_bs_obj_from_url(http_url)
    
    if bs_obj is None:
        return None
    
    parent_list = bs_obj.find_all("li", {"class": "clear xiaoquListItem"})
    
    xiaoqu_list = []
    
    if not (len(parent_list) == 0):
        for li in parent_list:
            xiaoqu_url = str(li.find("div", {"class": "title"}).find("a").attrs["href"])
            xiaoqu_id = "".join(list(filter(str.isdigit, xiaoqu_url)))
            xiaoqu_list.append(xiaoqu_id)
    return page_no, xiaoqu_list


""" 获取一个城市的所有小区ID列表 """
def get_xiaoqu_of_city(city):
    district_list = get_district_from_city(city)
    xiaoqu_list = []
    for district in district_list:
        xiaoqu_of_district = get_xiaoqu_from_district(city, district)
        xiaoqu_list += xiaoqu_of_district
        print("****** 当前行政区域 {} 的小区数: {}, 总小区数: {} ******".format(
            district, len(xiaoqu_of_district), len(xiaoqu_list)))
    return xiaoqu_list


""" 根据小区ID获取小区详细信息 """
def get_xiaoqu_info(city, xiaoqu_id):
    http_url = "http://{}.lianjia.com/xiaoqu/{}".format(city, xiaoqu_id)
    bs_obj = get_bs_obj_from_url(http_url)
    
    df = pd.DataFrame()
    
    if bs_obj is not None:
        try:
            location_list = bs_obj.find("div", {"class": "fl l-txt"}).find_all("a")
            info_city = location_list[1].get_text().replace("小区", "")
            info_district = location_list[2].get_text().replace("小区", "")
            info_area = location_list[3].get_text().replace("小区", "")
            info_name = location_list[4].get_text()

            if bs_obj.find("span", {"class": "xiaoquUnitPrice"}) is not None:
                info_price = bs_obj.find("span", {"class": "xiaoquUnitPrice"}).get_text()
            else:
                info_price = "暂无报价"

            info_address = bs_obj.find("div", {"class": "detailDesc"}).get_text()

            info_list = bs_obj.find_all("span", {"class": "xiaoquInfoContent"})
            info_year = info_list[0].get_text().replace("年建成", "")
            info_type = info_list[1].get_text()
            info_property_fee = info_list[2].get_text()
            info_property_company = info_list[3].get_text()
            info_developer_company = info_list[4].get_text()
            info_building_num = info_list[5].get_text().replace("栋", "")
            info_house_num = info_list[6].get_text().replace("户", "")

            df = pd.DataFrame(data=[[xiaoqu_id, http_url, info_name, info_city,
                                     info_district, info_area, info_price, info_year,
                                     info_building_num, info_house_num, info_developer_company, info_property_fee,
                                     info_property_company, info_type, info_address]],
                              columns=["ID", "URL", "小区名称", "城市",
                                       "区域", "片区", "参考均价", "建筑年代",
                                       "总栋数", "总户数", "开发商","物业费",
                                       "物业公司", "建筑类型", "地址"])
        except Exception as e:
            print("[E]: get_xiaoqu_info, xiaoqu_id =", xiaoqu_id, e)

    return xiaoqu_id, df


""" 根据城市和小区ID列表，获取所有小区的详细信息 """
def get_xiaoqu_info_from_xiaoqu_list(city, xiaoqu_list):
    df_xiaoqu_info = pd.DataFrame()
    count = 0
    pct = 0
    
    with futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        future_list = []
        for xiaoqu in xiaoqu_list:
            future_list.append(executor.submit(get_xiaoqu_info, city, xiaoqu))
        fail_list = []
        print(" ")
        for future in futures.as_completed(future_list):
            xiaoqu, df_info_partial = future.result()
            if len(df_info_partial) == 0:
                fail_list.append(xiaoqu)
            else:
                df_xiaoqu_info = df_xiaoqu_info.append(df_info_partial)
                count += 1
                sys.stdout.write("\r获取小区信息: {}/{}".format(count, len(xiaoqu_list)))
        for xiaoqu in fail_list:
            _, df_info_partial = get_xiaoqu_info(city, xiaoqu)
            if len(df_info_partial) > 0:
                df_xiaoqu_info = df_xiaoqu_info.append(df_info_partial)
                count += 1
        sys.stdout.write("\r获取小区信息: {}/{}".format(count, len(xiaoqu_list)))

    return df_xiaoqu_info

""" 获取小区成交记录的某一页的内容 """
def get_xiaoqu_transactions_in_page(city, xiaoqu_id, page_no):
    http_url = "http://{}.lianjia.com/chengjiao/pg{}c{}/".format(city, page_no, xiaoqu_id)
    
    df = pd.DataFrame(columns=["小区ID", "小区名称", "行政区域", "片区", "户型", 
                               "建筑面积", "成交价", "挂牌价", "单价",
                               "成交周期", "成交日期", "成交渠道", "朝向", "装修",
                               "电梯", "楼层", "总楼层", "建筑年份", "建筑类型",
                               "是否满二满五"])

    done = False
    try_time = 0
    while not done:
        try:
            district = str(df_xiaoqu_info.loc[xiaoqu_id, '区域']) if xiaoqu_id in df_xiaoqu_info.index else ""
            district = district.values[0] if type(district) == pd.core.series.Series else district
            region = str(df_xiaoqu_info.loc[xiaoqu_id, '片区']) if xiaoqu_id in df_xiaoqu_info.index else ""
            region = region.values[0] if type(region) == pd.core.series.Series else region
            bs_obj = get_bs_obj_from_url(http_url)
            div_list = bs_obj.find_all("div", {"class": "info"})

            for div in div_list:
                div_title = div.find("div", {"class": "title"}).find("a")
                url = div_title.attrs["href"]
                # 成交记录ID
                trans_id = url[url.rfind('/')+1:url.rfind('.')]
                title_strs = div_title.get_text().split(" ")
                # 小区名称
                xiaoqu_name = title_strs[0]
                # 户型
                house_type = title_strs[1]
                # 建筑面积
                built_area = title_strs[2].replace("平米", "")
                built_area = float(built_area) if is_number(built_area) else built_area

                house_info_strs = div.find("div", {"class": "houseInfo"}).get_text().replace(" ", "").split("|")
                # 朝向
                direction = house_info_strs[0].strip()
                # 装修
                decoration = house_info_strs[1].replace("&nbsp;", "").strip()
                # 电梯
                elevator = house_info_strs[2].strip().replace("电梯", "") if len(house_info_strs) == 3 else ""

                # 成交日期
                deal_date = div.find("div", {"class": "dealDate"}).get_text()
                # 成交价
                deal_price = (None if "暂无价格" in div.text 
                                  else float(div.find("div", {"class": "totalPrice"}).find("span", {"class": "number"}).get_text()))
                # 成交渠道
                deal_firm = "链家" if "链家成交" in div.text else "其它"

                position_info_strs = div.find("div", {"class": "positionInfo"}).get_text().split(" ")
                # 楼层
                floor = position_info_strs[0].split("(共")[0]
                # 总楼层
                total_floors = int(position_info_strs[0][position_info_strs[0].find("共")+1:position_info_strs[0].rfind("层")])
                # 建筑年份
                build_year = int(position_info_strs[1].split("年建")[0]) if "年建" in position_info_strs[1] else ""
                # 建筑类型
                build_type = position_info_strs[1].split("年建")[1] if "年建" in position_info_strs[1] else position_info_strs[1]
                # 单价
                unit_price = (None if "暂无单价" in div.text
                                  else int(div.find("div", {"class": "unitPrice"}).find("span", {"class": "number"}).get_text()))

                # 是否满二满五
                cert_term_type = ""
                if "房屋满" in div.text:
                    cert_term_type = div.text.split("房屋满")[1][:1]

                # 挂牌价与成交周期
                list_price = None
                if "挂牌" in div.text:
                    list_price = float(div.text.split("挂牌")[1].split("万")[0])
                deal_cycle = None
                if "成交周期" in div.text:
                    deal_cycle = int(div.text.split("成交周期")[1].split("天")[0])

                temp_df = pd.Series(data=[xiaoqu_id, xiaoqu_name, district, region, house_type, 
                                          built_area, deal_price, list_price, unit_price, 
                                          deal_cycle, deal_date, deal_firm, direction, decoration, 
                                          elevator, floor, total_floors, build_year, build_type,
                                          cert_term_type],
                                    index=["小区ID", "小区名称", "行政区域", "片区", "户型", 
                                           "建筑面积", "成交价", "挂牌价", "单价",
                                           "成交周期", "成交日期", "成交渠道", "朝向", "装修",
                                           "电梯", "楼层", "总楼层", "建筑年份", "建筑类型",
                                           "是否满二满五"],
                                   name=trans_id)
                df = df.append(temp_df)
                done = True
        except Exception as e:
            try_time += 1
            if try_time == 5:
                print("[E]: get_xiaoqu_transactions_in_page ", xiaoqu_id, page_no, e)
                break
    return df


""" 获取小区所有的成交记录 """
def get_xiaoqu_transactions(city, xiaoqu_id):    
    df_xiaoqu_transctions = pd.DataFrame()
    
    for i in range(5):
        try:
            http_url = "http://{}.lianjia.com/chengjiao/c{}/".format(city, xiaoqu_id)
            bs_obj = get_bs_obj_from_url(http_url)
            if not bs_obj.find("a", {"href": "/chengjiao/c{}/".format(xiaoqu_id)}):
                print("[W]: xiaoqu_id = {}, 没有这个小区的成交记录".format(xiaoqu_id))
                return
            total_transaction_num = int(bs_obj.find("div", {"class": "total fl"}).find("span").get_text())
            if total_transaction_num == 0:
                return df_xiaoqu_transctions
            total_pages = int(json.loads(bs_obj.find("div", {"class": "page-box house-lst-page-box"}).attrs["page-data"])["totalPage"])
            
            break
        except Exception as e:
            if i == 4:
                print("[E]: get_xiaoqu_transactions ", xiaoqu_id, e)
                return df_xiaoqu_transctions
        
    fail_list = []
    for page_no in range(1, total_pages+1):
        xiaoqu_transactions_partial = get_xiaoqu_transactions_in_page(city, xiaoqu_id, page_no)
        if xiaoqu_transactions_partial is None or len(xiaoqu_transactions_partial) == 0:
            fail_list.append(page_no)
        else:
            df_xiaoqu_transctions = df_xiaoqu_transctions.append(xiaoqu_transactions_partial) 
    for page_no in fail_list:
        xiaoqu_transactions_partial = get_xiaoqu_transactions_in_page(city, xiaoqu_id, page_no)
        if xiaoqu_transactions_partial is not None and len(xiaoqu_transactions_partial) > 0:
            df_xiaoqu_transctions = df_xiaoqu_transctions.append(xiaoqu_transactions_partial)        
    return df_xiaoqu_transctions


""" 根据小区ID列表，获取所有小区的所有成交记录 """
def get_transactions_from_xiaoqu_list(city, xiaoqu_list):
    df = pd.DataFrame()
    print(" ")

    with futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        future_list = []
        for xiaoqu in xiaoqu_list:
            future_list.append(executor.submit(get_xiaoqu_transactions, city, xiaoqu))
        fail_list = []
        count = 0
        for future in futures.as_completed(future_list):
            if future.exception() is not None:
                print(future.exception())
            else:
                xiaoqu_transactions_partial = future.result()
                df = df.append(xiaoqu_transactions_partial)    
            count += 1
            sys.stdout.write("\rProgress: {}/{}".format(count, len(xiaoqu_list)))
    return df


def get_transactions_detail_from_id(city, trans_id):
    district = df_transactions.loc[trans_id, "行政区域"]
    district = district.values[0] if type(district) == pd.core.series.Series else district
    region = df_transactions.loc[trans_id, "片区"]
    region = region.values[0] if type(region) == pd.core.series.Series else region
    xiaoqu_id = df_transactions.loc[trans_id, "小区ID"]
    xiaoqu_name = df_transactions.loc[trans_id, "小区名称"]

    trans_id = str(trans_id)
    http_url = "http://{}.lianjia.com/chengjiao/{}.html".format(city, trans_id)
    done = False
    try_times = 0

    while not done:
        try:
            ss = pd.Series(name=trans_id)
            bs_obj = get_bs_obj_from_url(http_url)

            ss.set_value("行政区域", district)
            ss.set_value("片区", region)
            ss.set_value("小区ID", xiaoqu_id)
            ss.set_value("小区名称", xiaoqu_name)

            # 价格
            div_price = bs_obj.find("div", {"class": "price"})
            ## 总价
            deal_price = float(div_price.find("i").text) if div_price.find("i") else None
            ss.set_value("总价", deal_price)
            ## 单价
            unit_price = float(div_price.find("b").text) if div_price.find("b") else None
            ss.set_value("单价", unit_price)

            # 成交渠道
            deal_firm = "链家" if "链家成交" in str(bs_obj.find("div", {"class": "house-title"})) else "其他"
            ss.set_value("成交渠道", deal_firm)

            # 户型图
            house_picture_url = bs_obj.find("div", {"class": "bigImg"}).find("li", {"data-desc": "户型图"}).attrs['data-src'] \
                                    if "户型图" in str(bs_obj) else None
            ss.set_value("户型图URL", house_picture_url)

            # 右上角信息
            if bs_obj.find("div", {"class": "msg"}):
                msg_spans = bs_obj.find("div", {"class": "msg"}).find_all("span")
                for span in msg_spans:
                    key = str(span).split("</label>")[1].split("</span")[0].strip()
                    value = span.find("label").text
                    value = float(value) if is_number(value) else value
                    value = None if value == "暂无数据" else value
                    ss.set_value(key, value)

            # 基本信息
            li_list = list()
            ## 基本属性
            if bs_obj.find("div", {"class": "base"}):
                li_list += bs_obj.find("div", {"class": "base"}).find_all("li")
            ## 交易属性
            if bs_obj.find("div", {"class": "transaction"}):
                li_list += bs_obj.find("div", {"class": "transaction"}).find_all("li")
            for li in li_list:
                key = li.find("span").text
                value = str(li).split("span>")[1].split("</li")[0].strip()
                if "面积" in key:
                    value = float(value[:-1]) if is_number(value[:-1]) else value
                elif "年限" in key:
                    value = int(value[:-1]) if is_number(value[:-1]) else value
                elif key == "所在楼层" and " (" in value:
                    floor, total_floors = value.strip().split(" ")
                    ss.set_value("楼层", floor)
                    if "共" in total_floors:
                        total_floors = int(total_floors.split("共")[1].split("层")[0])
                    ss.set_value("总楼层", total_floors)
                    continue
                elif key == "建成年代":
                    value = int(value) if is_number(value) else value
                value = None if value == "暂无数据" else value
                ss.set_value(key, value)
            done = True
        except Exception as e:
            try_times += 1
            if try_times == 5:
                print("[E]: get_transactions_from_xiaoqu_id, xiaoqu_id = ", trans_id, e)
                break
    return ss


def get_transaction_detail_all(city, start=0, end=None):
    df_trans_detail = pd.DataFrame()
    with futures.ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        future_list = list()
        trans_id_list = df_transactions.index.values[start:end]
        count = 0
        for trans_id in trans_id_list:
            future_list.append(executor.submit(get_transactions_detail_from_id, city, trans_id))
        for future in futures.as_completed(future_list):
            if future.exception() is not None:
                print(future.exception())
            else:
                ss_id = future.result()
                df_trans_detail = df_trans_detail.append(ss_id)            
            count += 1
            sys.stdout.write("\r获取成交记录详情网页: {}/{}".format(count, len(trans_id_list)))
        
    return df_trans_detail

def encode_address(address):
    http_url = "http://api.map.baidu.com/geocoder/v2/"
    params = {
        "address": address,
        "ak": BAIDU_AK,
        "output": "json"
    }
    try:
        ret = requests.get(http_url, params=params)
        o = json.loads(ret.text)
        if o['status'] != 0:
            print(ret.text)
            print("[E]: 地址编码异常: {}，".format(address))
            return None
        longtitude = o['result']['location']['lng']
        latitude = o['result']['location']['lat']
        return longtitude, latitude
    except Exception as e:
        print("[E]: 地址编码错误，" + address + e)
        return None

###########################################################
# 总共四个步骤，依次运行。
# 运行第一步的时候，把其余几步的代码注释掉，依次类推
###########################################################

# 设置城市, 更多城市根据链家网自行添加
CITY = city_dict["广州"]

# 1.爬取城市的小区ID列表

xiaoqu_list = get_xiaoqu_of_city(CITY)
with open("{}_list.txt".format(CITY), mode="w") as f:
    for xiaoqu in xiaoqu_list:
        f.write(xiaoqu + "\n")
print("list write finished.")


# 2.爬取小区ID列表对应的小区信息并保存

with open("{}_list.txt".format(CITY), mode="r") as f:
    xiaoqu_list = [int(line[:-1]) for line in f.readlines()]
print("获取小区信息 ...")
df_xiaoqu_info = get_xiaoqu_info_from_xiaoqu_list(CITY, xiaoqu_list)
df_xiaoqu_info.to_csv("{}_info.csv".format(CITY), sep=",", encoding="utf-8")
writer = pd.ExcelWriter("{}_info.xlsx".format(CITY))
df_xiaoqu_info.to_excel(writer, "小区信息")
writer.save()
print("小区信息保存成功.")


# 3.爬成交记录
# 首先先载入小区信息用于查询行政区域与片区

print("加载小区信息 ...")
with open("{}_list.txt".format(CITY), mode="r") as f:
    xiaoqu_list = [int(line[:-1]) for line in f.readlines()]
df_xiaoqu_info = pd.read_csv("./{}_info.csv".format(CITY), index_col=1)

# 开始爬取，分段进行，避免失败重新爬，根据具体情况设置PART的值
PART = 10
START = 0
df_transactions = pd.DataFrame()
print("爬取成交记录 ...")
for i in range(START, PART):
    start = int(i * len(xiaoqu_list) / PART)
    end = int((i + 1) * len(xiaoqu_list) / PART)
    df_transactions = df_transactions.append(get_transactions_from_xiaoqu_list(CITY, xiaoqu_list[start:end]))
    writer = pd.ExcelWriter("{}_成交记录_{}.xlsx".format(CITY, i+1))
    df_transactions.to_excel(writer, "Data")
    writer.save()
    df_transactions.to_csv("{}_成交记录_{}.csv".format(CITY, i+1), sep=",", encoding="utf-8")
    print("\nfile {} written.".format(i+1))
    try:
       os.remove("{}_成交记录_{}.csv".format(CITY, i))
       os.remove("{}_成交记录_{}.xlsx".format(CITY, i))
    except Exception as e:
        pass
shutil.copy("{}_成交记录_{}.xlsx".format(CITY, PART),
            "{}_成交记录.xlsx".format(CITY))
shutil.copy("{}_成交记录_{}.csv".format(CITY, PART),
            "{}_成交记录.csv".format(CITY))

# 4.根据成交记录id，爬取成交记录详情，附加到成交记录表中

print("加载成交记录 ...")
df_transactions = pd.read_excel("{}_成交记录.xlsx".format(CITY), index_col=0)
PART = 10
START = 0
df_trans_detail_all = pd.DataFrame()
print("获取成交记录详情 ...")
for i in range(START, PART):
    start = int(i * len(df_transactions) / PART)
    end = int((i + 1) * len(df_transactions) / PART)
    df_trans_detail_part = get_transaction_detail_all(CITY, start, end)
    df_trans_detail_all = df_trans_detail_all.append(df_trans_detail_part)
    # Pandas对导出的Excel支持的URL数量有限，所以Excel保存时去掉URL
    writer = pd.ExcelWriter("{}_成交记录_all_{}.xlsx".format(CITY, i+1))
    df_temp = df_trans_detail_all.drop("户型图URL", inplace=False, axis=1)
    df_temp.to_excel(writer, "Data")
    writer.save()
    df_trans_detail_all.to_csv("{}_成交记录_all_{}.csv".format(CITY, i+1), sep=",", encoding="utf-8")
    try:
        os.remove("{}_成交记录_all_{}.csv".format(CITY, i))
        os.remove("{}_成交记录_all_{}.xlsx".format(CITY, i))
    except Exception as e:
        pass
    print("\nfile {} written.".format(i+1))

# 5.根据小区地址，利用百度地图API进行地理编码，获取经纬度信息

# print("开始进行地理编码...")
# print("加载小区信息 ...")
# df_xiaoqu_info = pd.read_csv("./{}_info.csv".format(CITY), index_col=1)
# xiaoqu_list = df_xiaoqu_info.index.values.tolist()

# for count, xiaoqu in enumerate(xiaoqu_list[:100]):
#     address = df_xiaoqu_info.loc[xiaoqu, '地址']
#     address = CITY + address
#     longtitude, latitude = encode_address(address)
#     if longtitude is None:
#         continue
#     df_xiaoqu_info.loc[xiaoqu, '坐标-经度'] = longtitude
#     df_xiaoqu_info.loc[xiaoqu, '坐标-纬度'] = latitude
#     sys.stdout.write("\r已完成: {}/{}".format(count, len(xiaoqu_list)))
# print("保存数据...")
# writer = pd.ExcelWriter("{}_info.xlsx".format(CITY))
# df_xiaoqu_info.to_excel(writer, "小区信息")
# writer.save()
