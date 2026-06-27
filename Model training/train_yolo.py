import os
import shutil
import random
import yaml
from pathlib import Path
from ultralytics import YOLO

def prepare_dataset():
    # 1. 定义你的路径
    base_dir = Path(r"g:\files and docs\Projects\ICX\training")
    src_images = base_dir / "images"
    src_labels = base_dir / "labels"

    # 新的规范化数据集目录
    dataset_dir = base_dir / "dataset"
    split_dirs = ['train', 'val']

    # 2. 创建标准的 YOLO 数据集目录结构
    for split in split_dirs:
        (dataset_dir / split / 'images').mkdir(parents=True, exist_ok=True)
        (dataset_dir / split / 'labels').mkdir(parents=True, exist_ok=True)

    # 3. 自动划分验证集和训练集
    print("正在划分数据集...")
    all_images = [f for f in os.listdir(src_images) if f.endswith('.jpg')]
    random.shuffle(all_images) # 打乱顺序

    split_index = int(len(all_images) * 0.8) # 80% 训练, 20% 验证
    train_images = all_images[:split_index]
    val_images = all_images[split_index:]

    def copy_files(file_list, split_name):
        for img_name in file_list:
            label_name = img_name.replace('.jpg', '.txt')
            
            # 复制图片
            if (src_images / img_name).exists():
                shutil.copy(src_images / img_name, dataset_dir / split_name / 'images' / img_name)
            # 复制标注（即使是0字节的负样本也照常复制）
            if (src_labels / label_name).exists():
                shutil.copy(src_labels / label_name, dataset_dir / split_name / 'labels' / label_name)

    copy_files(train_images, 'train')
    copy_files(val_images, 'val')
    print(f"划分完成！训练集: {len(train_images)}张, 验证集: {len(val_images)}张")

    # 4. 自动生成 data.yaml
    yaml_path = dataset_dir / "data.yaml"
    data_config = {
        'path': str(dataset_dir.absolute()), # 使用绝对路径，防止路径识别错误
        'train': 'train/images',
        'val': 'val/images',
        'nc': 9,
        'names': [
            '人工智能学院', 
            '信步科技', 
            '医学院', 
            '机械与动力工程学院', 
            '电子信息与电气工程学院', 
            '电气工程学院', 
            '自动化与感知学院', 
            '计算机学院', 
            '集成电路学院'
        ]
    }

    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(data_config, f, allow_unicode=True)
    print(f"data.yaml 已生成在 {yaml_path}")
    
    return yaml_path

# 5. 开始使用 Python 训练 YOLO (这里以 YOLOv8n 为例)
if __name__ == '__main__':
    yaml_path = prepare_dataset()
    print("开始训练模型...")
    # 加载预训练模型 (自动下载针对轻量化设备的 nano 版本，适合树莓派部署)
    model = YOLO('yolov8n.pt') 
    
    # 启动训练
    results = model.train(
        data=str(yaml_path),
        epochs=100,      # 训练轮数 (可根据需要调到 200~300)
        imgsz=640,       # 输入图像大小
        batch=64,        # RTX 5070 配合 nano 模型，显存十分宽裕，可开大 batch 到 64 即便128也可以，加速训练
        device=0,        # 明确告诉程序使用第0张显卡(也就是你的RTX 5070)
        workers=8,       # 增加数据加载时的多线程数，防止显卡饿着等数据
        
        # --- 数据增强参数 (YOLOv8 默认是开启的，这里显式写出来方便你观察和调节) ---
        mosaic=1.0,      # 马赛克增强概率：将4张图强行拼成1张，非常利于教模型发现小目标 (YOLO特色，默认开启)
        mixup=0.0,       # 图像混合增强概率 (默认就是0)
        degrees=10.0,    # 图像随机旋转角度范围 (-10 到 10度)
        translate=0.1,   # 图像纵横向随机平移 10%
        scale=0.5,       # 图像随机缩放范围 (-50% 到 +50%)
        fliplr=0.5,      # 图像水平翻转概率！注意：如果你识别的图标有严格的方向性(比如文字不能反)，强烈建议改为 0.0！
        hsv_h=0.015,     # 色调抖动幅度
        hsv_s=0.7,       # 饱和度抖动幅度
        hsv_v=0.4,       # 亮度抖动幅度
        
        project='runs/train', # 训练结果保存目录
        name='yolov8_school_icons'
    )
    print("🎉 训练完成！权重文件保存在 runs/train/yolov8_school_icons/weights/best.pt")
