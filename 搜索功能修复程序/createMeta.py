import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import json
import os
import random
import time
import urllib.request
import urllib.parse
import urllib.error
import re
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

qww = lambda x, y: True if x == y else False
# import MeCab

# scenes_path = 'E:\さいきん\Flower\kfg-viewer\public\scenes'
scenes_path = 'scenes'
data_path = 'data.json'


def get_scene_ids():
    scene_ids = []
    for folder_name in os.listdir(scenes_path):
        if folder_name.startswith("c"):
            if "_" in folder_name:
                # If the folder name is c110001_2, then we need to add 300000 to 110001 to get 410001
                folder_id = int(folder_name[1:7]) + 300000
            else:
                # If the folder name is c100001, then we need to remove the first character to get 100001
                folder_id = int(folder_name[1:])
            scene_ids.append(folder_id)

    return scene_ids


def load_data():
    with open(data_path, 'r', encoding="utf-8") as f:
        data = json.load(f)
    return data['charaData']

def get_aliases(name):
    # mecab = MeCab.Tagger("-Owakati")

    # 删除括号
    name = name.replace('(', ' ').replace(')', ' ')

    # 按照空格分割字符串
    aliases = name.split()

    return aliases


def get_eng_aliases(eng_name):
    # 去除括号并分割字符串
    parts = eng_name.replace('(', '').replace(')', '').split()

    # 初始化结果列表
    aliases = []

    # 处理每一部分
    for i in range(0, len(parts), 2):
        # 添加第一个单词
        aliases.append(parts[i])
        # 如果存在第二个单词，将两个单词反过来并添加
        if i + 1 < len(parts):
            aliases.append(parts[i + 1] + ' ' + parts[i])
            aliases.append(parts[i + 1])

    return aliases


def get_eng_name(eng_name):
    name = eng_name

    if "(" in name:
        parts = name.split("(")
        name = parts[0].strip()
        form = parts[1][:-1].replace("-", "_")
    else:
        form = None

    name = name.upper().replace(" ", "_").replace("-", "_").replace("'", "")

    return name, form

def get_form_name(form):
    if not form:
        return None

    parts = form.split()
    if len(parts) > 1:
        return parts[-1].lower()
    else:
        return form.lower()


def generate_meta():
    scene_ids = get_scene_ids()
    chara_data = load_data()

    artist_dict = {}
    tag_dict = {}
    cv_dict = {}
    char_dict = {}
    scene_dict = {}

    for chara in chara_data:

        char_id = chara['id']

        if char_id in scene_ids:
            name = chara['name']
            eng_name, form = get_eng_name(chara['engName'])

            formName = get_form_name(form)

            aliases = get_aliases(chara['name'])
            engAlias = get_eng_aliases(chara['engName'])


            if eng_name not in char_dict:
                # char_dict[eng_name] = {}
                char_dict[eng_name] = {"base": {}}

            if form:
                if "form" not in char_dict[eng_name]:
                    char_dict[eng_name]["form"] = {}
                # char_dict[eng_name]["form"] = {"form": {}}
                char_dict[eng_name]["form"][formName] = {}
                char_dict[eng_name]["form"][formName]["name"] = {
                    "eng": chara['engName'],
                    "engAlias": engAlias,
                    "jap": name,
                    "japAlias": aliases,
                }
                # char_dict[eng_name]["form"][formName]["tags"] = []
                # char_dict[eng_name]["form"][formName]["gender"] = "male"
                # char_dict[eng_name]["form"][formName]["artist"] = "ARTIST.IGNORE"
                # char_dict[eng_name]["form"][formName]["cv"] = "CV.IGNORE"
            else:
                char_dict[eng_name]["base"]["name"] = {
                    "eng": chara['engName'],
                    "engAlias": engAlias,
                    "jap": name,
                    "japAlias": aliases
                }
                char_dict[eng_name]["base"]["tags"] = []
                char_dict[eng_name]["base"]["gender"] = "female"
                char_dict[eng_name]["base"]["artist"] = "ARTIST.IGNORE"
                char_dict[eng_name]["base"]["cv"] = "CV.IGNORE"

            # 检查 char_id 是否大于 300000，如果是，恢复原来的名称
            if char_id >= 300000:
                char_id -= 300000
                char_id = str(char_id)+"_2"
            scene_dict[f'c{char_id}'] = {
                'character': [f"CHAR.{eng_name}"]
                # 'nextScene': f'c{char_id}_2'
            }
            # 如果 formName 存在，添加 'form' 键值对
            if formName:
                scene_dict[f'c{char_id}']['form'] = [formName]

            scene_dict[f'c{char_id}']['tags'] = {
                "female": [],
                "male": [],
                "location": [],
                "misc": []
            }
            scene_dict[f'c{char_id}']['ignoredCharacterTags'] = []

    # 检查是否有空的char_dict[XXX]["base"]，如果有，用char_dict[XXX]["form"]赋值给它
    for char_name, char_info in char_dict.items():
        if not char_info["base"]:
            base_key = list(char_info["form"].keys())[0]
            char_info["base"] = char_info["form"][base_key]
            char_info["base"]["tags"] = []
            char_info["base"]["gender"] = "female"
            char_info["base"]["artist"] = "ARTIST.IGNORE"
            char_info["base"]["cv"] = "CV.IGNORE"

    artist_dict["IGNORE"] = {
        "eng": "",
        "engAlias": [],
        "jap": "",
        "japAlias": [],
    }

    tag_dict["IGNORE"] = {
        "name": "",
        "aliases": [],
        "parents": []
    }

    cv_dict["IGNORE"] = {
        "eng": "",
        "engAlias": [],
        "jap": "",
        "japAlias": [],
    }



    output_path = "data\scripts\data"
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    output = os.path.join(output_path, 'meta.js')
    with open(output, 'w', encoding="utf-8") as f:
        meta = f"var ARTIST = {json.dumps(artist_dict, ensure_ascii=False, indent=2)}\n\nvar CV = {json.dumps(cv_dict, ensure_ascii=False, indent=2)}\n\n" \
               f"var TAG = {json.dumps(tag_dict, ensure_ascii=False, indent=2)}\n\n" \
               f"var CHAR = {json.dumps(char_dict, ensure_ascii=False, indent=2)}\n\nvar SCENE = {json.dumps(scene_dict, ensure_ascii=False, indent=2)}"
        meta = re.sub(r'"ARTIST\.(.*?)"', r'ARTIST.\1', meta)
        meta = re.sub(r'"CV\.(.*?)"', r'CV.\1', meta)
        meta = re.sub(r'"CHAR\.(.*?)"', r'CHAR.\1', meta)
        meta = re.sub(r'"(.*?)":', r'\1:', meta)
        f.write(meta)
        print("meta.js已修复完毕！")

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
    request = urllib.request.Request(url,data=data,headers=headers)
    html = ""
    session = requests.Session()
    retry = Retry(total=100,
                  backoff_factor=0.1,
                  status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retry))
    session.mount('https://', HTTPAdapter(max_retries=retry))

    try:
        response = session.get(url, headers=headers, timeout=20)
        html = response.text
        return html
    except:
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

# 爬取页面
def getData(baseurl):
    html = askURL(baseurl)  # 保存获取到的网页源码
    bs = BeautifulSoup(html, "html.parser")

    listOne = bs.select('table.sortable.wikitable > tbody', limit=1)  # 查找id为“sortable wikitable”的table标签的
                                                                    #子标签————tbody,同时只找到第一个，因为第二个tbody的id相同
    idList = []

    for item in listOne:
        listTwo = item.select('tr')[2:]  # 跳过数组的前两个元素
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(process_item, item1)
                       for item1 in listTwo]
            for future in futures:

                id = future.result()

                if id:
                    idList.append(id)

        idList = list(idList)
        data_id_list = get_scene_ids()

        newList = []
        for data in data_id_list:
            for id in idList:
                if(data == id["id"]) or (data - 300000 == id["id"]):
                    newDict = {}
                    if data > 300000:
                        newDict['id'] = data
                    else:
                        newDict['id'] = id['id']
                    newDict['name'] = id['name']
                    newDict['engName'] = id['engName']
                    newList.append(newDict)


        print(idList)

        dataObj = {}
        dataObj["charaData"] = newList

        file_name = "data.json"
        # 文件路径
        file_path = file_name

        with open(file_path, 'w', encoding="utf-8") as fp:
            fp.write(json.dumps(dataObj, indent=2, ensure_ascii=False))



def process_item(item1):
    listThr = item1.findAll('td')[1:5]  # 只查找第二和第三个元素

    print(listThr[1])
    dict = {}
    try:
        dict['id'] = int(listThr[0].get_text())
        dict['name'] = listThr[1].select("td > a")[0].get_text()
        dict['engName'] = listThr[2].select("td > a")[0].get_text()
    except IndexError:
        print(listThr[0].get_text() + "-" + "表格格式异常！")
        return None
    return dict

def main():
    baseurl = "https://flowerknight.fandom.com/wiki/List_of_Flower_Knights_by_ID"

    # 将时间间隔转换为天数
    YOUR_TIME_INTERVAL = 30  # 7天

    # 将时间间隔转换为秒
    time_interval_in_seconds = YOUR_TIME_INTERVAL * 24 * 60 * 60

    # 检查文件是否存在
    if os.path.isfile("data.json"):
        # 如果文件存在，则获取文件的修改时间
        file_time = os.path.getmtime("data.json")
        # 获取当前时间
        current_time = time.time()
        # 计算文件的年龄（以秒为单位）
        file_age = current_time - file_time
        # 如果文件的年龄超过指定时间，则重新获取数据
        if file_age > time_interval_in_seconds:
            getData(baseurl)
    else:
        # 如果文件不存在，则重新获取
        getData(baseurl)

    generate_meta()

    input("按下Enter键退出...")

if __name__ == "__main__":
    main()
