#该程序用来在pc端控制摄像头拍照，并生成去畸变后的图片，检验标定结果
import cv2
import numpy as np
import os
from datetime import datetime

# ================= 配置 =================
# 摄像头索引，外接摄像头通常是 1
CAMERA_INDEX = 1
# 标定数据文件路径
CALIBRATION_FILE = 'calibration/camera_calibration_data.npz'
# 修正后照片输出目录
OUTPUT_DIR = 'calibration/test_output'
# ========================================

def main():
    # 1. 检查标定文件是否存在并加载参数
    if not os.path.exists(CALIBRATION_FILE):
        print(f"找不到标定文件: {CALIBRATION_FILE}")
        print("请先运行标定程序生成 camera_calibration_data.npz！")
        return
        
    print("正在加载标定参数...")
    with np.load(CALIBRATION_FILE) as data:
        mtx = data['mtx']
        dist = data['dist']
        
    print("相机内参 (mtx):")
    print(mtx)
    print("畸变系数 (dist):")
    print(dist)

    # 2. 确保输出目录存在
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"已创建输出目录: {OUTPUT_DIR}")

    # 3. 初始化摄像头
    print(f"正在尝试打开摄像头 (ID: {CAMERA_INDEX})...")
    cap = cv2.VideoCapture(CAMERA_INDEX)
    
    if not cap.isOpened():
        print(f"无法打开摄像头 {CAMERA_INDEX}，请检查连接或尝试更改 CAMERA_INDEX。")
        return

    print("摄像头已开。")
    print("按 'q' 键拍照并保存修正后的图片，按 'ESC' 键退出。")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("无法获取画面，退出。")
            break

        # 在窗口中显示实时预览（未修正画面，以便于取景）
        cv2.imshow("Camera Preview (Original)", frame)

        # 监听按键输入，等待 1 毫秒
        key = cv2.waitKey(1) & 0xFF
        
        # 按 'q' 拍照
        if key == ord('q'):
            print("正在处理并保存照片...")
            
            # 使用获取的画面宽和高去获取更优化的内参矩阵（可选，用于裁剪黑边）
            # h,  w = frame.shape[:2]
            # newcameramtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w,h), 1, (w,h))
            # undistorted = cv2.undistort(frame, mtx, dist, None, newcameramtx)
            
            # 直接使用原始参数去畸变
            undistorted = cv2.undistort(frame, mtx, dist, None, mtx)
            
            # 生成带时间戳的文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"undistorted_{timestamp}.jpg"
            save_path = os.path.join(OUTPUT_DIR, filename)
            
            # 保存修正后的图片
            cv2.imwrite(save_path, undistorted)
            print(f"已保存修正后的照片: {save_path}")
            
            # 也可以短暂显示一下修正后的图片
            cv2.imshow("Captured & Undistorted", undistorted)
            
        # 按 ESC ( ASCII 码 27) 退出
        elif key == 27:
            print("正在退出...")
            break

    # 释放资源
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()