/*
  Speed alarm + LED speed display for the SDR Doppler radar - Arduino Nano.

  Receives lines from 02_doppler_radar.py over USB serial (115200 baud):
      S<speed km/h>,P<proximity 0-100>,V<volume 0-100>,L<last speed km/h, -1 = none>
  e.g. "S45.2,P70,V75,L38.0"

  Buzzer behaviour:
    - volume (PWM duty cycle)  follows speed     -> faster target = louder
    - pitch                    follows speed     -> faster target = higher tone
    - beep rate (1..10 /s)     follows proximity -> closer target = faster beeps
    - silent when no target, or when no data arrives for 0.5 s

  LED display (TM1637, 4 digits):
    - live speed while a target is passing
    - holds the LAST measured speed after it has passed
    - "----" until the first pass

  Wiring:
    Buzzer (D9 is fixed: it is Timer1's PWM output OC1A)
      D9 --[1k]--> NPN base (2N2222 / BC547)
      NPN emitter --> GND
      NPN collector --> buzzer (-)
      buzzer (+) --> 5V
    TM1637 display
      CLK --> D2
      DIO --> D3
      VCC --> 5V
      GND --> GND

  Library: "TM1637" by Avishay Orpaz (Arduino IDE -> Tools -> Manage Libraries)
*/

#include <TM1637Display.h>

const uint8_t BUZZER_PIN = 9;
const uint8_t DISP_CLK = 2;
const uint8_t DISP_DIO = 3;
const uint8_t LED_PIN = LED_BUILTIN;   // on-board LED blinks with the beeps
const unsigned long TIMEOUT_MS = 500;

TM1637Display display(DISP_CLK, DISP_DIO);
const uint8_t DASHES[] = {SEG_G, SEG_G, SEG_G, SEG_G};

float speedKmh = 0;
float lastKmh = -1;  // -1 = no pass yet
int proximity = 0;   // 0..100
int volume = 0;      // 0..100

char line[40];
uint8_t lineLen = 0;
unsigned long lastMsgMs = 0;
int shown = -2;      // value currently on the display (avoids redundant writes)

// Timer1 fast PWM on D9: frequency = pitch, duty cycle = loudness
void buzzerOn(float pitchHz, int vol) {
  uint16_t top = (uint16_t)(2000000.0 / pitchHz) - 1;   // 16 MHz / prescaler 8
  float duty = 0.02 + 0.48 * vol / 100.0;               // 2 % (quiet) .. 50 % (loudest)
  ICR1 = top;
  OCR1A = (uint16_t)(top * duty);
  if (TCNT1 > top) TCNT1 = 0;                           // pitch dropped mid-cycle: avoid counting to 65535
  TCCR1A = _BV(COM1A1) | _BV(WGM11);
  TCCR1B = _BV(WGM13) | _BV(WGM12) | _BV(CS11);
}

void buzzerOff() {
  TCCR1A = 0;
  TCCR1B = 0;
  digitalWrite(BUZZER_PIN, LOW);
}

// Show a speed rounded to whole km/h, or dashes for a negative value
void showSpeed(float kmh) {
  int value = kmh < 0 ? -1 : (int)(kmh + 0.5);
  if (value == shown) return;
  shown = value;
  if (value < 0) display.setSegments(DASHES);
  else display.showNumberDec(min(value, 9999), false);
}

// Parse "S45.2,P70,V75,L38.0"
void parseLine(char *s) {
  for (char *tok = strtok(s, ","); tok; tok = strtok(NULL, ",")) {
    if (tok[0] == 'S') speedKmh = atof(tok + 1);
    else if (tok[0] == 'P') proximity = constrain(atoi(tok + 1), 0, 100);
    else if (tok[0] == 'V') volume = constrain(atoi(tok + 1), 0, 100);
    else if (tok[0] == 'L') lastKmh = atof(tok + 1);
  }
  lastMsgMs = millis();
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      line[lineLen] = '\0';
      parseLine(line);
      lineLen = 0;
    } else if (c != '\r' && lineLen < sizeof(line) - 1) {
      line[lineLen++] = c;
    }
  }
}

void setup() {
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  buzzerOff();
  Serial.begin(115200);

  display.setBrightness(7);       // 0..7
  display.showNumberDec(8888);    // display test
  buzzerOn(1000, 60);             // start-up chirp: buzzer wired correctly
  delay(300);
  buzzerOff();
  showSpeed(-1);
}

void loop() {
  readSerial();

  bool active = volume > 0 && proximity > 0 && millis() - lastMsgMs < TIMEOUT_MS;

  // Display: live speed during a pass, otherwise hold the last speed
  showSpeed(active ? speedKmh : lastKmh);

  if (!active) {
    buzzerOff();
    digitalWrite(LED_PIN, LOW);
    return;
  }

  float beepsPerSec = 1.0 + 9.0 * proximity / 100.0;
  unsigned long period = (unsigned long)(1000.0 / beepsPerSec);
  bool beepOn = (millis() % period) < period / 2;      // 50 % on / off

  if (beepOn) {
    float pitch = 600.0 + 6.0 * volume;                 // 600 Hz .. 1200 Hz
    buzzerOn(pitch, volume);
    digitalWrite(LED_PIN, HIGH);
  } else {
    buzzerOff();
    digitalWrite(LED_PIN, LOW);
  }
}
