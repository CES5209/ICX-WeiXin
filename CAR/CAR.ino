#include <RPLidar.h>
#include <MecanumDriver.h>
#include <Arduino.h>

// ======================== 调试开关 ========================
#define DEBUG_SERIAL 0
#if DEBUG_SERIAL
#define DBG_BEGIN(baud) Serial.begin(baud)
#define DBG_PRINT(x) Serial.print(x)
#define DBG_PRINTLN(x) Serial.println(x)
#else
#define DBG_BEGIN(baud)
#define DBG_PRINT(x)
#define DBG_PRINTLN(x)
#endif

// ======================== 硬件引脚定义 ========================
#define MOTOR1_PIN1 9
#define MOTOR1_PIN2 8
#define MOTOR2_PIN1 12
#define MOTOR2_PIN2 13
#define MOTOR3_PIN1 11
#define MOTOR3_PIN2 10
#define MOTOR4_PIN1 46
#define MOTOR4_PIN2 21

#define RPLIDAR_SERIAL Serial2
#define PI_SERIAL Serial
#define RPLIDAR_MOTOR  3

// ======================== 运动控制参数 ========================
#define SPEED_STRAIGHT     25
#define SPEED_TURN         15
#define SPEED_TURNAROUND   15

// ======================== 转弯控制参数 ========================
#define TURN_MIN_DURATION   600   // 转弯最小时长 (ms)
#define TURN_MAX_DURATION   900  // 转弯安全超时 (ms)
#define TURN_FRONT_BLOCKED  20    // 前方受阻阈值 (cm)，车头还对着墙

// ======================== 雷达距离阈值 (单位: cm) ========================
#define FRONT_OBSTACLE_TH  30    // 前方有障碍物阈值
#define FRONT_OPEN_TH      90    // 前方空旷阈值
#define SIDE_WALL_TH       20    // 侧向贴墙阈值
#define OPEN_AREA_TH       50    // 转向侧开阔区域阈值
#define SIDE_DIFF_TH       60    // T字路口左右距离差阈值（绝对值）
#define FRONT_PHOTO_TH     100   // 准备拍照前方阈值

// ======================== 卡死检测参数 ========================
#define STUCK_DELTA_TH     1.0f
#define STUCK_DURATION     500

// ======================== 角度扇区定义 (0° = 正前方) ========================
#define SECTOR_FRONT_START 170
#define SECTOR_FRONT_END   190
#define SECTOR_LEFT_START   70
#define SECTOR_LEFT_END    110
#define SECTOR_RIGHT_START 250
#define SECTOR_RIGHT_END   290
#define SECTOR_LEFT_FRONT_START  130
#define SECTOR_LEFT_FRONT_END    150
#define SECTOR_RIGHT_FRONT_START 210
#define SECTOR_RIGHT_FRONT_END   230

// ======================== 状态机 ========================
enum RobotState {
  STATE_STRAIGHT,
  STATE_TURN_LEFT,
  STATE_TURN_RIGHT,
  STATE_TURN_AROUND,
  STATE_STUCK_RECOVER,
  STATE_FINISH
};

enum TurnDirection {
  TURN_NONE,
  TURN_LEFT,
  TURN_RIGHT
};

// 路线规划: 去程每个路口的期望转向 (用户根据实际赛道修改)
const TurnDirection path_forward[] = {TURN_LEFT, TURN_LEFT, TURN_LEFT, TURN_LEFT, TURN_RIGHT, TURN_RIGHT, TURN_RIGHT, TURN_RIGHT};
const int path_length = 8;

// ======================== 全局变量 ========================
RPLidar lidar;
MecanumDriver mecanum(MOTOR1_PIN1, MOTOR1_PIN2,
                      MOTOR2_PIN1, MOTOR2_PIN2,
                      MOTOR3_PIN1, MOTOR3_PIN2,
                      MOTOR4_PIN1, MOTOR4_PIN2);

hw_timer_t *timer = NULL;
RobotState robotState = STATE_STRAIGHT;
int turnCount = 0;
int circle = 1;     // 1:去程, 2:返程

float lidarDistances[360];
float lastLidarDistances[360];
static unsigned long lastSectorUpdate = 0;
float frontDist = 0.0f;
float frontDistDel0 = 0.0f;
float leftDist = 0.0f;
float rightDist = 0.0f;
float leftFrontDist = 0.0f;
float rightFrontDist = 0.0f;
float lrerror = 0.0f;
float flfrerror = 0.0f;

unsigned long turnConditionStartTime = 0;
bool turnConditionMet = false;
unsigned long lastGoodLidarMs = 0;
unsigned long turnStartTime = 0;
unsigned long stuckStartTime = 0;
unsigned long reverseStartTime = 0;
unsigned long adjustStartTime = 0;
int stuckRecoverStep = 0;
float prevFrontDist = 0.0f;
bool photoFlag = false;
unsigned long lastTurnExitTime = 0;
bool turnAroundFlag = false;
unsigned long turnAroundStartTime = 0;
bool frontBlocked = false;
bool stopFlag = false;

// ======================== 函数声明 ========================
void updateRadarData();
void setSpeed(float speedX, float speedY, float angularW);
void forward(float speed);
void turnLeft(float speed);
void turnRight(float speed);
void stopCar();
void doStraight();
void doTurnLeft();
void doTurnRight();
void doStuckRecover();
float getSectorAverageDistanceDelete0(int startAngle, int endAngle, int lastDist);
float getSectorAverageDistance(int startAngle, int endAngle, int lastDist);
bool isStuck();
void enterTurn(TurnDirection turn);
void exitTurn();
void handleIntersection();

// ======================== 运动控制 ========================
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

void forward(float speed) { setSpeed(speed, 0, 0); }
void turnLeft(float speed) { setSpeed(0, 0, speed); }
void turnRight(float speed) { setSpeed(0, 0, -speed); }
void moveLeft(float speed) { setSpeed(0, -speed, 0); }
void moveRight(float speed) { setSpeed(0, speed, 0); }
void stopCar() { setSpeed(0, 0, 0); }

// ======================== 雷达数据处理 ========================
void updateRadarData() {
  if (!lidar.isOpen()) return;
  int batchCount = 0;
  while (RPLIDAR_SERIAL.available() >= 5 && batchCount < 100 && IS_OK(lidar.waitPoint(1))) {
    lastGoodLidarMs = millis();
    float dist = lidar.getCurrentPoint().distance;
    float angle = lidar.getCurrentPoint().angle;
    int idx = (int)round(angle);
    if (idx >= 0 && idx < 360) lidarDistances[idx] = dist;
    batchCount++;
  }
  if (millis() - lastSectorUpdate > 50) {
    frontDist = getSectorAverageDistance(SECTOR_FRONT_START, SECTOR_FRONT_END, frontDist);
    frontDistDel0 = getSectorAverageDistanceDelete0(SECTOR_FRONT_START, SECTOR_FRONT_END, frontDistDel0);
    leftDist  = getSectorAverageDistanceDelete0(SECTOR_LEFT_START, SECTOR_LEFT_END, leftDist);
    rightDist = getSectorAverageDistanceDelete0(SECTOR_RIGHT_START, SECTOR_RIGHT_END,rightDist);
    leftFrontDist = getSectorAverageDistanceDelete0(SECTOR_LEFT_FRONT_START, SECTOR_LEFT_FRONT_END, leftFrontDist);
    rightFrontDist = getSectorAverageDistanceDelete0(SECTOR_RIGHT_FRONT_START, SECTOR_RIGHT_FRONT_END, rightFrontDist);
    lastSectorUpdate = millis();
    /*DBG_PRINT(" dixt:");
    DBG_PRINTLN(frontDist);
    DBG_PRINTLN(frontDistDel0);
    DBG_PRINTLN(rightDist);
    DBG_PRINTLN(leftDist);
    DBG_PRINT(" leftFront:"); DBG_PRINT(leftFrontDist);
    DBG_PRINT(" rightFront:"); DBG_PRINTLN(rightFrontDist);*/
  }
}

float getSectorAverageDistanceDelete0(int startAngle, int endAngle, int lastDist) {
  float sum = 0.0f;
  int count = 0;
  
  for (int a = startAngle; a <= endAngle; a++) {
    int idx = a % 360;
    if (idx < 0) idx += 360;
    float d = lidarDistances[idx];    // 单位: mm
    if (d != lastLidarDistances[idx] && d > 0 && d < 9999) {                   // 只累加有效距离
      sum += d;
      count++;
      lastLidarDistances[idx] = d;
    }
  }
  
  if (count == 0) {
    return lastDist;                     // 无有效数据
  }
  return (sum / count) / 10.0f * 0.6 + lastDist * 0.4;      // 平均 mm -> cm
}

float getSectorAverageDistance(int startAngle, int endAngle, int lastDist) {
  float sum = 0.0f;
  int count = 0;
  
  for (int a = startAngle; a <= endAngle; a++) {
    int idx = a % 360;
    if (idx < 0) idx += 360;
    float d = lidarDistances[idx];    // 单位: mm
    if (d < 9999) {                   // 只累加有效距离
      sum += d;
      count++;
    }
  }
  
  if (count == 0) {
    return 9999.0f;                     // 无有效数据
  }
  return (sum / count) / 10.0f;      // 平均 mm -> cm
}

// 向树莓派发送状态信息
void sendStatusToPi(float frontDist, bool flag) {
  PI_SERIAL.print("{\"dist\": ");
  PI_SERIAL.print(frontDist);
  PI_SERIAL.print(", \"flag\": ");
  PI_SERIAL.print(flag ? "true" : "false");
  PI_SERIAL.println("}");
  flag = false;
}

// ======================== 直线居中控制 ========================
void doStraight() {
  float linear = SPEED_STRAIGHT;
  if (turnAroundFlag && (millis() - lastTurnExitTime) > 2000)
  {
    turnAroundFlag = false;
    robotState = STATE_TURN_AROUND;
    turnAroundStartTime = millis();
  }
  else if(stopFlag && (millis() - lastTurnExitTime) > 1800)
  {
    stopFlag = false;
    robotState = STATE_FINISH;
  }
  lrerror = leftDist - rightDist;
  flfrerror = leftFrontDist - rightFrontDist;
  if (frontDistDel0 <= 60 || abs(lrerror) > 60){
    lrerror = 0;
    flfrerror = 0;
  }
  float angular = flfrerror * 0.1;
  angular = constrain(angular, -5, 5);
  float lateral = -lrerror * 0.25;
  lateral = constrain(lateral, -20.0f, 20.0f);
  if (frontDistDel0 < 60) {
    linear = SPEED_STRAIGHT * (frontDistDel0 / 80.0);
    linear = constrain(linear, 0, SPEED_STRAIGHT);
  } 
  setSpeed(linear, lateral, angular);
}

// ======================== 转向动作 ========================
void doTurnLeft() {
  unsigned long elapsed = millis() - turnStartTime;
  if (elapsed < TURN_MIN_DURATION){
    turnLeft(SPEED_TURN);
  }
  else if ((frontDistDel0 > FRONT_OPEN_TH) || (elapsed > TURN_MAX_DURATION)){
    exitTurn();
    return;
  }
  else {turnLeft(SPEED_TURN);}
}

void doTurnRight() {
  unsigned long elapsed = millis() - turnStartTime;
  if (elapsed < TURN_MIN_DURATION){
    turnRight(SPEED_TURN);
  }
  else if ((frontDistDel0 > FRONT_OPEN_TH) || (elapsed > TURN_MAX_DURATION)){
    exitTurn();
    return;
  }
  else {turnRight(SPEED_TURN);}
}

void enterTurn(TurnDirection turn) {
  turnConditionMet = false; 
  turnStartTime = millis();
  if (turn == TURN_LEFT) {
    robotState = STATE_TURN_LEFT;
  } else {
    robotState = STATE_TURN_RIGHT;
  }
}

void exitTurn() {
  turnCount++;
  lastTurnExitTime = millis();
  DBG_PRINTLN("turn exit");
  if (turnCount >= path_length) {
    if (circle == 1) {
      circle = 2;
      turnCount = 0;
      turnAroundFlag = true;
      DBG_PRINTLN(turnAroundFlag);
    } else {
      stopFlag = true;
    }
  }
  robotState = STATE_STRAIGHT;
  delay(200);
}

void doTurnAround() {
  turnRight(SPEED_TURNAROUND);
  if (!frontBlocked && frontDistDel0 < FRONT_OBSTACLE_TH) {
    frontBlocked = true;
  }
  if (frontBlocked && frontDistDel0 > FRONT_OPEN_TH || millis() - turnAroundStartTime > 2000) {
    frontBlocked = false;
    stopCar();
    delay(100);
    robotState = STATE_STRAIGHT;
  }
}
// ======================== 路口检测 ========================
void handleIntersection() {
  if (frontDist < FRONT_PHOTO_TH && (turnCount % 4 + 1) / 2 == 1) {
    if (!photoFlag){
      photoFlag = true;
      sendStatusToPi(frontDistDel0, photoFlag);
    }
  }
  else {photoFlag = false;}
  // 刚转完弯，2500ms 内不处理新路口
  if ((millis() - lastTurnExitTime) < 2500) {
    turnConditionMet = false; 
    setSpeed(SPEED_STRAIGHT, 0, 0);
    return;
  }
  // ---------- 判断是否满足转弯条件 ----------
  bool shouldTurn = false;
  TurnDirection target = TURN_NONE;
  TurnDirection expected = path_forward[turnCount];
  // 情况1：前方有障碍
  if (frontDistDel0 < FRONT_OBSTACLE_TH) {
    bool leftOpen = (leftDist > OPEN_AREA_TH);
    bool rightOpen = (rightDist > OPEN_AREA_TH);
    if (expected == TURN_LEFT && leftOpen) {
      shouldTurn = true;
      target = TURN_LEFT;
    } else if (expected == TURN_RIGHT && rightOpen) {
      shouldTurn = true;
      target = TURN_RIGHT;
    }
  }
  // 情况2：前方空旷但左右差距大（T字路口）
  else if (frontDistDel0 > FRONT_OPEN_TH) {
    float diff = fabs(leftDist - rightDist);
    if (diff > SIDE_DIFF_TH) {
      bool leftOpen = (leftDist > OPEN_AREA_TH);
      bool rightOpen = (rightDist > OPEN_AREA_TH);
      if (expected == TURN_LEFT && leftOpen) {
        shouldTurn = true;
        target = TURN_LEFT;
        DBG_PRINTLN("turn left");
      } else if (expected == TURN_RIGHT && rightOpen) {
        shouldTurn = true;
        target = TURN_RIGHT;
        DBG_PRINTLN("turn right");
      }
    }
  }
  // ---------- 延迟处理 ----------
  if (shouldTurn) {
    if (!turnConditionMet) {
      // 第一次检测到条件，开始计时
      turnConditionMet = true;
      turnConditionStartTime = millis();
    } else {
      // 已经计时，检查是否满 0.15 秒
      if (millis() - turnConditionStartTime >= 150) {
        // 执行转弯
        enterTurn(target);
        DBG_PRINTLN("turn enter");
        turnConditionMet = false;   // 复位
      }
    }
  } else {
    // 条件不满足，重置计时
    turnConditionMet = false;
  }
}

// ======================== 卡死检测与恢复 ========================
bool isStuck() {
  float delta = fabs(prevFrontDist - frontDist);
  if (delta > STUCK_DELTA_TH || frontDist > 20) {
    stuckStartTime = millis();
  } 
  prevFrontDist = frontDist;
  return (millis() - stuckStartTime >= STUCK_DURATION);
}

void doStuckRecover(){
  //先倒退一小段距离
  if (stuckRecoverStep == 1 && millis() - reverseStartTime <= 500)
  {
    setSpeed(-20, 0, 0);
  }
  else if (stuckRecoverStep == 1){
    adjustStartTime = millis();
    stuckRecoverStep = 2;
  }
  //小幅度修正车头
  if(stuckRecoverStep == 2 && millis() - adjustStartTime <= 500)
  {
    float adjustErr = leftFrontDist - rightFrontDist;
    adjustErr = constrain(adjustErr * 0.1, -15, 15);
    setSpeed(18, 0, adjustErr);
  }
  else if(stuckRecoverStep == 2){
    stuckRecoverStep = 0;
    robotState = STATE_STRAIGHT;
    lastTurnExitTime = millis();
  }
}

// ======================== 雷达初始化 ========================
void initRPLidar() {
  pinMode(RPLIDAR_MOTOR, OUTPUT);
  analogWrite(RPLIDAR_MOTOR, 0);
  lidar.begin(RPLIDAR_SERIAL);
  delay(500);
  rplidar_response_device_info_t info;
  if (IS_OK(lidar.getDeviceInfo(info, 200))) {
    lidar.startScan();
    analogWrite(RPLIDAR_MOTOR, 255);
    delay(1000);
  } else {
  }
}

// ======================== 主程序 ========================

void setup() {
  DBG_BEGIN(115200);
  DBG_PRINTLN("八字赛道小车启动 (支持T字路口)");
  for (int i = 0; i < 360; i++) {
    lidarDistances[i] = 9999.0f;
  }
  mecanum.begin();
  mecanum.setAllDirection(1, -1, 1, -1);
  lastTurnExitTime = 0;
  initRPLidar();
  for (int i = 0; i < 10; i++) {
    updateRadarData();
    delay(10);
  }
  robotState = STATE_STRAIGHT;
}

void loop() {
  updateRadarData();
  sendStatusToPi(frontDist, true);
  switch (robotState) {
    case STATE_STRAIGHT:
      if (isStuck()) {
        robotState = STATE_STUCK_RECOVER;
        DBG_PRINTLN("Stuck detected.");
        reverseStartTime = millis();
        stuckRecoverStep = 1;
        break;
      }
      handleIntersection();
      if (robotState == STATE_STRAIGHT){
        doStraight();
      }
      break;
    case STATE_TURN_LEFT:
      doTurnLeft();
      break;
    case STATE_TURN_RIGHT:
      doTurnRight();
      break;
    case STATE_TURN_AROUND:
      doTurnAround();
      break;
    case STATE_STUCK_RECOVER:
      doStuckRecover();
      break;
    case STATE_FINISH:
      stopCar();
      return;
  }
  //delay(10);
}
