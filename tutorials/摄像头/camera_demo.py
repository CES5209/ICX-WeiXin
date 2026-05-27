import argparse
import os
import time
from threading import Thread

import cv2


class VideoStream:
    def __init__(self, src=0, resolution=(640, 480)):
        # src=0 表示系统里第 0 号摄像头（默认那个）
        self.stream = cv2.VideoCapture(src)
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH,  resolution[0])
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        # 先读一帧当作初始画面，避免 self.frame 一开始是 None
        self.grabbed, self.frame = self.stream.read()
        self.stopped = False

    def start(self):
        # daemon=True：主程序退出时线程自动结束
        Thread(target=self._update, daemon=True).start()
        return self

    def _update(self):
        while not self.stopped:
            self.grabbed, self.frame = self.stream.read()
        self.stream.release()

    def read(self):
        return self.frame

    def stop(self):
        self.stopped = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=int, default=0, help="摄像头编号，默认 0 号")
    parser.add_argument("--save_interval", type=float, default=0.2, help="自动保存照片的时间间隔")
    parser.add_argument("--save_dir", default="photos", help="保存照片的目录")
    parser.add_argument("--no_preview", action="store_true", help="无桌面环境（如远程 SSH 树莓派）时加这个")
    args = parser.parse_args()

    os.makedirs(args.save_dir, exist_ok=True)

    # 启动摄像头，留 1 秒热身
    vs = VideoStream(src=args.src).start()
    time.sleep(1.0)

    if vs.read() is None:
        print("无法读取摄像头，检查是否插好/被别的程序占用")
        vs.stop()
        return

    print("按 q 退出，程序会按固定时间间隔自动保存照片")

    last_save_time = 0

    while True:
        frame = vs.read()
        if frame is None:
            continue

        if not args.no_preview:
            cv2.imshow("camera_demo", frame)

        now = time.time()

        if now - last_save_time >= args.save_interval:
            ts = time.strftime("%Y%m%d_%H%M%S")

            filename = "img_{}.jpg".format(ts)
            path = os.path.join(args.save_dir, filename)
            cv2.imwrite(path, frame)

            last_save_time = now

        # waitKey(1)：等 1ms 同时取键盘事件；& 0xFF 兼容跨平台
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break

    vs.stop()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
