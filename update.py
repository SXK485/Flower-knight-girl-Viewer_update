# 导入requests库，用于发送网络请求
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import threading
# 导入hashlib库，用于进行md5加密
import hashlib
# 导入zlib库，用于进行zlib解压缩
import zlib
# 导入os库，用于进行文件和目录操作
import os
import random
import urllib.request
import urllib.parse
import urllib.error
import re
import shutil
import time
import json
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from PIL import Image

qww = lambda x, y: True if x == y else False

# 定义一个常数，表示图片的前缀
IMAGE_PREFIX = "https://dugrqaqinbtcq.cloudfront.net/product/ynnFQcGDLfaUcGhp/assets/ultra/images/hscene_r18/"
# 定义一个常数，表示语音的前缀
VOICE_PREFIX = "https://dugrqaqinbtcq.cloudfront.net/product/ynnFQcGDLfaUcGhp/assets/voice/c/"
# 定义一个常数，表示剧本的前缀
SCRIPT_PREFIX = "https://dugrqaqinbtcq.cloudfront.net/product/ynnFQcGDLfaUcGhp/assets/event/hscene_r18/"
#定义一个常数，表示spine动画文件的前缀
URL_R18 = 'https://dugrqaqinbtcq.cloudfront.net/product/ynnFQcGDLfaUcGhp/assets/hscene_r18_spine/'

def main():
    baseurl1 = "https://flowerknight.fandom.com/wiki/List_of_Flower_Knights_by_ID"

    # 将时间间隔转换为天数
    YOUR_TIME_INTERVAL = 30  # 7天

    # 将时间间隔转换为秒
    time_interval_in_seconds = YOUR_TIME_INTERVAL * 24 * 60 * 60

    #检查文件是否存在
    if os.path.isfile("differenceList.txt"):
        # 如果文件存在，则获取文件的修改时间
        file_time = os.path.getmtime("differenceList.txt")
        # 获取当前时间
        current_time = time.time()
        # 计算文件的年龄（以秒为单位）
        file_age = current_time - file_time
        # 如果文件的年龄超过指定时间，则重新获取数据
        if file_age > time_interval_in_seconds:
            datalist = getData(baseurl1)
            if not datalist:
                return
            # 将数据保存到文本文件中
            with open("differenceList.txt", "w") as f:
                for item in datalist:
                    f.write(str(item) + "\n")
        else:
            # 如果文件未过期，则读取文件并将其转换为整数列表
            with open("differenceList.txt", "r") as f:
                datalist = [int(line.strip()) for line in f.readlines()]
    else:
        # 如果文件不存在，则重新获取
        datalist = getData(baseurl1)
        if not datalist:
            return
        # 将数据保存到文本文件中
        with open("differenceList.txt", "w") as f:
            for item in datalist:
                f.write(str(item) + "\n")

    # datalist = [100011]

    if not os.path.exists("scenes"):
        os.mkdir("scenes")

    # 定义一个列表，存储所有线程
    threads = []

    for id in datalist:
        t = threading.Thread(target=download_role, args=(id,))
        threads.append(t)
        t.start()

    # 等待所有线程执行完毕
    for t in threads:
        t.join()

    if not os.path.exists("data/scripts/data"):
        os.makedirs("data/scripts/data")

    #获取sceneData.js
    get_sceneData()

def download_role(id):
    print(str(id)+"线程")
    # 判断是否有动画
    is_spine = False

    # 定义一个变量，表示角色的形态，1表示普通形态，2表示开花形态
    form = 1
    if id > 400000:
        form = 2
        id -= 300000
    # 定义一个变量，表示资源文件夹的名称
    folder_name = "c" + str(id)
    # 如果形态为2，表示开花形态，需要在资源文件夹的名称后面加上_2
    if form == 2:
        folder_name += "_2"
    #
    folder_path = "scenes/"+folder_name
    # 创建资源文件夹
    if not os.path.exists(folder_path):
        os.mkdir(folder_path)
    if os.path.exists(folder_path + "/script.txt"):
        print(folder_name+"已存在!")
        return
    # 在资源文件夹中创建images文件夹
    if not os.path.exists(folder_path + "/images"):
        os.mkdir(folder_path + "/images")
    # 在资源文件夹中创建voices文件夹
    if not os.path.exists(folder_path + "/voices"):
        os.mkdir(folder_path + "/voices")

    # 定义一个变量，表示图片的数量，根据您的需求可以修改
    image_num = 2
    # 遍历图片的数量，从0开始计数
    None_H = False
    for i in range(image_num):
        # 定义一个变量，表示图片的名称，根据您的需求可以修改
        if form == 1:
            image_name = "r18_" + str(id) + "_00" + str(i)
        elif form == 2:
            image_name = "r18_" + str(id) + "_10" + str(i)
        # 使用md5加密图片的名称，并转换为16进制字符串
        image_md5 = hashlib.md5(image_name.encode()).hexdigest()
        # 拼接图片的url，使用前缀和加密后的字符串，并添加.bin后缀
        image_url = IMAGE_PREFIX + image_md5 + ".bin"
        # 拼接图片的文件名，使用资源文件夹名称和图片名称，并添加.jpg后缀
        image_file_name = folder_path + "/images/" + image_name + ".jpg"
        # 调用函数，下载图片，并保存为jpg格式
        None_H = download_image(image_url, image_file_name)
    if None_H == True:
        # 删除文件夹及其内容
        shutil.rmtree(folder_path)
        print(folder_path + "该角色无场景")
        return

    # 定义一个变量，表示剧本的名称，根据您的需求可以修改
    if form == 1:
        script_name = "hscene_r18_" + str(id)
    elif form == 2:
        script_name = "hscene_r18_" + str(id) + "_2"
    # 使用md5加密剧本的名称，并转换为16进制字符串
    script_md5 = hashlib.md5(script_name.encode()).hexdigest()
    # 拼接剧本的url，使用前缀和加密后的字符串，并添加.bin后缀
    script_url = SCRIPT_PREFIX + script_md5 + ".bin"
    # 拼接剧本的文件名，使用资源文件夹名称和script.txt作为名称，并添加.txt后缀
    # script_file_name = folder_name + "/script.txt"
    # 调用函数，下载剧本，并保存为txt格式，并进行zlib解压缩
    download_script(script_url, folder_path + "/script_original.txt")

    result = script_conversion(folder_path, folder_path + "/script_original.txt", is_spine)
    is_spine = result[0]
    voice_num = result[1]
    if is_spine == True:
        download_spine(str(id), folder_path, URL_R18)
        is_spine = False

    print("音频数量" + str(voice_num))
    # 遍历语音的数量，从1开始循环到46
    for i in range(1, voice_num + 1):
        # 定义一个变量，表示语音的名称，根据您的需求可以修改
        if form == 1:
            voice_name = "fkg_" + str(id) + "_hscene0" + str(i).zfill(2)
        elif form == 2:
            voice_name = "fkg_" + str(id) + "_hscene2" + str(i).zfill(2)
        print(voice_name)
        # 使用md5加密语音的名称，并转换为16进制字符串
        voice_md5 = hashlib.md5(voice_name.encode()).hexdigest()
        # 拼接语音的url，使用前缀和角色id和加密后的字符串，并添加.mp3后缀
        voice_url = VOICE_PREFIX + str(id) + "/" + voice_md5 + ".mp3"
        # 拼接语音的文件名，使用资源文件夹名称和语音名称，并添加.mp3后缀
        voice_file_name = folder_path + "/voices/" + voice_name + ".mp3"
        # 调用函数，下载语音，并保存为mp3格式
        download_voice(voice_url, voice_file_name)

    # 打印完成信息
    print(str(id) + "资源文件夹已经生成完毕，请查看")

# 定义一个函数，用于从数据结构中提取角色的id
def get_id_from_data():
    # folder_path = "E:\さいきん\Flower knight girl Viewer 1.0\package.nw\scenes"
    folder_path = "scenes"
    folder_names = []

    for folder_name in os.listdir(folder_path):
        if folder_name.startswith("c"):
            if "_" in folder_name:
                # If the folder name is c110001_2, then we need to add 300000 to 110001 to get 410001
                folder_id = int(folder_name[1:7]) + 300000
            else:
                # If the folder name is c100001, then we need to remove the first character to get 100001
                folder_id = int(folder_name[1:])
            folder_names.append(folder_id)

    return folder_names


# 定义一个函数，用于判断一个id是否在数据结构中
def in_data(id, data_id_list):
    # 判断id是否在数据结构的id列表中
    if id in data_id_list:
        # 如果在列表中，返回True
        return True
    else:
        # 如果不在列表中，返回False
        return False


def askURL(url):
    headers_list = [
        {
            'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (iPad; CPU OS 13_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/87.0.4280.77 Mobile/15E148 Safari/604.1'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 8.0; Pixel 2 Build/OPD3.170816.012) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.109 Safari/537.36 CrKey/1.54.248666'
        }, {
            'user-agent': 'Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.188 Safari/537.36 CrKey/1.54.250320'
        }, {
            'user-agent': 'Mozilla/5.0 (BB10; Touch) AppleWebKit/537.10+ (KHTML, like Gecko) Version/10.0.9.2372 Mobile Safari/537.10+'
        }, {
            'user-agent': 'Mozilla/5.0 (PlayBook; U; RIM Tablet OS 2.1.0; en-US) AppleWebKit/536.2+ (KHTML like Gecko) Version/7.2.1.0 Safari/536.2+'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; U; Android 4.3; en-us; SM-N900T Build/JSS15J) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; U; Android 4.1; en-us; GT-N7100 Build/JRO03C) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; U; Android 4.0; en-us; GT-I9300 Build/IMM76D) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 7.0; SM-G950U Build/NRD90M) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.84 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 8.0.0; SM-G965U Build/R16NW) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.111 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 8.1.0; SM-T837A) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.80 Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; U; en-us; KFAPWI Build/JDQ39) AppleWebKit/535.19 (KHTML, like Gecko) Silk/3.13 Safari/535.19 Silk-Accelerated=true'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; U; Android 4.4.2; en-us; LGMS323 Build/KOT49I.MS32310c) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/102.0.0.0 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Windows Phone 10.0; Android 4.2.1; Microsoft; Lumia 550) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/46.0.2486.0 Mobile Safari/537.36 Edge/14.14263'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 6.0.1; Moto G (4)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 6.0.1; Nexus 10 Build/MOB31T) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 4.4.2; Nexus 4 Build/KOT49H) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 8.0.0; Nexus 5X Build/OPR4.170623.006) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 7.1.1; Nexus 6 Build/N6F26U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 8.0.0; Nexus 6P Build/OPP3.170518.006) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 6.0.1; Nexus 7 Build/MOB30X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (compatible; MSIE 10.0; Windows Phone 8.0; Trident/6.0; IEMobile/10.0; ARM; Touch; NOKIA; Lumia 520)'
        }, {
            'user-agent': 'Mozilla/5.0 (MeeGo; NokiaN9) AppleWebKit/534.13 (KHTML, like Gecko) NokiaBrowser/8.5.0 Mobile Safari/534.13'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 9; Pixel 3 Build/PQ1A.181105.017.A1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.158 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; Pixel 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 11; Pixel 3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.181 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 5.0; SM-G900P Build/LRX21T) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 8.0; Pixel 2 Build/OPD3.170816.012) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (Linux; Android 8.0.0; Pixel 2 XL Build/OPD1.170816.004) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.0.0 Mobile Safari/537.36'
        }, {
            'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1'
        }, {
            'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1'
        }, {
            'user-agent': 'Mozilla/5.0 (iPad; CPU OS 11_0 like Mac OS X) AppleWebKit/604.1.34 (KHTML, like Gecko) Version/11.0 Mobile/15A5341f Safari/604.1'
        }, {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36'
        }
    ]

    headers = random.choice(headers_list)

    data = bytes(urllib.parse.urlencode({"name": "eric"}), encoding="utf-8")
    request = urllib.request.Request(url, data=data, headers=headers)
    html = ""

    session = requests.Session()
    retry = Retry(total=100,
                  backoff_factor=0.1,
                  status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retry))
    session.mount('https://', HTTPAdapter(max_retries=retry))

    try:
        response = urllib.request.urlopen(request)
        html = response.read().decode("utf-8")
        response.close()
        return html
    except:
        # for i in range(100):  # 循环去请求网站
        #     try:
        #         response = requests.get(url, headers=headers, timeout=20)
        #         try:
        #             if response.code == 200:
        #                 html = response.read().decode("utf-8")
        #                 response.close()
        #                 return html
        #         except AttributeError:
        #             print(response)
        #     except:
        #         html = askURL(url)
        #         return html
        while True:
            try:
                response = session.get(url, headers=headers, timeout=20)
                if response.status_code == 200:
                    html = response.text
                    return html

            except requests.exceptions.RequestException as e:
                print("Request failed, retrying:", url)
                html = ""
                continue
    # return html  # 返回一个html页面


# 爬取页面
def getData(baseurl):

    data_id_list = get_id_from_data()
    print(data_id_list)

    url = "https://flowerknight.fandom.com"
    html = askURL(baseurl)  # 保存获取到的网页源码
    bs = BeautifulSoup(html, "html.parser")

    listOne = bs.select('table.sortable.wikitable > tbody', limit=1)  # 查找id为“sortable wikitable”的table标签的
    # 子标签————tbody,同时只找到第一个，因为第二个tbody的id相同
    bloomedList = []
    idList = []

    #2、3、4星角色ID集合
    lowIDList = [131909, 141101, 160007, 130801, 152701, 120801, 111505, 160809, 142201, 140901,
                 111101, 121601, 131901, 132001, 111903, 132401, 140803, 111501, 141301, 122301,
                 111905, 160405, 141901, 142501, 110807, 141303, 132801, 120401, 120201, 142401,
                 120701, 151801, 111503, 112601, 120203, 122305, 121303, 141701, 135101, 152501,
                 150803, 152711, 132101, 152709, 132501, 120101, 151901, 150801, 160011, 160011,
                 130501, 152001, 152401, 152801, 122701, 122401, 152707, 130301, 160005]

    for item in listOne:
        listTwo = item.select('tr')[2:]  # 跳过数组的前两个元素
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(process_item, item1, data_id_list, url, lowIDList)
                       for item1 in listTwo]

            for future in futures:

                row_id = None
                bloomed_id = None

                result = future.result()

                if result:
                    row_id, bloomed_id = result

                if row_id:
                    idList.append(row_id)

                if bloomed_id:
                    bloomedList.append(bloomed_id)

        print(idList)
        print(bloomedList)

        resultList = idList + bloomedList
        print(resultList)

        #找出ID差集，并保存
        differenceSet = set(resultList).difference(set(data_id_list))
        differenceList = list(differenceSet)
        print(differenceList)
        if differenceList:
            with open("differenceList.txt", "w") as f:
                for differenceID in differenceList:
                    f.write(str(differenceID) + "\n")

        return differenceList

def process_item(item1, data_id_list, url, lowIDList):
    listThr = item1.findAll('td')[1:4]  # 只查找第二和第三个元素

    print(listThr[1])

    rowID = int(listThr[0].get_text())
    bloomedID = None

    # 获取角色详情页
    detialUrl = listThr[1].select("td > a")[0].get("href")
    # 获取角色的id
    id = int(listThr[0].get_text()) + 300000
    # 跳过已经开花场景的角色，跳过2、3、4星角色
    if in_data(id, data_id_list) == True or in_data(int(listThr[0].get_text()), lowIDList) == True:
        print("跳过" + str(id))
        return
    print(url + detialUrl)
    detailHtml = askURL(url + detialUrl)
    try:
        bs1 = BeautifulSoup(detailHtml, "html.parser")
    except TypeError:
        print(detailHtml)
    table = bs1.select('table.wikitable.cs.cs-force-center')[0]
    listFour = table.findAll('tbody')

    # print(t_list3)
    status2 = 0

    # 开花寝室
    for item2 in listFour:

        listFive = item2.findAll('tr')[7:]

        for liem3 in listFive:
            td = liem3.findAll('td')[0]
            tdName = td.get_text()
            if qww("Bloomed\n", tdName) == True:
                if liem3.findAll('td')[1] != None:
                    print(liem3.findAll('td')[1].select("img")[0])
                    if liem3.findAll('td')[1].select("img")[0] != None:
                        line = liem3.findAll('td')[1].select("img")[0].get("alt")
                        pattern = "Icon (.+).png"
                        m = re.search(pattern, str(line))

                        if m != None or qww(line, listThr[2].findAll('a')[0].get_text()):
                            status2 = int(listThr[0].get_text()) + 300000
                            print("开花"+str(status2))
                            print("\n")
                            bloomedID = status2

    print(int(listThr[0].get_text()))
    return rowID, bloomedID

#遍历scenes文件夹并输出sceneData.js
def get_sceneData():
    # 遍历scenes文件夹
    scenes_dir = 'scenes'
    scene_data = {}

    for scene_folder in os.listdir(scenes_dir):
        scene_id = scene_folder[1:7]

        if "_" in scene_folder:
            form = 2
        else:
            form = 1

        # 检查是否包含spines文件夹
        has_spines = os.path.exists(os.path.join(scenes_dir, scene_folder, 'spines'))

        scene_data[scene_folder] = {
            "SCRIPTS": {
                "PART1": {
                    "SCRIPT": open(os.path.join(scenes_dir, scene_folder, 'script.txt'), encoding='utf-8').read().split(
                        '\n'),
                    "HIERARCHY": {
                        "pairList": []
                    },
                    "NAME": scene_folder,
                    "THUMBNAIL": f"r18_{scene_id}_000" if form == 1 else f"r18_{scene_id}_100",
                    "ANIMATED": "1" if has_spines else "0"
                }
            }
        }

    # 输出sceneData.js
    scene_data_js = f"sceneData = {json.dumps(scene_data, indent=2, ensure_ascii=False)}"
    with open('data\scripts\data\sceneData.js', 'w', encoding='utf-8') as f:
        f.write(scene_data_js)

# 定义一个函数，用于下载图片，并保存为jpg格式
def download_image(url, file_name):

    max_retries = 5

    for i in range(max_retries):

        try:
            # 定义重试策略
            retry_strategy = Retry(
                total=50,  # 最大重试次数
                status_forcelist=[500, 502, 503, 504],  # 遇到这些状态码时重试
                backoff_factor=1  # 重试之间的时间间隔
            )

            # 创建一个会话对象
            session = requests.Session()
            session.mount("http://", HTTPAdapter(max_retries=retry_strategy))
            session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

            # 发送网络请求，获取图片的内容
            response = session.get(url)
            # 判断网络请求是否成功
            if response.status_code == 200:
                # 获取图片的二进制数据
                image_data = response.content
                # 打开一个文件，以二进制写入模式
                with open(file_name, "wb") as f:
                    # 将图片的二进制数据写入文件中
                    f.write(image_data)
                    # 关闭文件
                    f.close()
                    return
            else:
                # 打印错误信息
                print("网络请求失败，请检查url是否正确")
                None_H = True
                return None_H

        except Exception as e:
            print(f"Download exception: {e}")

            if i == max_retries - 1:
                print(f"Failed after {max_retries} retries for {url}")
                return

            else:
                time.sleep(1)
                continue


# 定义一个函数，用于下载语音，并保存为mp3格式
def download_voice(url, file_name):

    max_retries = 5

    for i in range(max_retries):

        try:
            # 定义重试策略
            retry_strategy = Retry(
                total=50,  # 最大重试次数
                status_forcelist=[500, 502, 503, 504],  # 遇到这些状态码时重试
                backoff_factor=1  # 重试之间的时间间隔
            )

            # 创建一个会话对象
            session = requests.Session()
            session.mount("http://", HTTPAdapter(max_retries=retry_strategy))
            session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

            # 发送网络请求，获取语音的内容
            response = session.get(url)
            # 判断网络请求是否成功
            if response.status_code == 200:
                # 获取语音的二进制数据
                voice_data = response.content
                # 打开一个文件，以二进制写入模式
                with open(file_name, "wb") as f:
                    # 将语音的二进制数据写入文件中
                    f.write(voice_data)
                    # 关闭文件
                    f.close()
                    return
            else:
                # 打印错误信息
                print("网络请求失败，请检查url是否正确")

        except Exception as e:
            print(f"Download exception: {e}")

            if i == max_retries - 1:
                print(f"Failed after {max_retries} retries for {url}")
                return

            else:
                time.sleep(1)
                continue

# 定义一个函数，用于下载剧本，并保存为txt格式，并进行zlib解压缩
def download_script(url, file_name):

    max_retries = 5

    for i in range(max_retries):

        try:
            # 定义重试策略
            retry_strategy = Retry(
                total=50,  # 最大重试次数
                status_forcelist=[500, 502, 503, 504],  # 遇到这些状态码时重试
                backoff_factor=1  # 重试之间的时间间隔
            )

            # 创建一个会话对象
            session = requests.Session()
            session.mount("http://", HTTPAdapter(max_retries=retry_strategy))
            session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

            # 发送网络请求，获取剧本的内容
            response = session.get(url)
            # 判断网络请求是否成功
            if response.status_code == 200:
                # 获取剧本的二进制数据，并进行zlib解压缩
                script_data = zlib.decompress(response.content,wbits=15+32)
                # 打开一个文件，以二进制写入模式
                with open(file_name, "wb") as f:
                    # 将剧本的文本数据写入文件中
                    f.write(script_data)
                    # 关闭文件
                    f.close()
                    return
            else:
                # 打印错误信息
                print("网络请求失败，请检查url是否正确")

        except Exception as e:
            print(f"Download exception: {e}")

            if i == max_retries - 1:
                print(f"Failed after {max_retries} retries for {url}")
                return

            else:
                time.sleep(1)
                continue

def script_conversion(file_name, script_original, is_spine):
    voice_num = 0
    # 打开原始文件
    with open(script_original, 'r', encoding='utf-8') as f:
        # 读取所有行
        lines = f.readlines()
        # 创建一个空列表，用于存储转换后的行
        new_lines = []
        # 在列表中添加第一行固定内容
        new_lines.append('<BGM_PLAY>fkg_bgm_hscene001,1000\n')
        # 遍历原始文件的每一行
        for line in lines:
            if line == '':
                continue
            # 去掉行尾的换行符
            line = line.strip()
            # 去掉可能存在的 BOM 字符
            line = line.replace('\ufeff', '')
            # 如果行以 mess 开头，表示是对话内容
            if line.startswith('mess,'):
                # 用逗号分割行，得到四个部分
                parts = line.split(',')
                # 如果第二个部分为空，表示是内心对白
                if parts[1] == '':
                    # 在列表中添加<NAME_PLATE>标签和对白内容
                    new_lines.append('<NAME_PLATE>\n')
                    new_lines.append(parts[2] + '\n')
                    # 在列表中添加<PAUSE>标签
                    new_lines.append('<PAUSE>\n')
                # 如果第二个部分不为空，表示是人物对白
                else:
                    # 如果第四个部分不为空，表示有音频名称
                    if parts[3] != '':
                        voice_num += 1
                        # 在列表中添加<VOICE_PLAY>标签和音频名称，其中音频名称需要去掉 ID，只保留 fkg_ 开头的部分
                        new_lines.append('<VOICE_PLAY>' + parts[3].split('/')[1] + '\n')
                    # 在列表中添加<NAME_PLATE>标签和人物名字
                    new_lines.append('<NAME_PLATE>' + parts[1] + '\n')
                    # 在列表中添加对白内容
                    new_lines.append(parts[2] + '\n')
                    # 在列表中添加<PAUSE>标签
                    new_lines.append('<PAUSE>\n')
            # 如果行以 effect 开头，表示是特效内容
            elif line.startswith('effect'):
                # 用逗号分割行，得到四个部分
                parts = line.split(',')
                # 如果第二个部分是 3，表示是白色淡入效果
                if parts[1] == '3':
                    # 在列表中添加<FADE_IN>标签和参数
                    new_lines.append('<FADE_IN>white,670\n')
                # 如果第二个部分是 4，表示是闪烁效果的结束
                elif parts[1] == '4':
                    # 在列表中添加闪烁效果的最后一个标签和参数
                    new_lines.append('<FADE_OUT>white,670\n')
                    # 如果第二个部分是 5，表示是闪烁效果的开始
                elif parts[1] == '5':
                    # 在列表中添加闪烁效果的一系列标签和参数
                    new_lines.append('<FADE_OUT>white,100\n')
                    new_lines.append('<FADE_IN>white,100\n')
                    new_lines.append('<WAIT>100\n')
                    new_lines.append('<FADE_OUT>white,200\n')
                    new_lines.append('<FADE_IN>white,200\n')
                    new_lines.append('<WAIT>100\n')
                    new_lines.append('<FADE_OUT>white,200\n')
                    new_lines.append('<FADE_IN>white,200\n')
                # 如果第二个部分是 6，表示是淡出效果
                if parts[1] == '6':
                    # 在列表中添加<FADE_OUT>标签和参数
                    new_lines.append('<FADE_OUT>black,670\n')
                # 如果第二个部分是 7，表示是淡入效果
                elif parts[1] == '7':
                    # 在列表中添加<FADE_IN>标签和参数
                    new_lines.append('<FADE_IN>black,670\n')
            # 如果行以 image 开头，表示是图片内容
            elif line.startswith('image,'):
                # 用逗号分割行，得到四个部分
                parts = line.split(',')
                # 在列表中添加<EV>标签和参数，其中图片名称需要去掉前缀 hscene_r18/
                new_lines.append('<EV>' + parts[1].replace('hscene_r18/', '') + ',NONE,0\n')
            # 如果行以 message_window 开头，表示是界面显示内容
            elif line.startswith('message_window,'):
                # 用逗号分割行，得到三个部分
                parts = line.split(',')
                # 如果第二个部分是 0，表示是隐藏界面
                if parts[1] == '0':
                    # 在列表中添加<UI_DISP>标签和参数
                    new_lines.append('<UI_DISP>OFF,0\n')
                # 如果第二个部分是 1，表示是显示界面
                elif parts[1] == '1':
                    # 在列表中添加<UI_DISP>标签和参数
                    new_lines.append('<UI_DISP>ON,0\n')
            # 如果行以 spine 开头，表示是动画内容
            elif line.startswith('spine,'):
                is_spine = True
                # 用逗号分割行，得到六个部分
                parts = line.split(',')
                # 在列表中添加<SPINE>标签和参数，其中动画名称需要去掉前缀 hscene_r18_spine/
                new_lines.append(
                    '<SPINE>' + parts[1].replace('hscene_r18_spine/', '') + ',' + ','.join(parts[2:]) + '\n')
            # 如果行以 spine_play 开头，表示是动画播放内容
            elif line.startswith('spine_play,'):
                # 用逗号分割行，得到四个部分
                parts = line.split(',')
                # 在列表中添加<SPINE_PLAY>标签和参数，去掉最后的逗号
                new_lines.append('<SPINE_PLAY>' + ','.join(parts[1:-1]) + '\n')
            # 如果行以 spine_effect 开头，表示是动画特效内容
            elif line.startswith('spine_effect,'):
                # 用逗号分割行，得到四个部分
                parts = line.split(',')
                # 只有当第三个部分为空时，才会执行对特效的处理
                if parts[2] == '':
                    # 如果第二个部分是 3，表示是白色淡入效果
                    if parts[1] == '3':
                        # 在列表中添加<FADE_IN2>标签和参数
                        new_lines.append('<FADE_IN2>white,670\n')
                    # 如果第二个部分是 4，表示是闪烁效果的结束
                    elif parts[1] == '4':
                        # 在列表中添加闪烁效果的最后一个标签和参数
                        new_lines.append('<FADE_OUT2>white,670\n')
                    # 如果第二个部分是 5，表示是闪烁效果的开始
                    elif parts[1] == '5':
                        # 在列表中添加闪烁效果的一系列标签和参数
                        new_lines.append('<FADE_OUT2>white,100\n')
                        new_lines.append('<FADE_IN2>white,100\n')
                        new_lines.append('<WAIT2>100\n')
                        new_lines.append('<FADE_OUT2>white,200\n')
                        new_lines.append('<FADE_IN2>white,200\n')
                        new_lines.append('<WAIT2>100\n')
                        new_lines.append('<FADE_OUT2>white,200\n')
                        new_lines.append('<FADE_IN2>white,200\n')
                    # 如果第二个部分是 6，表示是黑色淡出效果
                    elif parts[1] == '6':
                        # 在列表中添加<FADE_OUT2>标签和参数
                        new_lines.append('<FADE_OUT2>black,670\n')
                # 如果第二个部分是 7，表示是黑色淡入效果
                if parts[1] == '7':
                    # 在列表中添加<FADE_IN2>标签和参数
                    new_lines.append('<FADE_IN2>black,670\n')
            # 如果行以 spine_wait 开头，表示是动画等待内容
            elif line.startswith('spine_wait,'):
                # 用逗号分割行，得到三个部分
                parts = line.split(',')
                # 在列表中添加<WAIT2>标签和参数，其中等待时间需要乘以 1000 转换为毫秒
                new_lines.append('<WAIT2>' + str(int(float(parts[1]) * 1000)) + '\n')
        # 在列表末尾添加固定内容
        new_lines.append('<BGM_STOP>500\n')
        new_lines.append('<UI_DISP>OFF, 500\n')
        new_lines.append('<BG_OUT>500\n')
        new_lines.append('<SCENARIO_END>')
    # 打开新的文件，用于写入转换后的内容
    with open(file_name+'/script.txt', 'w', encoding='utf-8') as f:
        # 遍历转换后的每一行
        for line in new_lines:
            # 写入文件，并在每一行后面加上换行符
            f.write(line)
    print("音频数量"+str(voice_num))
    return is_spine,voice_num

def download_spine(id, folder_name, url_r18):
    path_per_id = os.path.join(folder_name, "spines")
    os.makedirs(path_per_id, exist_ok=True)
    # atlas
    md5_name = hashlib.md5(('atlasr18_spine_' + id + '_000').encode()).hexdigest()
    res = requests.get(url_r18 + md5_name + '.bin')
    # print('atlasr18_spine_'+id+'_000')
    # print(url_r18+md5_name+'.bin')
    with open(os.path.join(path_per_id, 'atlasr18_spine_' + id + '_000.atlas'), 'wb') as fp:
        fp.write(zlib.decompress(res.content))

    md5_name = hashlib.md5(('spiner18_spine_' + id + '_000').encode()).hexdigest()
    res = requests.get(url_r18 + md5_name + '.bin')
    # p/rint(url_r18+md5_name+'.bin')
    with open(os.path.join(path_per_id, 'spiner18_spine_' + id + '_000.json'), 'wb') as fp:
        fp.write(zlib.decompress(res.content))

    # images loop
    for i in range(0, 7):
        if i == 0:
            webpname = 'webpr18_spine_' + id + '_000'
            webpsavename = 'r18_spine_' + id + '_000'
        else:
            webpname = 'webpr18_spine_' + id + '_000_' + str(i + 1)
            webpsavename = 'r18_spine_' + id + '_000_' + str(i + 1)

        md5_name = hashlib.md5((webpname).encode()).hexdigest()
        res = requests.get(url_r18 + md5_name + '.bin')
        if res.status_code == 200:
            # print(webpname)
            # print(url_r18+md5_name+'.bin')
            with open(os.path.join(path_per_id, webpsavename + '.png'), 'wb') as fp:
                fp.write(zlib.decompress(res.content))
            img = Image.open(os.path.join(path_per_id, webpsavename + '.png'))
            img.save(os.path.join(path_per_id, webpsavename + '.png'), 'png')
        else:
            print('not found:' + str(i + 1))


if __name__ == "__main__":
    main()