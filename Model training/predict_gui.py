"""
YOLO 图片检测脚本
------------------
使用 Model training\best.pt 权重文件，
从电脑中选择图片，显示 YOLO 检测结果。
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO


# ==================== 配置 ====================

# 类别名称（与 train_yolo.py 中的 names 一致）
CLASS_NAMES = [
    '人工智能学院',
    '信步科技',
    '医学院',
    '机械与动力工程学院',
    '电子信息与电气工程学院',
    '电气工程学院',
    '自动化与感知学院',
    '计算机学院',
    '集成电路学院',
]

# 权重文件路径（与脚本同目录）
SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_PATH = SCRIPT_DIR / 'best.pt'

# 为每个类别分配固定颜色（BGR 格式，用于 OpenCV）
COLORS = [
    (0, 0, 255),      # 红
    (0, 255, 0),      # 绿
    (255, 0, 0),      # 蓝
    (0, 255, 255),    # 黄
    (255, 0, 255),    # 品红
    (255, 255, 0),    # 青
    (128, 0, 255),    # 紫
    (0, 128, 255),    # 橙
    (255, 128, 0),    # 天蓝
]

# 中文字体路径（Windows 常用字体，按优先级尝试）
CANDIDATE_FONTS = [
    'C:/Windows/Fonts/msyh.ttc',   # 微软雅黑
    'C:/Windows/Fonts/simhei.ttf', # 黑体
    'C:/Windows/Fonts/simsun.ttc',  # 宋体
    'C:/Windows/Fonts/msyhbd.ttc',  # 微软雅黑粗体
]


# ==================== 工具函数 ====================

def find_chinese_font(font_size: int = 24) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """查找可用的中文字体，返回 PIL ImageFont 对象。"""
    for font_path in CANDIDATE_FONTS:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, font_size)
            except Exception:
                continue
    print("⚠️ 未找到中文字体，将使用默认字体（中文可能显示为方块）")
    return ImageFont.load_default()


def load_model(model_path: Path) -> YOLO:
    """加载 YOLO 模型。"""
    if not model_path.exists():
        print(f"❌ 找不到权重文件: {model_path}")
        print("   请确保 best.pt 与本脚本在同一目录下。")
        sys.exit(1)
    print(f"✅ 正在加载模型: {model_path}")
    model = YOLO(str(model_path))
    class_count = len(model.names)
    print(f"   模型加载完成！类别数: {class_count}")
    # 模型自带训练时的类别名称，无需覆盖
    return model


def open_image_dialog() -> str | None:
    """弹出文件选择窗口，返回用户选择的图片路径。"""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    file_path = filedialog.askopenfilename(
        title='选择一张图片进行检测',
        filetypes=[
            ('图片文件', '*.jpg *.jpeg *.png *.bmp *.webp'),
            ('JPEG', '*.jpg *.jpeg'),
            ('PNG', '*.png'),
            ('BMP', '*.bmp'),
            ('所有文件', '*.*'),
        ],
    )
    root.destroy()
    return file_path if file_path else None


def print_detection_results(results) -> None:
    """在终端打印检测详情。"""
    found_any = False
    for result in results:
        if result.boxes is None:
            continue
        boxes = result.boxes.xyxy.cpu().numpy().astype(int)
        confs = result.boxes.conf.cpu().numpy()
        clss  = result.boxes.cls.cpu().numpy().astype(int)

        for box, conf, cls_id in zip(boxes, confs, clss):
            found_any = True
            class_name = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f'Class {cls_id}'
            x1, y1, x2, y2 = box
            print(f'  📦 {class_name:<12s}  置信度: {conf:.4f}  位置: [{x1}, {y1}, {x2}, {y2}]')

    if not found_any:
        print('  (未检测到任何目标)')


def draw_results_on_image(image_bgr: np.ndarray, results, font: ImageFont.FreeTypeFont) -> np.ndarray:
    """
    将检测结果绘制到图像上。
    使用 PIL 绘制中文标签，再合成为 OpenCV 图像。
    """
    img = image_bgr.copy()
    h, w = img.shape[:2]

    # 转成 PIL Image（RGB 格式）
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_img)

    for result in results:
        if result.boxes is None:
            continue
        boxes = result.boxes.xyxy.cpu().numpy().astype(int)
        confs = result.boxes.conf.cpu().numpy()
        clss  = result.boxes.cls.cpu().numpy().astype(int)

        line_width = max(2, int(min(w, h) * 0.005))

        for box, conf, cls_id in zip(boxes, confs, clss):
            x1, y1, x2, y2 = box
            class_name = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f'Class {cls_id}'
            color_rgb = COLORS[cls_id % len(COLORS)][::-1]  # BGR -> RGB

            label = f'{class_name} {conf:.2f}'

            # 绘制边界框
            draw.rectangle([x1, y1, x2, y2], outline=color_rgb, width=line_width)

            # 计算标签背景尺寸
            bbox = draw.textbbox((0, 0), label, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            # 标签位置：框上方；超出图片则放框内顶部
            label_y = y1 - text_h - 6
            if label_y < 0:
                label_y = y1 + 2

            # 背景矩形
            draw.rectangle(
                [x1, label_y, x1 + text_w + 4, label_y + text_h + 4],
                fill=color_rgb,
            )
            # 白字
            draw.text((x1 + 2, label_y + 2), label, font=font, fill=(255, 255, 255))

    # 转回 OpenCV BGR
    result_np = np.array(pil_img)
    result_bgr = cv2.cvtColor(result_np, cv2.COLOR_RGB2BGR)
    return result_bgr


# ==================== 主流程 ====================

def main():
    print('=' * 60)
    print('  YOLO 图片检测工具')
    print('=' * 60)

    model = load_model(MODEL_PATH)
    font = find_chinese_font(font_size=28)

    print()
    print('📷 即将弹出文件选择窗口，请选择一张图片...')
    print('   按 ESC 键关闭检测结果窗口')
    print()

    while True:
        image_path = open_image_dialog()
        if image_path is None:
            print('🚪 未选择图片，退出程序。')
            break

        print(f'📷 检测图片: {image_path}')

        image_bgr = cv2.imread(image_path)
        if image_bgr is None:
            print(f'❌ 无法读取图片: {image_path}')
            continue

        print('🔍 正在进行检测...')
        results = model.predict(
            source=image_bgr,
            conf=0.25,
            iou=0.45,
            verbose=False,
        )

        print('📊 检测结果:')
        print_detection_results(results)

        result_img = draw_results_on_image(image_bgr, results, font)

        # 自适应窗口大小
        screen_h = 900
        img_h, img_w = result_img.shape[:2]
        if img_h > screen_h:
            scale = screen_h / img_h
            new_w = int(img_w * scale)
            result_img = cv2.resize(result_img, (new_w, screen_h))

        cv2.namedWindow('YOLO Detection (Press ESC to close)', cv2.WINDOW_NORMAL)
        cv2.imshow('YOLO Detection (Press ESC to close)', result_img)

        print('   按 ESC 关闭图片窗口，然后选择下一张图片...')
        key = cv2.waitKey(0) & 0xFF
        cv2.destroyAllWindows()

        if key == 27:  # ESC
            print('🚪 ESC 被按下，退出程序。')
            break

        print()
        print('--- 继续选择下一张图片 ---')
        print()

    cv2.destroyAllWindows()
    print('✅ 程序结束。')


if __name__ == '__main__':
    main()
