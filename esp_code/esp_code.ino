#include <WiFi.h>
#include <WebServer.h>
#include <FastLED.h>
#include <ArduinoJson.h>
#include "esp_wpa2.h"

// ---------------- LED CONFIG ----------------
#define STRIP_LEDS 7
#define TUBE_LEDS 8

#define LED1 4
#define LED2 17
#define LED3 5
#define LED4 16

#define STRIP1_PIN 14
#define STRIP2_PIN 27
#define STRIP3_PIN 26
#define STRIP4_PIN 25

#define BUZZER 18
#define TUBE_PIN 19
#define FAN_PIN 33

CRGB strip1[STRIP_LEDS];
CRGB strip2[STRIP_LEDS];
CRGB strip3[STRIP_LEDS];
CRGB strip4[STRIP_LEDS];
CRGB tube[TUBE_LEDS];

CRGB* strips[4] = {strip1, strip2, strip3, strip4};
int ledPins[4] = {LED1, LED2, LED3, LED4};

WebServer server(8100);

// ---------------- WIFI ----------------
const char* ssid1 = "IIIT-Guest";
const char* pass1 = "f6s68VHJ89mC";

const char* ssid2 = "wifi@iiith";
const char* username = "sasidhar.varada@research.iiit.ac.in";
const char* password2 = "Sasi#$802";

// ---------------- MODE ----------------
enum Mode { DEMO, MANUAL };
Mode systemMode = DEMO;

unsigned long lastCommandTime = 0;
const unsigned long MANUAL_TIMEOUT = 300000; // 5 min

// ---------------- DEMO ----------------
unsigned long lastDemoUpdate = 0;
int demoStep = 0;
int currentStrip = 0;

unsigned long actuatorStart = 0;
bool actuatorActive = false;
int activeActuator = -1;

// ---------------- STATES ----------------
enum State {IDLE, ANIMATING};
State stripState[4] = {IDLE, IDLE, IDLE, IDLE};
int snakePos[4] = {0};

unsigned long lastUpdate = 0;
int moveSpeed = 120;

// ---------------- DEVICES ----------------
int buzzer_mode = 0;
bool tube_state = 0;
CRGB tubeColor = CRGB::White;
int fan_speed = 0;

// ---------------- WIFI CONNECT ----------------
void connectWiFi()
{
  WiFi.disconnect(true);
  WiFi.mode(WIFI_STA);

  Serial.println("Trying IIIT-Guest...");
  WiFi.begin(ssid1, pass1);

  int attempt = 0;
  while (WiFi.status() != WL_CONNECTED && attempt < 20)
  {
    delay(500);
    Serial.print(".");
    attempt++;
  }

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("\nConnected to IIIT-Guest");
    Serial.println(WiFi.localIP());
    return;
  }

  Serial.println("\nFallback to WPA2 Enterprise...");

  WiFi.disconnect(true);
  delay(1000);

  esp_wifi_sta_wpa2_ent_enable();
  esp_wifi_sta_wpa2_ent_set_identity((uint8_t *)username, strlen(username));
  esp_wifi_sta_wpa2_ent_set_username((uint8_t *)username, strlen(username));
  esp_wifi_sta_wpa2_ent_set_password((uint8_t *)password2, strlen(password2));

  WiFi.begin(ssid2);

  attempt = 0;
  while (WiFi.status() != WL_CONNECTED && attempt < 40)
  {
    delay(500);
    Serial.print("#");
    attempt++;
  }

  if (WiFi.status() == WL_CONNECTED)
  {
    Serial.println("\nConnected to WPA2 Enterprise");
    Serial.println(WiFi.localIP());
  }
  else
  {
    Serial.println("\nWiFi Failed → Running Demo Mode");
  }
}

// ---------------- SNAKE ----------------
void gradientSnake(CRGB *strip, int &pos)
{
  fill_solid(strip, STRIP_LEDS, CRGB::Black);

  int i = STRIP_LEDS - 1 - pos;

  if(i>=0 && i<STRIP_LEDS) strip[i] = CRGB(0,0,255);
  if(i+1<STRIP_LEDS) strip[i+1] = CRGB(0,0,180);
  if(i+2<STRIP_LEDS) strip[i+2] = CRGB(0,0,100);

  pos++;

  if(pos > STRIP_LEDS + 2)
    pos = 0;
}

// ---------------- DEMO ----------------
void runDemo()
{
  if(millis() - lastDemoUpdate < 2000) return;
  lastDemoUpdate = millis();

  currentStrip = random(0,4);
  stripState[currentStrip] = ANIMATING;
  snakePos[currentStrip] = 0;

  demoStep++;

  // every 3 cycles → ONLY tube + fan
  if(demoStep % 3 == 0 && !actuatorActive)
  {
    activeActuator = random(0,2); // 0 = tube, 1 = fan

    actuatorActive = true;
    actuatorStart = millis();

    if(activeActuator == 0)
    {
      tube_state = 1;
    }
    else if(activeActuator == 1)
    {
      fan_speed = 200;
    }
  }
}

void handleActuatorTimeout()
{
  if(actuatorActive && millis() - actuatorStart > 5000)
  {
    actuatorActive = false;

    buzzer_mode = 0;
    tube_state = 0;
    fan_speed = 0;
  }
}

// ---------------- BUZZER ----------------
void buzzerControl()
{
  if(buzzer_mode == 0)
  {
    noTone(BUZZER);
    return;
  }

  tone(BUZZER, 2000);
}

// ---------------- HTTP ----------------
void handleData()
{
  String body = server.arg("plain");

  StaticJsonDocument<200> doc;

  if(deserializeJson(doc, body))
  {
    server.send(400,"text/plain","JSON ERROR");
    return;
  }

  JsonArray arr = doc["cmd"];

  if(arr.size() < 8)
  {
    server.send(400,"text/plain","INVALID");
    return;
  }

  systemMode = MANUAL;
  lastCommandTime = millis();

  for(int i=0;i<4;i++)
  {
    if(arr[i]==1)
    {
      stripState[i] = ANIMATING;
      snakePos[i] = 0;
      digitalWrite(ledPins[i], LOW);
    }
    else
    {
      stripState[i] = IDLE;
      fill_solid(strips[i], STRIP_LEDS, CRGB::Black);
      digitalWrite(ledPins[i], HIGH);
    }
  }

  buzzer_mode = arr[4];
  tube_state  = arr[5];

  JsonArray rgb = arr[6];
  tubeColor = CRGB(rgb[0], rgb[1], rgb[2]);

  fan_speed = arr[7];

  server.send(200,"text/plain","OK");
}

// ---------------- SETUP ----------------
void setup()
{
  Serial.begin(115200);

  for(int i=0;i<4;i++)
  {
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], HIGH);
  }

  pinMode(BUZZER, OUTPUT);

  ledcAttach(FAN_PIN,1000,8);

  connectWiFi();

  FastLED.addLeds<WS2812B,STRIP1_PIN,GRB>(strip1,STRIP_LEDS);
  FastLED.addLeds<WS2812B,STRIP2_PIN,GRB>(strip2,STRIP_LEDS);
  FastLED.addLeds<WS2812B,STRIP3_PIN,GRB>(strip3,STRIP_LEDS);
  FastLED.addLeds<WS2812B,STRIP4_PIN,GRB>(strip4,STRIP_LEDS);
  FastLED.addLeds<WS2812B,TUBE_PIN,GRB>(tube,TUBE_LEDS);

  server.on("/data",HTTP_POST,handleData);
  server.begin();
}

// ---------------- LOOP ----------------
void loop()
{
  server.handleClient();

  // WiFi auto-reconnect
  if(WiFi.status() != WL_CONNECTED)
  {
    static unsigned long lastRetry = 0;
    if(millis() - lastRetry > 10000)
    {
      lastRetry = millis();
      connectWiFi();
    }
  }

  // fallback after 5 min
  if(systemMode == MANUAL && millis() - lastCommandTime > MANUAL_TIMEOUT)
  {
    systemMode = DEMO;

    // reset system cleanly
    buzzer_mode = 0;
    tube_state = 0;
    fan_speed = 0;
  }

  if(systemMode == DEMO)
  {
    runDemo();
    handleActuatorTimeout();
  }

  // animation engine
  if(millis() - lastUpdate > moveSpeed)
  {
    lastUpdate = millis();

    for(int i=0;i<4;i++)
    {
      if(stripState[i] == ANIMATING)
      {
        gradientSnake(strips[i], snakePos[i]);

        if(snakePos[i] == 0)
        {
          stripState[i] = IDLE;
          digitalWrite(ledPins[i], HIGH);
        }
      }
    }

    FastLED.show();
  }

  // tube
  fill_solid(tube, TUBE_LEDS, tube_state ? tubeColor : CRGB::Black);

  // buzzer
  buzzerControl();

  // fan
  ledcWrite(FAN_PIN, fan_speed);