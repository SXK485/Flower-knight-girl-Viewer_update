import json
import os
import re

# 用于正则匹配的scenes文件夹的目录
scenes_path = 'scenes'
# 译好后的json文件位于的目录
output_path = 'json_cn'
# json转回txt后保存的目录
# translated_path = 'translated'
translated_path = 'scenes'

# 使用正则表达式匹配<NAME_PLATE><PAUSE>对话标签对
pattern = r'<NAME_PLATE>(.*?)<PAUSE>'
# 文本替换模板，用于将原文替换成译文
replacement_template = '{name}\n{message}\n'


# 解析scenes文件夹下角色对应的script.txt文件，找出所有对话标签对
def parse_script(file_path):
    with open(file_path, encoding='utf-8') as f:
        lines = f.read()
        matches = re.findall(pattern, lines, re.DOTALL)
        return matches


# 将json文件中的译文替换到script.txt文件的标签对中，返回替换后的文本
def replace_script(file_path, translations):
    with open(file_path, encoding='utf-8') as f:
        content = f.read()

    for translation in translations:
        name = translation.get('name', '')
        message = translation['message']
        # 格式化字符串，将译文填充至对话标签对
        replacement = replacement_template.format(name=name, message=message)
        # 使用replace方法，将原文替换成原文
        content = content.replace(translation['original'], replacement)

    return content


def main():
    if not os.path.exists(translated_path):
        os.makedirs(translated_path)

    # 遍历scenes_path文件夹
    for filename in os.listdir(scenes_path):
        # 用于正则匹配的script.txt文件的路径
        file_path = os.path.join(scenes_path, filename, 'script.txt')

        if os.path.exists(file_path):
            # 用文件夹名称作为角色ID
            id = filename

            # 译好后的json文件的路径
            json_path = os.path.join(output_path, id + '_script.json')

            if os.path.isfile(json_path) and os.path.isfile(file_path):
                # 解析scenes文件夹下角色对应的script.txt文件，找出所有对话标签对
                translations = parse_script(file_path)
                # 获取json文件获取json数据
                with open(json_path, encoding='utf-8') as f:
                    json_data = json.load(f)

                # 定义一个列表，用于保存拥有原文本和译文信息的字典
                merged_translations = []
                # 循环对话标签对，将原文和json对象中的译文保存到字典中
                for i, translation in enumerate(translations):
                    merged_translation = {
                        'original': translation,
                        'name': json_data[i].get('name', ''),
                        # 将换行符\\n替换为\n，使播放器能够正常显示文本
                        'message': json_data[i]['message'].replace('\n', '\\n')
                    }
                    merged_translations.append(merged_translation)

                # 将json文件中的译文替换到script.txt文件的标签对中，返回替换后的文本
                translated_content = replace_script(file_path, merged_translations)

                # 将替换好的文本保存到指定路径(可以直接覆盖原来的script.txt)
                os.makedirs(os.path.dirname(translated_path + '/' + id + '/script.txt'), exist_ok=True)
                with open(translated_path + '/' + id + '/script.txt', 'w', encoding='utf-8') as f:
                    f.write(translated_content)
                    print(translated_path + '/' + id + '/script.txt'+"替换完成！")


if __name__ == '__main__':
    main()