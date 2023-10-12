import os
import json

# 遍历scenes文件夹
# scenes_dir = 'E:\さいきん\Flower knight girl Viewer 1.0\package.nw\scenes'
scenes_dir = '.\scenes'
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
                "SCRIPT": open(os.path.join(scenes_dir, scene_folder, 'script.txt'), encoding='utf-8').read().split('\n'),
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
scene_data_js = f"sceneData = {json.dumps(scene_data, indent=2,ensure_ascii=False)}"
with open('.\sceneData.js', 'w', encoding='utf-8') as f:
    f.write(scene_data_js)

# with open('sceneData.js', 'w', encoding='utf-8') as f:
#     # 遍历转换后的每一行
#     for line in scene_data_js:
#         # 写入文件，并在每一行后面加上换行符
#         f.write(line)