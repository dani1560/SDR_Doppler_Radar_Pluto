/*
  Speed alarm + LED speed display for the SDR Doppler radar - Arduino Nano.

  Receives lines from 02_doppler_radar.py over USB serial (115200 baud):
      S<speed km/h>,P<proximity 0-100>,V<volume 0-100>,L<last speed km/h, -1 = none>,F<1 = last pass over limit>
  e.g. "S45.2,P70,V75,L38.0,F0"

  Buzzer behaviour:
    - volume (PWM duty cycle)  follows speed     -> faster target = louder
    - pitch                    follows speed     -> faster target = higher tone
    - beep rate (1..10 /s)     follows proximity -> closer target = faster beeps
    - silent when no target, or when no data arrives for 0.5 s

  LED display (TM1637, 4 digits), speed with one decimal:
    - modules with decimal points (HAS_DOTS = true): " 45.3", "123.4"
    - colon-only modules (HAS_DOTS = false): whole km/h, "  45"; with COLON_AS_POINT = true
      the colon is used as the decimal point, "45:3"
    - live speed while a target is passing
    - holds the LAST measured speed (peak of the pass) after it has passed
    - every new captured speed blinks for 5 s, then stays steady
    - keeps blinking if that pass was over the speed limit
    - "----" until the first pass
    Start-up test lights all segments, colon and dots: "88:88" means a colon module.

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
const unsigned long NEW_PASS_BLINK_MS = 5000;   // a new captured speed blinks this long
const bool HAS_DOTS = false;           // true for modules with decimal points, false for colon-only modules
const bool COLON_AS_POINT = false;     // colon-only modules: true = "45:3", false = whole km/h "  45"
const uint8_t DOT_000_0 = 0b00100000;  // decimal point after the 3rd digit
const uint8_t COLON = 0b10000000;      // colon modules: this bit of the 2nd digit lights the colon
const int BLANK = -2;                  // showTenths(): -1 = dashes, -2 = blank

TM1637Display display(DISP_CLK, DISP_DIO);
const uint8_t DASHES[] = {SEG_G, SEG_G, SEG_G, SEG_G};

float speedKmh = 0;
float lastKmh = -1;     // -1 = no pass yet
bool overLimit = false; // last pass was over the speed limit
float heldKmh = -1;     // last speed already noticed, to detect a new pass
unsigned long blinkUntilMs = 0;
int proximity = 0;      // 0..100
int volume = 0;         // 0..100

char line[48];
uint8_t lineLen = 0;
unsigned long lastMsgMs = 0;
int shown = -3;         // value currently on the display (avoids redundant writes)

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

// Speed in km/h -> tenths of km/h (45.3 -> 453), -1 for "no speed"
int toTenths(float kmh) {
  return kmh < 0 ? -1 : (int)min(kmh * 10 + 0.5, 9999.0);
}

// Colon module: "45:3" with the colon as decimal point (digits 1-2 whole km/h, digit 3 tenths)
void showColonDecimal(int value) {
  int whole = value / 10;
  uint8_t seg[4] = {0, 0, 0, 0};
  if (whole >= 10) seg[0] = display.encodeDigit(whole / 10);
  seg[1] = display.encodeDigit(whole % 10) | COLON;
  seg[2] = display.encodeDigit(value % 10);
  display.setSegments(seg);
}

// Show tenths of km/h as "45:3" / "45.3", dashes for -1, nothing for BLANK
void showTenths(int value) {
  if (value == shown) return;
  shown = value;
  if (value == BLANK) display.clear();
  else if (value < 0) display.setSegments(DASHES);
  else if (HAS_DOTS) display.showNumberDecEx(value, DOT_000_0, false);
  else if (COLON_AS_POINT && value < 1000) showColonDecimal(value);
  else display.showNumberDec((value + 5) / 10, false);   // whole km/h
}

// Parse "S45.2,P70,V75,L38.0,F0"
void parseLine(char *s) {
  for (char *tok = strtok(s, ","); tok; tok = strtok(NULL, ",")) {
    if (tok[0] == 'S') speedKmh = atof(tok + 1);
    else if (tok[0] == 'P') proximity = constrain(atoi(tok + 1), 0, 100);
    else if (tok[0] == 'V') volume = constrain(atoi(tok + 1), 0, 100);
    else if (tok[0] == 'L') lastKmh = atof(tok + 1);
    else if (tok[0] == 'F') overLimit = atoi(tok + 1) != 0;
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
  display.showNumberDecEx(8888, 0b11100000);  // display test: "8.8.8.8." (or "88:88" on colon modules)
  buzzerOn(1000, 60);             // start-up chirp: buzzer wired correctly
  delay(1000);
  buzzerOff();
  showTenths(-1);
}

void loop() {
  readSerial();

  bool active = volume > 0 && proximity > 0 && millis() - lastMsgMs < TIMEOUT_MS;

  // A new captured speed arrived: blink it for NEW_PASS_BLINK_MS
  if (lastKmh != heldKmh) {
    heldKmh = lastKmh;
    if (lastKmh >= 0) blinkUntilMs = millis() + NEW_PASS_BLINK_MS;
  }
  bool blinking = lastKmh >= 0 && (overLimit || millis() < blinkUntilMs);

  // Display: live speed during a pass, otherwise hold the last speed (blinking when new or over the limit)
  if (active) showTenths(toTenths(speedKmh));
  else if (blinking && (millis() / 250) % 2) showTenths(BLANK);
  else showTenths(toTenths(lastKmh));

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
