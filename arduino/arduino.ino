// ============================================================
//  StreamDeck – Arduino firmware
//  Potentiometers + button matrix → Serial (115200 baud)
// ============================================================

// === POTENTIOMETERS ===
static const uint8_t POT_COUNT     = 4;
static const uint8_t potPins[POT_COUNT] = {A0, A1, A2, A3};
static const uint8_t OVERSAMPLE    = 8;   // reads summed then averaged → keeps 0–1023 range
static const uint8_t POT_THRESHOLD = 5;   // min change to transmit after EMA (post-filtered)

// Integer fixed-point EMA: stored as value × 256
// alpha = 1/4  →  new = old*(3/4) + sample*(1/4)
// In fixed-point:  ema_fp = ema_fp - (ema_fp>>2) + (sample<<6)
// Read back with:  ema_fp >> 8
static int32_t emaFP[POT_COUNT];
static int16_t lastPotValues[POT_COUNT];

// === BUTTON MATRIX ===
static const uint8_t NUM_ROWS = 6;
static const uint8_t NUM_COLS = 4;
static const uint8_t rowPins[NUM_ROWS] = {2, 3, 4, 5, 6, 7};
static const uint8_t colPins[NUM_COLS] = {8, 9, 10, 11};

static bool     lastState[NUM_ROWS][NUM_COLS];
static uint32_t debounceTimer[NUM_ROWS][NUM_COLS];
static const uint16_t DEBOUNCE_MS = 18;

static char msgBuf[12];

// ---------------------------------------------------------------
//  8× oversampling — sums 8 reads, right-shifts 3 → keeps 0–1023
// ---------------------------------------------------------------
static inline int16_t oversampledRead(uint8_t pin) {
  int32_t sum = 0;
  for (uint8_t i = 0; i < OVERSAMPLE; i++) {
    sum += analogRead(pin);
  }
  return (int16_t)(sum >> 3);
}

// ---------------------------------------------------------------
void setup() {
  Serial.begin(115200);

  // Seed EMA and last-values from real readings
  for (uint8_t i = 0; i < POT_COUNT; i++) {
    int16_t v  = oversampledRead(potPins[i]);
    emaFP[i]   = (int32_t)v << 8;   // initialise fixed-point store
    lastPotValues[i] = v;
  }

  for (uint8_t r = 0; r < NUM_ROWS; r++) {
    pinMode(rowPins[r], OUTPUT);
    digitalWrite(rowPins[r], HIGH);
  }
  for (uint8_t c = 0; c < NUM_COLS; c++) {
    pinMode(colPins[c], INPUT_PULLUP);
  }

  memset(lastState,     false, sizeof(lastState));
  memset(debounceTimer, 0,     sizeof(debounceTimer));
}

// ---------------------------------------------------------------
static void scanPots() {
  for (uint8_t i = 0; i < POT_COUNT; i++) {
    int16_t sample = oversampledRead(potPins[i]);

    // Integer EMA  (alpha = 1/4)
    emaFP[i] = emaFP[i] - (emaFP[i] >> 2) + ((int32_t)sample << 6);
    int16_t val = (int16_t)(emaFP[i] >> 8);

    if (abs(val - lastPotValues[i]) > POT_THRESHOLD) {
      snprintf(msgBuf, sizeof(msgBuf), "P%u:%d", i, val);
      Serial.println(msgBuf);
      lastPotValues[i] = val;
    }
  }
}

// ---------------------------------------------------------------
static void scanButtons() {
  uint32_t now = millis();

  for (uint8_t r = 0; r < NUM_ROWS; r++) {
    digitalWrite(rowPins[r], LOW);
    delayMicroseconds(10);

    for (uint8_t c = 0; c < NUM_COLS; c++) {
      bool pressed = (digitalRead(colPins[c]) == LOW);

      if (pressed != lastState[r][c]) {
        if ((now - debounceTimer[r][c]) >= DEBOUNCE_MS) {
          debounceTimer[r][c] = now;
          lastState[r][c]     = pressed;

          if (pressed) {
            snprintf(msgBuf, sizeof(msgBuf), "B%u:1", (uint8_t)(r * NUM_COLS + c));
            Serial.println(msgBuf);
          }
        }
      }
    }

    digitalWrite(rowPins[r], HIGH);
  }
}

// ---------------------------------------------------------------
void loop() {
  scanPots();
  scanButtons();
}
