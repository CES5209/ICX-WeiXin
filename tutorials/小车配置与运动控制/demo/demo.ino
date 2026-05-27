#include <Arduino.h>
#include <RPLidar.h>
#include "MecanumDriver.h"


// =========================
// 串口监视开关
// =========================
#define DEBUG_SERIAL 1 // 1启用串口监视，0关闭

#if DEBUG_SERIAL
#define DBG_BEGIN(baud) Serial.begin(baud)
#define DBG_PRINT(x) Serial.print(x)
#define DBG_PRINTLN(x) Serial.println(x)
#else
#define DBG_BEGIN(baud)
#define DBG_PRINT(x)
#define DBG_PRINTLN(x)
#endif


// =========================
// 电机引脚
// =========================
#define MOTOR1_PIN1 9
#define MOTOR1_PIN2 8
#define MOTOR2_PIN1 12
#define MOTOR2_PIN2 13
#define MOTOR3_PIN1 11
#define MOTOR3_PIN2 10
#define MOTOR4_PIN1 46
#define MOTOR4_PIN2 21


// =========================
// 参数设置
// =========================
// 例：const int FORWARD_SPEED = 200;



// =========================
// 对象创建
// =========================
RPLidar lidar;
MecanumDriver mecanum(
  MOTOR1_PIN1, MOTOR1_PIN2,
  MOTOR2_PIN1, MOTOR2_PIN2,
  MOTOR3_PIN1, MOTOR3_PIN2,
  MOTOR4_PIN1, MOTOR4_PIN2
);


// =========================
// 变量创建
// =========================
float lidarDistances[360] = {0};


// =========================
// 函数声明（示例）
// =========================
void setSpeed(float speedX, float speedY, float angularW);
void forward(float speed);
void back(float speed);
void left(float speed);
void right(float speed);
void turnLeft(float speed);
void turnRight(float speed);
void stopCar();


// =========================
// 函数实现（示例）
// =========================
void setSpeed(float speedX, float speedY, float angularW) {
  float wheelFL = speedX + speedY - angularW;
  float wheelFR = speedX - speedY + angularW;
  float wheelBL = speedX - speedY - angularW;
  float wheelBR = speedX + speedY + angularW;

  mecanum.driveAllMotor(
    constrain(wheelFL, -255, 255),
    constrain(wheelFR, -255, 255),
    constrain(wheelBL, -255, 255),
    constrain(wheelBR, -255, 255)
  );
}

// 前进
void forward(float speed) {
  setSpeed(speed, 0, 0);
}

// 后退
void back(float speed) {
  setSpeed(-speed, 0, 0);
}

// 左横移
void left(float speed) {
  setSpeed(0, -speed, 0);
}

// 右横移
void right(float speed) {
  setSpeed(0, speed, 0);
}

// 原地左转
void turnLeft(float speed) {
  setSpeed(0, 0, -speed);
}

// 原地右转
void turnRight(float speed) {
  setSpeed(0, 0, speed);
}

// 停车
void stopCar() {
  setSpeed(0, 0, 0);
}


// =========================
// 主程序
// =========================
void setup() {
  DBG_BEGIN(115200);

  lidar.begin(Serial2);
  lidar.startScan();

  mecanum.begin();
}

void loop() {
  static unsigned long lastGoodLidarMs = 0;
  static unsigned long lastRestartLidarMs = 0;
  if (IS_OK(lidar.waitPoint())) {
    lastGoodLidarMs = millis();

    float dist = lidar.getCurrentPoint().distance; // 距离，单位 mm
    int angle = round(lidar.getCurrentPoint().angle);  // 扫描角度
    uint8_t quality = lidar.getCurrentPoint().quality; // 数据质量
    bool isNewScan = lidar.getCurrentPoint().startBit; // 是否进入新一圈扫描

    DBG_PRINT("dist:");
    DBG_PRINT(dist);
    DBG_PRINT(" angle:");
    DBG_PRINT(angle);
    DBG_PRINT(" quality:");
    DBG_PRINT(quality);
    DBG_PRINT(" newScan:");
    DBG_PRINTLN(isNewScan);

    if (angle >= 0 && angle < 360) {
      lidarDistances[angle] = dist;
    }

    if (isNewScan) {
      // 编写控制策略
      forward(150);
      delay(1000);
      left(150);
      delay(1000);
      turnLeft(150);
      delay(1000);
      stopCar();
      delay(1000);
    }
  }
  else {
    //重启雷达或其他自定义策略
    if (millis() - lastGoodLidarMs > 10000 && millis() - lastRestartLidarMs > 10000) {
      rplidar_response_device_info_t info;
      if (IS_OK(lidar.getDeviceInfo(info, 100))) {
        lidar.startScan();
      }
      lastRestartLidarMs = millis();
    }
  }
}
