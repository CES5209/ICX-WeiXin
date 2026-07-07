# 本代码手动部分测试无误，自动部分由于输入信号格式问题无法测试
# -*- coding: utf-8 -*-
import argparse
import os
import sys
import time
from threading import Thread
import queue
import cv2
import serial  # Ensure installed via: pip install pyserial
import json
from ultralytics import YOLO  # Import YOLOv8

class VideoStream:
    def __init__(self, src=0, resolution=(640, 480)):
        self.stream = cv2.VideoCapture(src)
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH,  resolution[0])
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        self.grabbed, self.frame = self.stream.read()
        self.stopped = False

    def start(self):
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


# ======================== ESP32 串口监听线程（自动触发） ========================
def esp32_serial_listener(port, baud, state_dict):
    print(f"\n[SERIAL ACTIVE] Listening to ESP32 on {port} at {baud} (Safe JSON Mode)...")
    try:
        ser = serial.Serial(port, baud, timeout=1)
        ser.flushInput()
        
        while not state_dict['exit_program']:
            if ser.in_waiting > 0:
                try:
                    raw_data = ser.readline()
                    line = raw_data.decode('utf-8', errors='replace').strip()
                    
                    if u'\ufffd' in line or not line: 
                        continue
                        
                    data = json.loads(line)
                    
                    if isinstance(data, dict):
                        is_trigger = data.get("flag", False)# 默认为false
                        distance = data.get("dist", "N/A")
                    elif isinstance(data, (bool, int, float)):
                        is_trigger = bool(data)
                        distance = "N/A" 
                    else:
                        is_trigger = False
                        distance = "N/A"
                    
                    # 仅联动自动控制阀门
                    if is_trigger != state_dict['auto_capturing']:
                        state_dict['auto_capturing'] = is_trigger
                        status_str = "AUTO_START" if is_trigger else "AUTO_END"
                        print(f"\n[ESP32 SIGNAL] {status_str} | Front Distance: {distance}cm")
                        
                        # 综合决策：手动或自动有一个满足，即代表正在捕获中
                        state_dict['is_capturing'] = state_dict['manual_capturing'] or state_dict['auto_capturing']
                            
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    print(f"Serial parse error: {e}")
                    
            time.sleep(0.01)
    except Exception as e:
        print(f"\nERROR: Failed to open serial port {port}. {e}")


# ======================== SSH 输入监听线程（手动触发） ========================
def ssh_input_listener(state_dict):
    print("\n[SSH MODE ACTIVE]")
    print(" -> Press '1' + Enter to manual START/END AI capture period.")
    print(" -> Press 'q' + Enter to QUIT program.\n")
    while True:
        user_input = input().strip().lower()
        if user_input == '1':
            # 仅取反手动阀门
            state_dict['manual_capturing'] = not state_dict['manual_capturing']
            # 综合更新最终捕捉状态
            state_dict['is_capturing'] = state_dict['manual_capturing'] or state_dict['auto_capturing']
            
            status = "OPEN" if state_dict['manual_capturing'] else "CLOSED"
            print(f"[MANUAL TRIGGER] --> Manual Window {status} | Global Capturing State: {state_dict['is_capturing']}")
        elif user_input == 'q':
            state_dict['exit_program'] = True
            break


# ======================== AI 推理工作线程 ========================
def ai_inference_worker(ai_task_queue, model, save_dir):
    print("[AI WORKER] Dedicated YOLO inference thread started.")
    
    while True:
        task = ai_task_queue.get()
        if task is None:  
            ai_task_queue.task_done()
            break
            
        timestamp_str, frames_to_process = task
        print(f"\n[AI WORKER] Processing Batch [{timestamp_str}] with {len(frames_to_process)} frames...")
        
        period_scores = {}
        best_frame_info = {"conf": 0.0, "frame": None, "label": "Unknown"}
        
        # 批量进行 YOLO 预测
        for cached_frame in frames_to_process:
            results = model(cached_frame, verbose=True, conf=0.3, imgsz=320)
            
            if len(results[0].boxes) > 0:
                for box in results[0].boxes:
                    class_id = int(box.cls[0].item())
                    label_name = model.names[class_id] 
                    confidence = float(box.conf[0].item())
                    
                    if label_name not in period_scores:
                        period_scores[label_name] = []
                    period_scores[label_name].append(confidence)
                    
                    if confidence > best_frame_info["conf"]:
                        best_frame_info["conf"] = confidence
                        best_frame_info["frame"] = results[0].plot()
                        best_frame_info["label"] = label_name

        # 批量权重决策与保存
        if period_scores:
            final_winner = None
            max_total_score = -1.0
            
            print(f"\n------------------ [REPORT FOR BATCH {timestamp_str}] ------------------")
            for label, conf_list in period_scores.items():
                avg_conf = sum(conf_list) / len(conf_list)
                frequency = len(conf_list)
                total_score = avg_conf * frequency 
                
                print(f" [Item ID: {label}] | Frequency: {frequency}/{len(frames_to_process)} frames | Avg Conf: {avg_conf:.4f} | Total Score: {total_score:.4f}")
                
                if total_score > max_total_score:
                    max_total_score = total_score
                    final_winner = label
            print("-------------------------------------------------------------------------")
            
            print(f"[DECISION RESULT] Batch {timestamp_str} Winner: {final_winner}")
            
            if best_frame_info["frame"] is not None:
                filename = f"Final_{final_winner}_{timestamp_str}.jpg"
                path = os.path.join(save_dir, filename)
                cv2.imwrite(path, best_frame_info["frame"])
                print(f"[SAVED] Saved to: {filename}\n")
        else:
            print(f"[DECISION RESULT] Batch {timestamp_str} failed. YOLO detected nothing.")
            if frames_to_process:
                filename = f"NoAI_Unrecognized_{timestamp_str}.jpg"
                path = os.path.join(save_dir, filename)
                cv2.imwrite(path, frames_to_process[0])
                print(f"[BAILOUT SAVED] Saved raw frame to: {filename}\n")
            
        ai_task_queue.task_done()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=int, default=0, help="Camera index")
    parser.add_argument("--save_interval", type=float, default=0.1, help="Frame snapshot interval (seconds)") 
    parser.add_argument("--save_dir", default="/home/weixin/Pictures/", help="Directory to save photos")
    parser.add_argument("--no_preview", action="store_true", help="Run without GUI preview")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port connected to ESP32")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    args = parser.parse_args()

    os.makedirs(args.save_dir, exist_ok=True)

    print("Loading Custom YOLOv8 model (weixin)...")
    model = YOLO("/home/weixin/Desktop/best.pt")
    print("Model loaded successfully!")

    # 1. 先启动摄像头流
    print("Initializing camera stream...")
    vs = VideoStream(src=args.src).start()
    
    # 【核心修改点】：循环等待相机就绪，最多等待 4 秒，防止因多线程调度导致一刀切报错
    camera_ready = False
    for i in range(20): # 20 * 0.2秒 = 4秒
        time.sleep(0.2)
        if vs.read() is not None:
            camera_ready = True
            break
        if i % 5 == 0:
            print(f"Waiting for camera to warm up... ({i*0.2:.1f}s)")

    if not camera_ready:
        print("ERROR: Cannot read camera. Check connection or try running with 'libcamerify'")
        vs.stop()
        return
        
    print("Camera stream initialized successfully!")

    # 分离并优化控制状态结构
    control_state = {
        'manual_capturing': False, # 手动强制抓拍状态
        'auto_capturing': False,   # ESP32自动感应状态
        'is_capturing': False,     # 综合决策状态
        'exit_program': False
    }

    # 实例化并启动 AI 队列线程
    ai_task_queue = queue.Queue()
    Thread(target=ai_inference_worker, args=(ai_task_queue, model, args.save_dir), daemon=True).start()

    # 启动 ESP32 串口自动监听线程
    Thread(target=esp32_serial_listener, args=(args.port, args.baud, control_state), daemon=True).start()

    if args.no_preview:
        Thread(target=ssh_input_listener, args=(control_state,), daemon=True).start()
    else:
        print("\n[GUI WINDOW MODE ACTIVE]")
        print(" -> Click the camera window, press [SPACE] to manual START/END period.")
        print(" -> Press [Q] to QUIT.\n")

    last_save_time = 0
    in_period_snapshot = False  
    frame_queue = []

    try:
        while not control_state['exit_program']:
            frame = vs.read()
            if frame is None:
                continue

            if not args.no_preview:
                cv2.imshow("Smart Camera Control (YOLOv8 aggregated)", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord(' '):  
                    # 针对 GUI 键盘空格事件，仅联动手动阀门
                    control_state['manual_capturing'] = not control_state['manual_capturing']
                    control_state['is_capturing'] = control_state['manual_capturing'] or control_state['auto_capturing']
                    status = "START" if control_state['manual_capturing'] else "PAUSE"
                    print(f"[KEY TRIGGER] Manual Capture Window: {status} | Global: {control_state['is_capturing']}")
                elif key == ord('q'):
                    break

            # ======================== PHASE 1: 开始图像帧入队缓存 ========================
            if control_state['is_capturing']:
                if not in_period_snapshot:
                    print("\n[INFO] ===>> Window opened. Caching frames...")
                    frame_queue.clear()
                    in_period_snapshot = True

                now = time.time()
                if now - last_save_time >= args.save_interval:
                    frame_queue.append(frame.copy())
                    last_save_time = now

            # ======================== PHASE 2: 窗口关闭，打包并交付 AI 线程 ========================
            elif not control_state['is_capturing'] and in_period_snapshot:
                ts = time.strftime("%Y%m%d_%H%M%S")
                print(f"\n[INFO] <<=== Window closed. Packaged {len(frame_queue)} frames. Handover to AI Worker.")
                
                if frame_queue:
                    ai_task_queue.put((ts, list(frame_queue)))
                
                frame_queue.clear()
                in_period_snapshot = False 
                
            else:
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    finally:
        print("Cleaning up...")
        control_state['exit_program'] = True
        ai_task_queue.put(None)  
        vs.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()