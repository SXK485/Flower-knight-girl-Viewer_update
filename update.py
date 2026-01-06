import sys
# 导入requests库，用于发送网络请求
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import threading
# 导入hashlib库，用于进行md5加密
import hashlib
# 导入zlib库，用于进行zlib解压缩
import zlib
# 导入os库，用于进行文件和目录操作
import os
import shutil
import time
import json
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from PIL import Image
import slpp

import logging

# 配置日志：同时输出到文件和控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("update_log.txt", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

qww = lambda x, y: True if x == y else False

# 定义一个常数，表示图片的前缀
IMAGE_PREFIX = "https://dugrqaqinbtcq.cloudfront.net/product/ynnFQcGDLfaUcGhp/assets/ultra/images/hscene_r18/"
# 定义一个常数，表示语音的前缀
VOICE_PREFIX = "https://dugrqaqinbtcq.cloudfront.net/product/ynnFQcGDLfaUcGhp/assets/voice/c/"
# 定义一个常数，表示剧本的前缀
SCRIPT_PREFIX = "https://dugrqaqinbtcq.cloudfront.net/product/ynnFQcGDLfaUcGhp/assets/event/hscene_r18/"
#定义一个常数，表示spine动画文件的前缀
URL_R18 = 'https://dugrqaqinbtcq.cloudfront.net/product/ynnFQcGDLfaUcGhp/assets/hscene_r18_spine/'
# scene folder
SCENE_PATH = "scenes"

def main():
    try:
        logger.info("Flower knight girl Viewer更新程序开始运行...")
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
                logger.info("differenceList.txt 已过期，尝试重新获取...")
                datalist = get_difference_list()
                if not datalist:
                    return
                # 将数据保存到文本文件中
                with open("differenceList.txt", "w") as f:
                    for item in datalist:
                        f.write(str(item) + "\n")
            else:
                logger.info("从本地加载 differenceList.txt")
                # 如果文件未过期，则读取文件并将其转换为整数列表
                with open("differenceList.txt", "r") as f:
                    datalist = [int(line.strip()) for line in f.readlines()]
        else:
            logger.info("未找到 differenceList.txt，开始从 Wiki 获取数据...")
            # 如果文件不存在，则重新获取
            datalist = get_difference_list()
            if not datalist:
                return
            # 将数据保存到文本文件中
            with open("differenceList.txt", "w") as f:
                for item in datalist:
                    f.write(str(item) + "\n")

        # datalist = [100011]
        if not datalist:
            logger.warning("未发现需要更新的角色数据。")
        else:
            logger.info(f"发现 {len(datalist)} 个新角色需要下载。")
            sub(datalist)

        logger.info("所有操作已完成！")

    except Exception as e:
        logger.error(f"程序运行发生致命错误: {str(e)}", exc_info=True)
        input("程序异常退出，请检查 update_log.txt 后按回车键结束...")

def sub(datalist):
    if not os.path.exists(SCENE_PATH):
        os.mkdir(SCENE_PATH)

    # 创建线程池
    executor = ThreadPoolExecutor(max_workers=10)  # 设置线程池的最大线程数

    # 提交任务到线程池
    results = []
    for id in datalist:
        future = executor.submit(download_role, id)
        results.append(future)

    # 等待所有任务完成
    for future in results:
        future.result()

    # 关闭线程池
    executor.shutdown()

    #获取sceneData.js
    get_sceneData()

    input("按下Enter键退出...")

def download_role(id):
    # 已知无场景的联动角色ID（转生史莱姆）
    exclude_list = [131807,134207,140829,154801]
    for i in exclude_list:
        if (id == i or id == i+2):
            return
    logger.info(f"线程启动：角色 ID {id}")

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
    folder_path = SCENE_PATH+"/"+folder_name
    # 创建资源文件夹
    if not os.path.exists(folder_path):
        os.mkdir(folder_path)
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
        None_H = download_image(image_url, image_file_name, folder_path + "/images", image_num)
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

    result = script_conversion(folder_path, folder_path + "/script_original.txt")
    is_spine = result[0]
    voice_num = result[1]
    voice_list = result[2]
    if is_spine == True:
        download_spine(str(id), folder_path, URL_R18)

    print("音频数量" + str(voice_num))
    voiceComplete = True;
    if voice_num != 0:
        # 遍历解析剧本得到的音频名称
        for voice_name in voice_list:
            # 使用md5加密语音的名称，并转换为16进制字符串
            voice_md5 = hashlib.md5(voice_name.encode()).hexdigest()
            # 拼接语音的url，使用前缀和角色id和加密后的字符串，并添加.mp3后缀
            voice_url = VOICE_PREFIX + str(id) + "/" + voice_md5 + ".mp3"
            # 拼接语音的文件名，使用资源文件夹名称和语音名称，并添加.mp3后缀
            voice_file_name = folder_path + "/voices/" + voice_name + ".mp3"
            if os.path.exists(folder_path + "/voices/" + voice_name + ".mp3"):
                print(voice_name + ".mp3"+"已存在!")
                continue
            # 调用函数，下载语音，并保存为mp3格式
            print(voice_name)
            voiceComplete = download_voice(voice_url, voice_file_name)

    # 打印完成信息
    if voiceComplete == False:
        logger.info(f"角色 ID {id} 资源文件夹已经生成完毕，请查看")
    return

# 定义一个函数，用于从数据结构中提取角色的id
def get_id_from_data():
    # folder_path = "E:\さいきん\Flower\kfg-viewer\public\scenes"
    folder_path = SCENE_PATH
    folder_names = []

    if os.path.exists(folder_path):
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


def get_difference_list():
    # 获取data.json中的数据
    url = "https://flowerknight.fandom.com/wiki/Module:MasterCharacterData?action=edit"
    lua_table = get_lua_table(url)
    data_list = filter_fields(lua_table)

    # 获取本地文件夹中的数据
    local_id_list = get_id_from_data()

    # 输出data_list的所有id
    data_id_list = [data['id'] for data in data_list]
    print("Data ID List:", data_id_list)

    # 输出local_id_list的所有id
    print("Local ID List:", local_id_list)

    # 找出ID差集，并保存
    differenceSet = set(data_id_list).difference(set(local_id_list))
    differenceList = list(differenceSet)
    print("Difference List:", differenceList)
    if differenceList:
        with open("differenceList.txt", "w") as f:
            for differenceID in differenceList:
                f.write(str(differenceID) + "\n")

    return differenceList

def get_lua_table(url):
    headers = requests.utils.default_headers()
    headers.update({
        'User-Agent': 'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
    })
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    # textarea = soup.find('textarea', {'id': 'wpTextbox1'})
    textarea = soup.select_one('#wpTextbox1')
    # none check
    if textarea is None:
        logger.error("无法在 Wiki 页面找到数据框 (#wpTextbox1)，可能是网络被屏蔽或 Wiki 结构已更新")
        return None
    lua_table_str = textarea.get_text()
    lua_table_str = lua_table_str.split('return ')[1]
    lua_table = slpp.SLPP().decode(lua_table_str)
    return lua_table

def filter_fields(lua_table):
    chara_data = []
    for key, value in lua_table.items():
        chara = {
            'id': value.get('id'),
            'name': value.get('name'),
            'reading': value.get('reading'),
            'rarity': value.get('rarity'),
            'tier3PowersOnlyBloom': value.get('tier3PowersOnlyBloom')
        }
        if chara['id'] < 700001:
            chara_data.append(chara)
        if chara['tier3PowersOnlyBloom'] == 0 and chara['id'] < 700001:
            charaBloomed = {
                'id': value.get('id') + 300000,
                'name': value.get('name'),
                'reading': value.get('reading'),
                'rarity': value.get('rarity'),
                'tier3PowersOnlyBloom': value.get('tier3PowersOnlyBloom')
            }
            chara_data.append(charaBloomed)
    return chara_data

#遍历scenes文件夹并输出sceneData.js
def get_sceneData():
    scenes_dir = SCENE_PATH
    scene_data = {}
    scene_data_name = "sceneData"

    # 遍历scenes文件夹
    count = 0
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

        count += 1

    logger.info(f"正在生成 sceneData.js，共计处理 {count} 个场景文件夹")

    output_path = 'data/scripts/data'
    if not os.path.exists(output_path):
        os.makedirs(output_path)
        logger.info(f"创建输出目录: {output_path}")

    # 输出sceneData.js
    scene_data_js = f"{scene_data_name} = {json.dumps(scene_data, indent=2, ensure_ascii=False)}"
    with open(f'data\scripts\data\{scene_data_name}.js', 'w', encoding='utf-8') as f:
        f.write(scene_data_js)
    logger.info("sceneData.js 已成功保存到 data/scripts/data/sceneData.js")

# 定义一个函数，用于下载图片，并保存为jpg格式
def download_image(url, file_name, image_path, image_num):

    # 获取路径下的文件数量
    file_count = len(os.listdir(image_path))

    # 判断文件数量是否与 image_num 相同
    if file_count == image_num:
        # 文件数量与 image_num 相同，说明文件已存在，直接返回，不进行下载
        return

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
                print(file_name+"-网络请求失败，请检查url是否正确:"+url+"\n", file=sys.stderr)
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
                    return False;
            else:
                # 打印错误信息
                print(file_name+"-网络请求失败，请检查url是否正确:"+url, file=sys.stderr)

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

    if os.path.exists(file_name):
        print(file_name+"已存在!\n")
        return

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
                try:
                    # 获取剧本的二进制数据，并进行zlib解压缩
                    script_data = zlib.decompress(response.content,wbits=15+32)
                    # 打开一个文件，以二进制写入模式
                    with open(file_name, "wb") as f:
                        # 将剧本的文本数据写入文件中
                        f.write(script_data)
                        # 关闭文件
                        f.close()
                        return
                except zlib.error:
                    logger.error(f"解压缩失败，文件可能损坏: {url}")
            else:
                # 打印错误信息
                logger.warning(f"下载失败 (HTTP {response.status_code}): {url}")

        except Exception as e:
            print(f"Download exception: {e}")

            if i == max_retries - 1:
                print(f"Failed after {max_retries} retries for {url}")
                return

            else:
                time.sleep(1)
                continue

def script_conversion(folder_path, script_original):


    if os.path.exists(folder_path+'/script.txt'):
        print(folder_path+'/script.txt'+"已存在!")
        # return None

    # 判断是否有动画
    is_spine = False
    voice_num = 0
    voice_list = []
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
                        # 拿音频名称
                        voice_list.append(parts[3].split('/')[1])
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
    with open(folder_path+'/script.txt', 'w', encoding='utf-8') as f:
        # 遍历转换后的每一行
        for line in new_lines:
            # 写入文件，并在每一行后面加上换行符
            f.write(line)
    return is_spine,voice_num,voice_list

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
            print('not found for '+id+': ' + str(i + 1), file=sys.stderr)


if __name__ == "__main__":
    main()