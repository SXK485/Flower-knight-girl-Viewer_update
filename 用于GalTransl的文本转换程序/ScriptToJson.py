import json
import os
import re

# 选择scenes文件夹作为剧本数据来源
# scenes_path = 'E:\さいきん\Flower\package.nw\scenes'
scenes_path = 'scenes'
# 转成json后保存的目录
output_path = 'json_jp'

# 使用正则表达式匹配<NAME_PLATE><PAUSE>对话标签对
pattern = r'<NAME_PLATE>(.*?)<PAUSE>'

# 解析script.txt，转换成json数据
def parse_script(file_path):
    # 创建空列表用于保存json对象
    data = []

    with open(file_path, encoding='utf-8') as f:
        lines = f.read()

        # 使用findall方法返回与pattern匹配的字符串，使用re.DOTALL参数，匹配字符串时忽略换行符
        for m in re.findall(pattern, lines, re.DOTALL):

            # 通过换行符分割姓名(如果有)与对话文本
            parts = m.split("\n")
            name = parts[0].strip()

            message = parts[1].strip()

            # 定义json对象
            json_obj ={}

            # 如果存在姓名，则添加姓名属性
            if name != "":
                json_obj['name'] = name
            # 保存对话文本
            json_obj['message'] = message

            # 将json对象添加到列表
            data.append(json_obj)

    return data


def main():
    # 创建输出目录
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    # 遍历scenes文件夹，获取每个角色的script.txt文件的路径
    for filename in os.listdir(scenes_path):

        file_path = os.path.join(scenes_path, filename, 'script.txt')

        if os.path.exists(file_path):
            # 用文件夹名称作为角色ID
            id = filename
            # 解析script.txt，转换成json数据
            data = parse_script(file_path)

            # 保存json数据，文件命名为"(文件夹名称) + '_script.json'"
            output = os.path.join(output_path, id + '_script.json')
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                print(output + "已生成")


if __name__ == '__main__':
    main()