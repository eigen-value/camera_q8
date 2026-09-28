/*
  Style Camera - MCU firmware (Arduino UNO Q)

  Peripherals : Modulino Buttons, SH1107 OLED (both on the Qwiic / Wire1 bus)
  Linux link  : Arduino_RouterBridge

  MCU -> Linux (Bridge.call)
    get_styles()          -> String   style names separated by '|'
    get_remaining_pics()  -> int      pictures left on the roll

  MCU -> Linux (Bridge.notify)
    take_picture()
    style_changed(int index, String name)

  Linux -> MCU (Bridge.provide)
    set_remaining_pics(int remaining) -> int
*/

#include <Arduino_RouterBridge.h>
#include <Arduino_Modulino.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SH110X.h>

// ---------------------------------------------------------------- Configuration
#define OLED_HEIGHT 64                 // 64 (128x64 module) or 128 (128x128 module)
constexpr uint8_t  OLED_ADDRESS   = 0x3C;
constexpr int      TOTAL_PICS     = 24;
constexpr char     BUTTON_STYLE   = 'A';
constexpr char     BUTTON_SHUTTER = 'C';
constexpr size_t   MAX_STYLES     = 16;
constexpr uint32_t LINK_RETRY_MS  = 1000;
constexpr uint32_t SHUTTER_LOCKOUT_MS = 400;

#define I2C_BUS Wire1

#if OLED_HEIGHT == 128
Adafruit_SH1107 display(128, 128, &I2C_BUS);
constexpr uint8_t OLED_ROTATION = 0;
#else
Adafruit_SH1107 display(64, 128, &I2C_BUS);
constexpr uint8_t OLED_ROTATION = 1;
#endif

ModulinoButtons buttons;

// ---------------------------------------------------------------- State
String  styleNames[MAX_STYLES];
size_t  styleCount = 0;
size_t  styleIndex = 0;
int     remaining  = 0;
volatile bool redrawRequested = false;

bool     stylePrev   = false;
bool     shutterPrev = false;
uint32_t lastShutter = 0;

// ---------------------------------------------------------------- Display helpers
int yOffset() { return (display.height() - 64) / 2; }

void showMessage(const String &text) {
  display.clearDisplay();
  display.setTextColor(SH110X_WHITE);
  display.setTextSize(1);
  int w = text.length() * 6;
  display.setCursor((display.width() - w) / 2, display.height() / 2 - 4);
  display.print(text);
  display.display();
}

void drawLogo() {
  const int size = 48;                      // logo height
  const int t    = size / 5;                // stroke thickness
  const int w    = (size * 3) / 5;          // logo width
  const int x0   = (display.width()  - w)    / 2;
  const int y0   = (display.height() - size) / 2;
  const int r    = t / 2;
  const int half = size / 2;

  struct Segment { int x, y, w, h; };
  const Segment segments[] = {
    { x0,         y0,                    w, t          },  // top bar
    { x0,         y0,                    t, half       },  // upper left stem
    { x0,         y0 + (size - t) / 2,   w, t          },  // middle bar
    { x0 + w - t, y0 + half,             t, size - half},  // lower right stem
    { x0,         y0 + size - t,         w, t          },  // bottom bar
  };

  display.clearDisplay();
  display.display();
  for (const Segment &s : segments) {
    display.fillRoundRect(s.x, s.y, s.w, s.h, r, SH110X_WHITE);
    display.display();
    delay(140);
  }
  delay(900);
}

void drawStatus() {
  const int yo = yOffset();
  const String rem = String(remaining);
  const String tot = "/" + String(TOTAL_PICS);
  const int remW = rem.length() * 24;       // size 4 glyph = 24 px wide
  const int totW = tot.length() * 12;       // size 2 glyph = 12 px wide
  const int x = (display.width() - (remW + totW)) / 2;

  display.clearDisplay();
  display.setTextColor(SH110X_WHITE);

  display.setTextSize(4);
  display.setCursor(x, yo + 2);
  display.print(rem);

  display.setTextSize(2);
  display.setCursor(x + remW, yo + 2 + 32 - 16);   // bottom-aligned with big digits
  display.print(tot);

  String name = styleCount > 0 ? styleNames[styleIndex] : String("no style");
  const uint8_t size = name.length() <= 10 ? 2 : 1;
  const size_t maxChars = display.width() / (6 * size);
  if (name.length() > maxChars) name = name.substring(0, maxChars);
  const int nameW = name.length() * 6 * size;

  display.setTextSize(size);
  display.setCursor((display.width() - nameW) / 2, yo + (size == 2 ? 44 : 48));
  display.print(name);

  display.display();
}

// ---------------------------------------------------------------- Bridge: Linux -> MCU
int setRemainingPics(int value) {
  remaining = constrain(value, 0, TOTAL_PICS);
  redrawRequested = true;
  return remaining;
}

// ---------------------------------------------------------------- Bridge: MCU -> Linux
void parseStyles(const String &list) {
  styleCount = 0;
  int start = 0;
  while (start <= (int)list.length() && styleCount < MAX_STYLES) {
    int end = list.indexOf('|', start);
    if (end < 0) end = list.length();
    String item = list.substring(start, end);
    item.trim();
    if (item.length() > 0) styleNames[styleCount++] = item;
    start = end + 1;
  }
  styleIndex = 0;
}

void syncWithLinux() {
  showMessage("Waiting for Linux...");

  String list;
  while (!(Bridge.call("get_styles").result(list) && list.length() > 0)) {
    delay(LINK_RETRY_MS);
  }
  parseStyles(list);

  int value = 0;
  while (!Bridge.call("get_remaining_pics").result(value)) {
    delay(LINK_RETRY_MS);
  }
  setRemainingPics(value);
}

// ---------------------------------------------------------------- Buttons
void nextStyle() {
  if (styleCount == 0) return;
  styleIndex = (styleIndex + 1) % styleCount;
  Bridge.notify("style_changed", (int)styleIndex, styleNames[styleIndex]);
  redrawRequested = true;
}

void shutter() {
  if (millis() - lastShutter < SHUTTER_LOCKOUT_MS) return;
  lastShutter = millis();

  if (remaining <= 0) {
    showMessage("Roll empty");
    delay(800);
    redrawRequested = true;
    return;
  }
  Bridge.notify("take_picture");
}

void pollButtons() {
  if (!buttons.update()) return;

  const bool styleNow   = buttons.isPressed(BUTTON_STYLE);
  const bool shutterNow = buttons.isPressed(BUTTON_SHUTTER);

  if (styleNow && !stylePrev)     nextStyle();
  if (shutterNow && !shutterPrev) shutter();

  stylePrev   = styleNow;
  shutterPrev = shutterNow;
}

// ---------------------------------------------------------------- Arduino entry points
void setup() {
  Bridge.begin();
  Bridge.provide_safe("set_remaining_pics", setRemainingPics);

  Modulino.begin(I2C_BUS);
  buttons.begin();
  buttons.setLeds(true, false, true);

  display.begin(OLED_ADDRESS, true);
  display.setRotation(OLED_ROTATION);

  drawLogo();
  syncWithLinux();
  drawStatus();
}

void loop() {
  pollButtons();

  if (redrawRequested) {
    redrawRequested = false;
    drawStatus();
  }
}
