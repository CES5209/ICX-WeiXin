#这是相机标定代码，用于产生相机标定参数

# -*- coding: utf-8 -*-
import cv2
import numpy as np
import glob

# ================= 1. 需要你修改的参数 =================
# 棋盘格内角点数量 (列数, 行数) -> 注意是数"内部十字交叉点"的个数，不是数方块！
CHECKERBOARD = (9, 6) 
# 单个方块的真实物理边长 (毫米)
SQUARE_SIZE = 24.0      
# 存放你拍的标定照片的文件夹路径 (支持通配符)
IMAGE_PATH = 'calibration/images/*.jpg'  
# =======================================================

# 设置寻找亚像素角点的迭代终止条件
criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

# 准备真实世界中的 3D 坐标点 (0,0,0), (25,0,0), (50,0,0) ...
# 注意：我们假定标定板放在 Z=0 的平面上
objp = np.zeros((CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)
objp[:, :2] = np.mgrid[0:CHECKERBOARD[0], 0:CHECKERBOARD[1]].T.reshape(-1, 2) * SQUARE_SIZE

# 用来存放所有图片的 3D 坐标点和对应的 2D 像素点
objpoints = [] # 真实世界中的 3D 点
imgpoints = [] # 图像中的 2D 像素点

# 读取所有图片
images = glob.glob(IMAGE_PATH)
if not images:
    print("未找到任何图片，请检查 IMAGE_PATH 路径！")
    exit()

print(f"共找到 {len(images)} 张图片，开始提取角点...")

# 遍历每一张图片
for fname in images:
    img = cv2.imread(fname)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 寻找棋盘格内角点
    # ret 是一个布尔值，代表是否成功找到了所有的角点
    ret, corners = cv2.findChessboardCorners(gray, CHECKERBOARD, None)
    
    # 如果找到了，就添加到数组中
    if ret == True:
        objpoints.append(objp)
        
        # 提高角点检测的精确度到亚像素级别
        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        imgpoints.append(corners2)
        
        # (可选) 在图片上画出角点并显示，按任意键看下一张
        # cv2.drawChessboardCorners(img, CHECKERBOARD, corners2, ret)
        # cv2.imshow('img', img)
        # cv2.waitKey(500)
        print(f"成功提取: {fname}")
    else:
        print(f"提取失败 (未找到完整棋盘格): {fname}")

cv2.destroyAllWindows()

# ================= 2. 开始核心标定计算 =================
print("\n正在计算相机内参和畸变系数，请稍候...")
ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, gray.shape[::-1], None, None)

print("\n========== 标定结果 ==========")
print("1. 相机内参矩阵 (Camera Matrix):")
print(mtx)
print("\n2. 畸变系数 (Distortion Coefficients):")
print(dist)

# 保存标定结果，供后续树莓派上的识别代码读取
np.savez("camera_calibration_data.npz", mtx=mtx, dist=dist)
print("\n已将参数保存到 camera_calibration_data.npz")