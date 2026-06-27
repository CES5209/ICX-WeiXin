import os
import shutil

# 路径配置
current_dir = os.path.dirname(os.path.abspath(__file__))
datas_dir = os.path.join(current_dir, "datas")
labels_dir = os.path.join(current_dir, "labels")
images_dir = os.path.join(current_dir, "images")

# 创建 images 文件夹
os.makedirs(images_dir, exist_ok=True)

print("正在扫描所有原图...")
# 1. 扫描 datas 底下所有的原始图片（无重名，直接建立一一对应字典）
origin_pics = {}
for root, dirs, files in os.walk(datas_dir):
    for f in files:
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            origin_pics[f] = os.path.join(root, f)

print(f"共找到 {len(origin_pics)} 张原图。正在进行匹配...")

# 2. 遍历 labels 里面的标注文件
label_files = [f for f in os.listdir(labels_dir) if f.endswith('.txt') and f != 'classes.txt']

success_count = 0
for label_file in label_files:
    # 例如：哈希值-IMG01.txt -> 提取 "哈希值-IMG01"
    base_name = label_file[:-4] 
    
    matched = False
    for origin_name, origin_path in origin_pics.items():
        # 原名：IMG01.jpg -> 提取 "IMG01"
        origin_base = os.path.splitext(origin_name)[0]
        
        # 只要标注文件名带有原图片名，说明匹配成功
        # (考虑到有时LS导出格式可能是 Hash-name.jpg.txt，所以增加对全名origin_name的判定)
        if base_name.endswith(origin_base) or base_name.endswith(origin_name):
            source_ext = os.path.splitext(origin_name)[1]
            
            # 为了确保与 txt 名字完全一致，新文件名必须也是哈希开头
            target_img_name = base_name if base_name.endswith(source_ext) else base_name + source_ext
            target_path = os.path.join(images_dir, target_img_name)
            
            # 复制过去
            shutil.copy2(origin_path, target_path)
            success_count += 1
            matched = True
            
            # 找到就结束当前txt的内层循环，节约时间
            break

    if not matched:
        print(f"⚠️ 找不到对应的原图: {label_file}")

print(f"\n✅ 搞定！干净利落地合并了 {success_count} 张照片。")
