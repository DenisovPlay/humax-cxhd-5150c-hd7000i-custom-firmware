/*
 JTAGenum
 Given a Arduino compatible microcontroller JTAGenum scans
 pins[] for basic JTAG functionality. After programming
 your microcontroller open a serial terminal with 115200
 baud and send 'h' to see usage information.

 SETUP:
 Define the pins[] and pinnames[] for your microcontroller.

 If after finding the JTAG pins of target you would like
 to run the IRenum and BYPASS scans, then set the
 TCK, TMS, TDO, TDI, TRST #define's

 Further documentation:
 http://github.com/cyphunk/JTAGenum/
 http://deadhacker.com/2010/02/03/jtag-enumeration/

 This license for this code is whatever you want it to be
*/

//needed to put help strings into flash
#ifdef ARDUINO_ARCH_AVR
#include <avr/pgmspace.h>
#else
#include <pgmspace.h>
#endif

#ifdef ESP32
#include <esp_task_wdt.h>
#endif

// #define DEBUGTAP
// #define DEBUGIR

/*
 * BEGIN USER DEFINITIONS
 */
//#define HALFCLOCK // uncomment for AVR (arduino/teensy) running at 3.3v

/*
 * SETUP TARGET PINS
 * determine your microcontroller platform mand set pins accordingly
 * pins[] should be valid pins of your microcontroller
 * pinnames[] can be any string you choose
 * when in doubt comment out all but one pin[] pinnames[] definition
 */
#if   defined(TEENSY_40)    // Teensy v4 usable digital are: A0-A9; A0-A9 are always digital 14-23, for Arduino compatibility
 byte       pins[] = {  A0 ,  A1 ,  A2 ,  A3 ,  A4 ,  A5 ,  A6 ,  A7, A8, A9  };
 String pinnames[] = { "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9" };
#elif   defined(KINETISK)   // Teensy v3 usable digital are: A0-A7. 13=LED
 byte       pins[] = {  A0 ,  A1 ,  A2 ,  A3 ,  A4 ,  A5 ,  A6 ,  A7  };
 String pinnames[] = { "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7" };
#elif defined(CORE_TEENSY)  // Teensy v2
 byte       pins[] = { PIN_B2 , PIN_B3 , PIN_B6 , PIN_B4 , PIN_B1  };
 String pinnames[] = {    "B2",    "B3",    "B6",    "B4",    "B1" };
#elif defined(ENERGIA)     // TI Launchpad Tiva C
 byte       pins[] = {  PA_5,   PB_4,   PE_5,   PE_4,   PB_1  };
 String pinnames[] = { "PA_5", "PB_4", "PE_5", "PE_4", "PB_1" };
#elif defined(STM32)       // STM32 bluepill, pinout is here: https://wiki.stm32duino.com/index.php?title=File:Bluepillpinout.gif. See also instructions to get it running with the Arduino IDE here: http://www.zoobab.com/bluepill-arduinoide
 byte       pins[] = {  10 ,  11 ,  12 ,  13 ,  14 ,  15 ,  16 ,  17, 18 , 19 , 21 , 22  };
 String pinnames[] = { "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "21", "22" };
#elif defined(STM32Nucleo) // STM32 Nucleo, pinout is here: https://os.mbed.com/platforms/ST-Nucleo-L152RE/.
 byte       pins[] = {  D2 ,  D3 ,  D4 ,  D5 ,  D6  };
 String pinnames[] = { "D2", "D3", "D4", "D5", "D6" };
#elif defined(ESP32)       // nano esp32 - not sure if correct pinout
 byte       pins[] = {  D2 ,  D3 ,  D4 ,  D5 ,  D6 ,  D7 ,  D8 ,  D9 ,  D10 ,  D11 ,  D12  };
 String pinnames[] = { "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"," D10", "D11", "D12" };
#elif defined(ESP8266) || defined(ARDUINO_ARCH_ESP8266) // Wemos D1 mini (ESP8266)
 // Humax JTAG: D1=TRST, D2=TDO, D5=TCK, D6=TDI, D7=TMS
 byte       pins[] = {  D1 ,  D2 ,  D5 ,  D6 ,  D7  };
 String pinnames[] = { "D1", "D2", "D5", "D6", "D7" };
#else                      // DEFAULT
                           // Arduino Pro. usable digital 2-12,14-10. 13=LED 0,1=serial
 byte       pins[] = { 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};
 String pinnames[] = { "DIG_2", "DIG_3", "DIG_4", "DIG_5" , "DIG_6",
                       "DIG_7", "DIG_8", "DIG_9", "DIG_10", "DIG_11"};
  #include <EEPROM.h>
  #define EEPROMSTORE
#endif

// Once you have found the JTAG pins you can define
// the following to allow for the boundary scan and
// irenum functions to be run.
//
// The value is the index to the pin in pins[] array
// eg. TCK=3 is used as pins[TCK] pins[3]
#define PIN_NOT_SET 0xff
String jtagpinnames[] = { "TCK", "TMS", "TDO", "TDI", "TRST" };

byte TCK  = PIN_NOT_SET;
byte TMS  = PIN_NOT_SET;
byte TDO  = PIN_NOT_SET;
byte TDI  = PIN_NOT_SET;
byte TRST = PIN_NOT_SET;

// Pattern used for scan() and loopback() tests
#define PATTERN_LEN              64
// Use something random when trying find JTAG lines:
static char pattern[PATTERN_LEN] = "0110011101001101101000010111001001";
// Use something more determinate when trying to find
// length of the DR register:
//static char pattern[PATTERN_LEN] = "1000000000000000000000000000000000";

// Max. number of JTAG enabled chips (MAX_DEV_NR) and length
// of the DR register together define the number of
// iterations to run for scan_idcode():
#define MAX_DEV_NR               8
#define IDCODE_LEN               32

// Target specific, check your documentation or guess
#define SCAN_LEN                 1890 // used for IR enum. bigger the better
#define IR_LEN                   5
// IR registers must be IR_LEN wide:
#define IR_IDCODE                "01100" // always 011
#define IR_SAMPLE                "10100" // always 101
#define IR_PRELOAD               IR_SAMPLE

/*
 * END USER DEFINITIONS
 */



// TAP TMS states we care to use. NOTE: MSB sent first
// Meaning ALL TAP and IR codes have their leftmost
// bit sent first. This might be the reverse of what
// documentation for your target(s) show.
#define TAP_RESET                "11111"       // looping 1 will return
                                               // IDCODE if reg available
#define TAP_SHIFTDR              "111110100"
#define TAP_SHIFTIR              "1111101100" // -11111> Reset -0> Idle -1> SelectDR
                                              // -1> SelectIR -0> CaptureIR -0> ShiftIR

// Ignore TCK, TMS use in loopback check:
#define IGNOREPIN                0xFFFF
// Flags configured by UI:
#define TRUE                     255
#define FALSE                    0
boolean VERBOSE                  = FALSE;
boolean DELAY                    = TRUE;
long    DELAYUS                  = 100;
boolean JTAG_PULLUP              = TRUE;


const byte pinslen               = sizeof(pins)/sizeof(pins[0]);

// For 3.3v AVR boards. Cuts clock in half. Also see cmd in setup()
#define CPU_PRESCALE(n) (CLKPR = 0x80, CLKPR = (n))


/*
* Return a pointer to the jtag pins given an index.
*
*/
byte * jtag_ptr_from_idx(const int idx){
  byte * curr;
  switch (idx) {
      case 0:
        curr = &TCK;
        break;
      case 1:
        curr = &TMS;
        break;
      case 2:
        curr = &TDO;
        break;
      case 3:
        curr = &TDI;
        break;
      case 4:
        curr = &TRST;
        break;
  }
  return curr;
}


void setup(void)
{
#ifdef HALFCLOCK
        // for 3.3v boards. Cuts clock in half
        // normally only on avr based arduino & teensy hardware
        CPU_PRESCALE(0x01);
#endif
        Serial.begin(115200);

        byte *curr;
        for (int i = 0; i < 5; ++i) {
          curr = jtag_ptr_from_idx(i);
          if (*curr == PIN_NOT_SET) {
#ifdef EEPROMSTORE
            // if we are on arduino we can save/restore jtag pins from
            // the eeprom
            *curr = EEPROM.read(i);
#endif
            if( *curr >= pinslen){
              *curr = i;
            }
          }
        }
}


/*
 * Set the JTAG TAP state machine
 */
void tap_state(String tap_state, int tck, int tms)
{
#ifdef DEBUGTAP
  Serial.print("tap_state: tms set to: ");
#endif
  int tap_state_length = tap_state.length();
  for (int i=0; i<tap_state_length; i++) {
    if (DELAY) delayMicroseconds(DELAYUS);
    digitalWrite(tck, LOW);
    digitalWrite(tms, tap_state[i] - '0'); // conv from ascii pattern
#ifdef DEBUGTAP
    Serial.print(tap_state[i] - '0',DEC);
#endif
    digitalWrite(tck, HIGH); // rising edge shifts in TMS
  }
#ifdef DEBUGTAP
  Serial.println();
#endif
}

static void pulse_tms(int tck, int tms, int s_tms)
{
  if (tck == IGNOREPIN) return;
  digitalWrite(tck, LOW);
  digitalWrite(tms, s_tms);
  digitalWrite(tck, HIGH);
}
static void pulse_tdi(int tck, int tdi, int s_tdi)
{
  if (DELAY) delayMicroseconds(DELAYUS);
  if (tck != IGNOREPIN) digitalWrite(tck, LOW);
  digitalWrite(tdi, s_tdi);
  if (tck != IGNOREPIN) digitalWrite(tck, HIGH);
}
byte pulse_tdo(int tck, int tdo)
{
  byte tdo_read;
  if (DELAY) delayMicroseconds(DELAYUS);
  digitalWrite(tck, LOW); // read in TDO on falling edge
  tdo_read = digitalRead(tdo);
  digitalWrite(tck, HIGH);
  return tdo_read;
}

/*
 * Initialize all pins to a default state
 * default with no arguments: all pins as INPUTs
 */
void init_pins(int tck = IGNOREPIN, int tms = IGNOREPIN, int tdi = IGNOREPIN, int ntrst = IGNOREPIN)
{
#if defined(ESP32)
  esp_task_wdt_reset(); //reset timer (feed watchdog)
#elif defined(ESP8266) || defined(ARDUINO_ARCH_ESP8266) || defined(ESP_H)
  ESP.wdtFeed(); //feed watchdog
#endif
  // default all to INPUT state
  for (int i = 0; i < pinslen; i++) {
    pinMode(pins[i], INPUT);
    // internal pullups default to logic 1:
    if (JTAG_PULLUP) digitalWrite(pins[i], HIGH);
  }
  // TCK = output
  if (tck != IGNOREPIN) pinMode(tck, OUTPUT);
  // TMS = output
  if (tms != IGNOREPIN) pinMode(tms, OUTPUT);
  // tdi = output
  if (tdi != IGNOREPIN) pinMode(tdi, OUTPUT);
  // ntrst = output, fixed to 1
  if (ntrst != IGNOREPIN) {
    pinMode(ntrst, OUTPUT);
    digitalWrite(ntrst, HIGH);
  }
}


/*
 * send pattern[] to TDI and check for output on TDO
 * This is used for both loopback, and Shift-IR testing, i.e.
 * the pattern may show up with some delay.
 * return: 0 = no match
 *       1 = match
 *       2 or greater = no pattern found but line appears active
 *
 * if retval == 1, *reglen returns the length of the register
 */
static int check_data(char pattern[], int iterations, int tck, int tdi, int tdo,
                      int *reg_len)
{
  int i;
  int w          = 0;
  int plen       = strlen(pattern);
  char tdo_read;
  char tdo_prev;
  int nr_toggle  = 0; // count how often tdo toggled
  /* we store the last plen (<=PATTERN_LEN) bits,
   *  rcv[0] contains the oldest bit */
  char rcv[PATTERN_LEN];

  tdo_prev = '0' + (digitalRead(tdo) == HIGH);

  for(i = 0; i < iterations; i++) {

    /* output pattern and incr write index */
    pulse_tdi(tck, tdi, pattern[w++] - '0');
    if (!pattern[w])
      w = 0;

    /* read from TDO and put it into rcv[] */
    tdo_read  =  '0' + (digitalRead(tdo) == HIGH);

    nr_toggle += (tdo_read != tdo_prev);
    tdo_prev  =  tdo_read;

    if (i < plen)
      rcv[i] = tdo_read;
    else
    {
      memmove(rcv, rcv + 1, plen - 1);
      rcv[plen-1] = tdo_read;
    }

    /* check if we got the pattern in rcv[] */
    if (i >= (plen - 1) ) {
      if (!memcmp(pattern, rcv, plen)) {
        *reg_len = i + 1 - plen;
        return 1;
      }
    }
  } /* for(i=0; ... ) */

  *reg_len = 0;
  return nr_toggle > 1 ? nr_toggle : 0;
}

static void print_pins(int tck, int tms, int tdo, int tdi, int ntrst)
{
  if (ntrst != IGNOREPIN) {
    Serial.print(" ntrst:");
    Serial.print(pinnames[ntrst]);
  }
  Serial.print(" tck:");
  Serial.print(pinnames[tck]);
  Serial.print(" tms:");
  Serial.print(pinnames[tms]);
  Serial.print(" tdo:");
  Serial.print(pinnames[tdo]);
  if (tdi != IGNOREPIN) {
    Serial.print(" tdi:");
    Serial.print(pinnames[tdi]);
  }
}

/*
 * Shift JTAG TAP to ShiftIR state. Send pattern to TDI and check
 * for output on TDO
 */
static void scan()
{
  int tck, tms, tdo, tdi, ntrst;
  int checkdataret = 0;
  int len;
  int reg_len;
  printProgStr(PSTR("================================\r\n"
                    "Starting scan for pattern:"));
  Serial.println(pattern);
  for(ntrst=0;ntrst<pinslen;ntrst++) {
    for(tck=0;tck<pinslen;tck++) {
      if(tck == ntrst) continue;
      for(tms=0;tms<pinslen;tms++) {
        if(tms == ntrst) continue;
        if(tms == tck  ) continue;
        for(tdo=0;tdo<pinslen;tdo++) {
          if(tdo == ntrst) continue;
          if(tdo == tck  ) continue;
          if(tdo == tms  ) continue;
          for(tdi=0;tdi<pinslen;tdi++) {
            if(tdi == ntrst) continue;
            if(tdi == tck  ) continue;
            if(tdi == tms  ) continue;
            if(tdi == tdo  ) continue;
            if(VERBOSE) {
              print_pins(tck, tms, tdo, tdi, ntrst);
              Serial.print("    ");
            }
            init_pins(pins[tck], pins[tms], pins[tdi], pins[ntrst]);
            tap_state(TAP_SHIFTIR, pins[tck], pins[tms]);
            checkdataret = check_data(pattern, (2*PATTERN_LEN),
                            pins[tck], pins[tdi], pins[tdo], &reg_len);
            if(checkdataret == 1) {
              Serial.print("FOUND! ");
              print_pins(tck, tms, tdo, tdi, ntrst);
              Serial.print(" IR length: ");
              Serial.println(reg_len, DEC);
            }
            else if(checkdataret > 1) {
              Serial.print("active ");
              print_pins(tck, tms, tdo, tdi, ntrst);
              Serial.print("  bits toggled:");
              Serial.println(checkdataret);
            }
            else if(VERBOSE) Serial.println();
          } /* for(tdi=0; ... ) */
        } /* for(tdo=0; ... ) */
      } /* for(tms=0; ... ) */
    } /* for(tck=0; ... ) */
  } /* for(ntrst=0; ... ) */
  printProgStr(PSTR("================================\r\n"));
}
/*
 * Check for pins that pass pattern[] between tdi and tdo
 * regardless of JTAG TAP state (tms, tck ignored).
 *
 * TDO, TDI pairs that match indicate possible shorts between
 * pins. Pins that do not match but are active might indicate
 * that the patch cable used is not shielded well enough. Run
 * the test again without the cable connected between controller
 * and target. Run with the verbose flag to examine closely.
 */
static void loopback_check()
{
  int tdo, tdi;
  int checkdataret = 0;
  int reg_len;

  printProgStr(PSTR("================================\r\n"
                    "Starting loopback check...\r\n"));
  for(tdo=0;tdo<pinslen;tdo++) {
    for(tdi=0;tdi<pinslen;tdi++) {
      if(tdi == tdo) continue;

      if(VERBOSE) {
        Serial.print(" tdo:");
        Serial.print(pinnames[tdo]);
        Serial.print(" tdi:");
        Serial.print(pinnames[tdi]);
        Serial.print("    ");
      }
      init_pins(IGNOREPIN/*tck*/, IGNOREPIN/*tms*/, pins[tdi], IGNOREPIN /*ntrst*/);
      checkdataret = check_data(pattern, (2*PATTERN_LEN), IGNOREPIN, pins[tdi], pins[tdo], &reg_len);
      if(checkdataret == 1) {
        Serial.print("FOUND! ");
        Serial.print(" tdo:");
        Serial.print(pinnames[tdo]);
        Serial.print(" tdi:");
        Serial.print(pinnames[tdi]);
        Serial.print(" reglen:");
        Serial.println(reg_len);
      }
      else if(checkdataret > 1) {
        Serial.print("active ");
        Serial.print(" tdo:");
        Serial.print(pinnames[tdo]);
        Serial.print(" tdi:");
        Serial.print(pinnames[tdi]);
        Serial.print("  bits toggled:");
        Serial.println(checkdataret);
      }
      else if(VERBOSE) Serial.println();
    }
  }
  printProgStr(PSTR("================================\r\n"));
}

static void list_pin_names()
{
  int pin;
  Serial.print("The configured pins are:\r\n");
  for(pin=0;pin<pinslen;pin++) {
    Serial.print(pinnames[pin]);
    Serial.print(" ");
  }
  Serial.println();
}

/*
 * Scan TDO for IDCODE. Handle MAX_DEV_NR many devices.
 * We feed zeros into TDI and wait for the first 32 of them to come out at TDO (after n * 32 bit).
 * As IEEE 1149.1 requires bit 0 of an IDCODE to be a "1", we check this bit.
 * We record the first bit from the idcodes into bit0.
 * (oppposite to the old code).
 * If we get an IDCODE of all ones, we assume that the pins are wrong.
 * This scan assumes IDCODE is the default DR between TDI and TDO.
 */
static void scan_idcode()
{
  int tck, tms, tdo, tdi, ntrst;
  int i, j;
  int tdo_read;
  uint32_t idcodes[MAX_DEV_NR];
  printProgStr(PSTR("================================\r\n"
                    "Starting scan for IDCODE...\r\n"
                    "(assumes IDCODE default DR)\r\n"));
  uint32_t idcode;
  for(ntrst=0;ntrst<pinslen;ntrst++) {
    for(tck=0;tck<pinslen;tck++) {
      if(tck == ntrst) continue;
      for(tms=0;tms<pinslen;tms++) {
        if(tms == ntrst) continue;
        if(tms == tck  ) continue;
        for(tdo=0;tdo<pinslen;tdo++) {
          if(tdo == ntrst) continue;
          if(tdo == tck  ) continue;
          if(tdo == tms  ) continue;
          for(tdi=0;tdi<pinslen;tdi++) {
            if(tdi == ntrst) continue;
            if(tdi == tck  ) continue;
            if(tdi == tms  ) continue;
            if(tdi == tdo  ) continue;
            if(VERBOSE) {
              print_pins(tck, tms, tdo, tdi, ntrst);
              Serial.print("    ");
            }
            init_pins(pins[tck], pins[tms], pins[tdi], pins[ntrst]);

            /* pulse nTRST low then high to force TAP reset */
            digitalWrite(pins[ntrst], LOW);
            delayMicroseconds(500);
            digitalWrite(pins[ntrst], HIGH);
            delayMicroseconds(500);

            /* we hope that IDCODE is the default DR after reset */
            tap_state(TAP_RESET, pins[tck], pins[tms]);
            tap_state(TAP_SHIFTDR, pins[tck], pins[tms]);

            /* j is the number of bits we pulse into TDI and read from TDO */
            for(i = 0; i < MAX_DEV_NR; i++) {
              idcodes[i] = 0;
              for(j = 0; j < IDCODE_LEN;j++) {
                /* we send '0' in */
                pulse_tdi(pins[tck], pins[tdi], 0);
                tdo_read = digitalRead(pins[tdo]);
                if (tdo_read)
                  idcodes[i] |= ( (uint32_t) 1 ) << j;

                if (VERBOSE)
                  Serial.print(tdo_read,DEC);
              } /* for(j=0; ... ) */
              if (VERBOSE) {
                Serial.print(" ");
                Serial.println(idcodes[i],HEX);
              }
              /* save time: break at the first idcode with bit0 != 1 */
              if (!(idcodes[i] & 1) || idcodes[i] == 0xffffffff)
                break;
            } /* for(i=0; ...) */

            if (i > 0) {
              print_pins(tck,tms,tdo,tdi,ntrst);
              Serial.print("  devices: ");
              Serial.println(i,DEC);
              for(j = 0; j < i; j++) {
                Serial.print("  0x");
                Serial.println(idcodes[j],HEX);
              }
            }
            else if (idcodes[0] == 0xffffffff) {
              Serial.print("all-ones");
              print_pins(tck,tms,tdo,tdi,ntrst);
              Serial.println();
            }
            else if (idcodes[0] != 0x00000000) {
              Serial.print("raw:0x");
              Serial.print(idcodes[0],HEX);
              print_pins(tck,tms,tdo,tdi,ntrst);
              Serial.println();
            } /* if (i > 0) */
          } /* for(tdo=0; ... ) */
        } /* for(tdi=0; ...) */
      } /* for(tms=0; ...) */
    } /* for(tck=0; ...) */
  } /* for(trst=0; ...) */

  printProgStr(PSTR("================================\r\n"));
}

static void shift_bypass()
{
  int tdi, tdo, tck;
  int checkdataret;
  int reg_len;

  printProgStr(PSTR("================================\r\n"
                    "Starting shift of pattern through bypass...\r\n"
                    "Assumes bypass is the default DR on reset.\r\n"
                    "Hence, no need to check for TMS. Also, currently\r\n"
                    "not checking for nTRST, which might not work\r\n"));
  for(tck=0;tck<pinslen;tck++) {
    for(tdi=0;tdi<pinslen;tdi++) {
      if(tdi == tck) continue;
      for(tdo=0;tdo<pinslen;tdo++) {
        if(tdo == tck) continue;
        if(tdo == tdi) continue;
        if(VERBOSE) {
          Serial.print(" tck:");
          Serial.print(pinnames[tck]);
          Serial.print(" tdi:");
          Serial.print(pinnames[tdi]);
          Serial.print(" tdo:");
          Serial.print(pinnames[tdo]);
          Serial.print("    ");
        }

        init_pins(pins[tck], IGNOREPIN/*tms*/,pins[tdi], IGNOREPIN /*ntrst*/);
        // if bypass is default on start, no need to init TAP state
        checkdataret = check_data(pattern, (2*PATTERN_LEN), pins[tck], pins[tdi], pins[tdo], &reg_len);
        if(checkdataret == 1) {
          Serial.print("FOUND! ");
          Serial.print(" tck:");
          Serial.print(pinnames[tck]);
          Serial.print(" tdo:");
          Serial.print(pinnames[tdo]);
          Serial.print(" tdi:");
          Serial.println(pinnames[tdi]);
        }
        else if(checkdataret > 1) {
          Serial.print("active ");
          Serial.print(" tck:");
          Serial.print(pinnames[tck]);
          Serial.print(" tdo:");
          Serial.print(pinnames[tdo]);
          Serial.print(" tdi:");
          Serial.print(pinnames[tdi]);
          Serial.print("  bits toggled:");
          Serial.println(checkdataret);
        }
        else if(VERBOSE) Serial.println();
      }
    }
  }
  printProgStr(PSTR("================================\r\n"));
}
/* ir_state()
 * Set TAP to Reset then ShiftIR.
 * Shift in state[] as IR value.
 * Switch to ShiftDR state and end.
 */
void ir_state(String state, int tck, int tms, int tdi)
{
#ifdef DEBUGIR
  Serial.println("ir_state: set TAP to ShiftIR:");
#endif
  tap_state(TAP_SHIFTIR, tck, tms);
#ifdef DEBUGIR
  Serial.print("ir_state: pulse_tdi to: ");
#endif
  for (int i=0; i < IR_LEN; i++) {
    if (DELAY) delayMicroseconds(DELAYUS);
    // TAP/TMS changes to Exit IR state (1) must be executed
    // at same time that the last TDI bit is sent:
    if (i == IR_LEN-1) {
      digitalWrite(tms, HIGH); // ExitIR
#ifdef DEBUGIR
      Serial.print(" (will be in ExitIR after next bit) ");
#endif
    }
    pulse_tdi(tck, tdi, state[i] - '0');
#ifdef DEBUGIR
    Serial.print(state[i] - '0', DEC);
#endif
    // TMS already set to 0 "shiftir" state to shift in bit to IR
  }
#ifdef DEBUGIR
  Serial.println("\r\nir_state: Change TAP from ExitIR to ShiftDR:");
#endif
  // a reset would cause IDCODE instruction to be selected again
  tap_state("1100", tck, tms); // -1> UpdateIR -1> SelectDR -0> CaptureDR -0> ShiftDR
}
static void sample(int iterations, int tck, int tms, int tdi, int tdo, int ntrst=IGNOREPIN)
{
  printProgStr(PSTR("================================\r\n"
                    "Starting sample (boundary scan)...\r\n"));
  init_pins(tck, tms ,tdi, ntrst);

  // send instruction and go to ShiftDR
  ir_state(IR_SAMPLE, tck, tms, tdi);

  // Tell TAP to go to shiftout of selected data register (DR)
  // is determined by the instruction we sent, in our case
  // SAMPLE/boundary scan
  for (int i = 0; i < iterations; i++) {
    // no need to set TMS. It's set to the '0' state to
    // force a Shift DR by the TAP
    Serial.print(pulse_tdo(tck, tdo),DEC);
    if (i % 32  == 31 ) Serial.print(" ");
    if (i % 128 == 127) Serial.println();
  }
}

char ir_buf[IR_LEN+1];
static void brute_ir(int iterations, int tck, int tms, int tdi, int tdo, int ntrst=IGNOREPIN)
{
  printProgStr(PSTR("================================\r\n"
                    "Starting brute force scan of IR instructions...\r\n"
                    "NOTE: If Verbose mode is off output is only printed\r\n"
                    "      after activity (bit changes) are noticed and\r\n"
                    "      you might not see the first bit of output.\r\n"
                    "IR_LEN set to "));
  Serial.println(IR_LEN,DEC);

  init_pins(tck, tms ,tdi, ntrst);
  int iractive;
  byte tdo_read;
  byte prevread;
  for (uint32_t ir = 0; ir < (1UL << IR_LEN); ir++) {
    iractive=0;
    // send instruction and go to ShiftDR (ir_state() does this already)
    // convert ir to string.
    for (int i = 0; i < IR_LEN; i++)
      ir_buf[i]=bitRead(ir, i)+'0';
    ir_buf[IR_LEN]=0;// terminate
    ir_state(ir_buf, tck, tms, tdi);
    // we are now in TAP_SHIFTDR state

    prevread = pulse_tdo(tck, tdo);
    for (int i = 0; i < iterations-1; i++) {
      // no need to set TMS. It's set to the '0' state to force a Shift DR by the TAP
      tdo_read = pulse_tdo(tck, tdo);
      if (tdo_read != prevread) iractive++;

      if (iractive || VERBOSE) {
        Serial.print(prevread,DEC);
        if (i%16 == 15) Serial.print(" ");
        if (i%128 == 127) Serial.println();
      }
      prevread = tdo_read;
    }
    if (iractive || VERBOSE) {
      Serial.print(prevread,DEC);
      Serial.print("  Ir ");
      Serial.print(ir_buf);
      Serial.print("  bits changed ");
      Serial.println(iractive, DEC);
    }
  }
}

void set_pattern()
{
  int i;
  char c;

  Serial.print("Enter new pattern of 1's or 0's (terminate with new line or '.'):\r\n"
               "> ");
  i = 0;
  while(1) {
    c = Serial.read();
    switch(c) {
    case '0':
    case '1':
      if(i < (PATTERN_LEN - 1) ) {
        pattern[i++] = c;
        Serial.print(c);
      }
      break;
    case '\n':
    case '\r':
    case '.': // bah. for the arduino serial console which does not pass us \n
      pattern[i] = 0;
      Serial.println();
      Serial.print("new pattern set [");
      Serial.print(pattern);
      Serial.println("]");
      return;
    }
  }
}

void configure_pins(){
  Serial.println("Available pins, the index is based on them");
  for(int pin=0;pin<pinslen;pin++) {
    Serial.print(pinnames[pin]);
    Serial.print("[");
    Serial.print(pin);
    Serial.print("]");
    Serial.print(" ");
  }
  Serial.println();
  Serial.println("Current pin configuration");
  print_pins(TCK, TMS, TDO, TDI, TRST);
  byte * curr = NULL;
  for (int i = 0; i < 5; ++i) {
    curr = jtag_ptr_from_idx(i);
    do{
      // Print current value
      Serial.println();
      Serial.print(jtagpinnames[i]);
      Serial.print("(");
      Serial.print(*curr, DEC);
      Serial.print(") = ");
      // Read the new pin configuration
      while(!Serial.available())
            ;
      *curr = Serial.parseInt();
    } while(*curr >= pinslen );
    Serial.print(*curr);
#ifdef EEPROMSTORE
    // Save to eeprom
    EEPROM.write(i, *curr);
#endif
  }
  Serial.print("\nConfiguration saved\n");
}

// given a PROGMEM string, use Serial.print() to send it out
void printProgStr(const char *str)
{
  char c;
  if(!str) return;
  while((c = pgm_read_byte(str++)))
    Serial.print(c);
}

void help()
{
  printProgStr(PSTR(
      "Short and long form commands can be used.\r\n"
      "\r\n"
      "SCANS\r\n"
      "-----\r\n"
      "s > pattern scan\r\n"
      "   Scans for all JTAG pins. Attempts to set TAP state to\r\n"
      "   DR_SHIFT and then shift the pattern through the DR.\r\n"
      "p > pattern set\r\n"
      "   currently: ["));
  Serial.print(pattern);
  printProgStr(PSTR("]\r\n"
      "\r\n"
      "i > idcode scan\r\n"
      "   Assumes IDCODE is default DR on reset. Ignores TDI.\r\n"
      "   Sets TAP state to DR_SHIFT and prints TDO to console\r\n"
      "   when TDO appears active. Human examination required to\r\n"
      "   determine if actual IDCODE is present. Run several\r\n"
      "   times to check for consistancy or compare against\r\n"
      "   active tdo lines found with loopback test.\r\n"
      "\r\n"
      "b > bypass scan\r\n"
      "   Assumes BYPASS is default DR on reset. Ignores TMS and\r\n"
      "   shifts pattern[] through TDI/TDO using TCK for clock.\r\n"
      "\r\n"
      "ERATTA\r\n"
      "------\r\n"
      "l > loopback check\r\n"
      "   ignores tck,tms. if patterns passed to tdo pins are\r\n"
      "   connected there is a short or a false-possitive\r\n"
      "   condition exists that should be taken into account\r\n"
      "r > pullups\r\n"
      "   internal pullups on inputs, on/off. might increase\r\n"
              "   stability when using a bad patch cable.\r\n"
      "v > verbose\r\n"
      "   on/off. print tdo bits to console during testing. If on, this will slow\r\n"
      "   down scan.\r\n"
      "d > delay\r\n"
      "   on/off. will slow down scan.\r\n"
      "- > delay -\r\n"
      "   reduce delay microseconds\r\n"
      "c > configure pin\r\n"
      "   configure jtag pins\r\n"
      "- > delay -\r\n"
      "   reduce delay microseconds\r\n"
      "+ > delay +\r\n"
      "h > help\r\n"
      "n > list pin names\r\n"
      "\r\n"
      "OTHER JTAG TESTS\r\n"
      "----------------\r\n"
      "Each of the following will not scan/find JTAG and require\r\n"
      "that you manually set the JTAG pins. See their respective\r\n"
      "call from the loop() function of code to set.\r\n"
      "\r\n"
      "1 > pattern scan single\r\n"
      "   runs a full check on one code-defined tdi<>tdo pair.\r\n"
      "   look at the main()/loop() code to specify pins.\r\n"
      "x > boundary scan\r\n"
      "   checks code defined tdo for 4000+ bits.\r\n"
      "   look at the main()/loop() code to specify pins.\r\n"
      "y > irenum\r\n"
      "   sets every possible Instruction Register and then\r\n"
      "   checks the output of the Data Register.\r\n"
      "   look at the main()/loop() code to specify pins.\r\n"
      ));
}
/*
 * main()
 */
#define CMDLEN 20
char command[CMDLEN];
int dummy;
void loop()
{
  if (Serial.available())
  {
    // READ COMMAND
    delay(5); // hoping read buffer is idle after 5 ms
    int i = 0;
    while (Serial.available() && i < CMDLEN-1)
      command[i++] = Serial.read();

    Serial.flush();
    command[i] = 0; // terminate string
    Serial.println(command); // echo back

    // EXECUTE COMMAND
    if     (strcmp(command, "pattern scan") == 0                     || strcmp(command, "s") == 0)
      scan();
    else if(strcmp(command, "pattern scan single") == 0              || strcmp(command, "1") == 0)
    {
      Serial.print("pins");
      print_pins(TCK, TMS, TDO, TDI, TRST);
      init_pins(pins[TCK], pins[TMS], pins[TDI], pins[TRST] /*ntrst*/);
      tap_state(TAP_SHIFTIR, pins[TCK], pins[TMS]);
      if (check_data(pattern, (2*PATTERN_LEN), pins[TCK], pins[TDI], pins[TDO], &dummy))
        Serial.println("found pattern or other");
      else
        Serial.println("no pattern found");
    }
    else if(strcmp(command, "pattern set") == 0                      || strcmp(command, "p") == 0)
      set_pattern();
    else if(strcmp(command, "loopback check") == 0                   || strcmp(command, "l") == 0)
      loopback_check();
    else if(strcmp(command, "idcode scan") == 0                      || strcmp(command, "i") == 0)
      scan_idcode();
    else if(strcmp(command, "bypass scan") == 0                      || strcmp(command, "b") == 0)
      shift_bypass();
    else if(strcmp(command, "boundary scan") == 0                    || strcmp(command, "x") == 0)
    {
      Serial.print("pins");
      print_pins(TCK, TMS, TDO, TDI, TRST);
      Serial.println();
      sample(SCAN_LEN+100, pins[TCK], pins[TMS], pins[TDI], pins[TDO], pins[TRST]);
    }
    else if(strcmp(command, "irenum") == 0                           || strcmp(command, "y") == 0)
      brute_ir(SCAN_LEN,   pins[TCK], pins[TMS], pins[TDI], pins[TDO], pins[TRST]);
    else if(strcmp(command, "verbose") == 0                          || strcmp(command, "v") == 0)
    {
      if (VERBOSE == FALSE) {VERBOSE = TRUE;} else {VERBOSE = FALSE;}
      Serial.println(VERBOSE ? "Verbose ON" : "Verbose OFF");
    }
    else if(strcmp(command, "delay") == 0                            || strcmp(command, "d") == 0)
    {
      if (DELAY == FALSE) {DELAY = TRUE;} else {DELAY = FALSE;}
      Serial.println(DELAY ? "Delay ON" : "Delay OFF");
    }
    else if(strcmp(command, "delay -") == 0                          || strcmp(command, "-") == 0)
    {
      Serial.print("Delay microseconds: ");
      if (DELAYUS != 0 && DELAYUS > 1000) DELAYUS-=1000;
      else if (DELAYUS != 0 && DELAYUS > 100) DELAYUS-=100;
      else if (DELAYUS != 0) DELAYUS-=10;
      Serial.println(DELAYUS,DEC);
    }
    else if(strcmp(command, "delay +") == 0                          || strcmp(command, "+") == 0)
    {
      Serial.print("Delay microseconds: ");
      if (DELAYUS < 100) DELAYUS+=10;
      else if (DELAYUS <= 1000) DELAYUS+=100;
      else DELAYUS+=1000;
      Serial.println(DELAYUS,DEC);
    }
    else if(strcmp(command, "pullups") == 0                          || strcmp(command, "r") == 0)
    {
      if (JTAG_PULLUP == FALSE) {JTAG_PULLUP = TRUE;} else {JTAG_PULLUP = FALSE;}
      Serial.println(JTAG_PULLUP ? "Pullups ON" : "Pullups OFF");
    }
    else if(strcmp(command, "gpio read") == 0                         || strcmp(command, "g") == 0)
    {
      Serial.println("Pin states (all as INPUT):");
      for(int pin=0;pin<pinslen;pin++) {
        pinMode(pins[pin], INPUT);
        digitalWrite(pins[pin], LOW); // no pullup
        delayMicroseconds(100);
        Serial.print("  ");
        Serial.print(pinnames[pin]);
        Serial.print("=");
        Serial.println(digitalRead(pins[pin]) ? "HIGH" : "LOW");
      }
      Serial.println("With pullup:");
      for(int pin=0;pin<pinslen;pin++) {
        pinMode(pins[pin], INPUT);
        digitalWrite(pins[pin], HIGH); // pullup
        delayMicroseconds(100);
        Serial.print("  ");
        Serial.print(pinnames[pin]);
        Serial.print("=");
        Serial.println(digitalRead(pins[pin]) ? "HIGH" : "LOW");
      }
      int a0 = analogRead(A0);
      Serial.print("  A0(TDO) raw=");
      Serial.print(a0);
      Serial.print(" ~");
      Serial.print((a0 * 3200) / 1023);
      Serial.println("mV");
    }
    else if(strcmp(command, "direct test") == 0                       || strcmp(command, "t") == 0)
    {
      // Direct test with known pins: D1=TRST D5=TCK D7=TMS D6=TDI
      // TDO on A0 (analog) — BCM7213 JTAG is 1.8V, digitalRead can't see it
      int p_trst = D1, p_tck = D5, p_tms = D7, p_tdi = D6;
      const int TDO_THRESH = 300; // ~0.94V — separates 0V (LOW) from 1.4V (HIGH)
      #define READ_TDO() (analogRead(A0) > TDO_THRESH ? 1 : 0)

      // Setup outputs
      pinMode(p_tck, OUTPUT); digitalWrite(p_tck, LOW);
      pinMode(p_tms, OUTPUT); digitalWrite(p_tms, LOW);
      pinMode(p_tdi, OUTPUT); digitalWrite(p_tdi, LOW);
      pinMode(p_trst, OUTPUT);
      // A0 is analog-only, no pinMode needed

      // Hard TRST pulse: drive LOW 50ms, then HIGH 50ms
      Serial.print("TRST pulse...");
      digitalWrite(p_trst, LOW);
      delay(50);
      // Check: can we actually read TRST back?
      pinMode(p_trst, INPUT);
      delayMicroseconds(10);
      Serial.print(" TRST(float)=");
      Serial.print(digitalRead(p_trst) ? "H" : "L");
      pinMode(p_trst, OUTPUT);
      digitalWrite(p_trst, HIGH);
      delay(50);
      pinMode(p_trst, INPUT);
      delayMicroseconds(10);
      Serial.print(" TRST(driven)=");
      Serial.println(digitalRead(p_trst) ? "H" : "L");
      pinMode(p_trst, OUTPUT);
      digitalWrite(p_trst, HIGH);

      // Check TDO now (analog)
      int raw_tdo = analogRead(A0);
      Serial.print("TDO after TRST pulse: raw=");
      Serial.print(raw_tdo);
      Serial.print(" (~");
      Serial.print((raw_tdo * 3200) / 1023);
      Serial.print("mV) => ");
      Serial.println(raw_tdo > TDO_THRESH ? "HIGH" : "LOW");

      // TAP reset via TMS (5 clocks TMS=1)
      Serial.print("TAP reset via TMS... ");
      for(int i=0; i<5; i++) {
        digitalWrite(p_tms, HIGH);
        delayMicroseconds(DELAYUS);
        digitalWrite(p_tck, LOW);
        delayMicroseconds(DELAYUS);
        digitalWrite(p_tck, HIGH);
        delayMicroseconds(DELAYUS);
      }
      raw_tdo = analogRead(A0);
      Serial.print("TDO raw=");
      Serial.print(raw_tdo);
      Serial.println(raw_tdo > TDO_THRESH ? " HIGH" : " LOW");

      // Navigate to Shift-DR: TMS sequence 0,1,0,0 from Test-Logic-Reset
      // Reset->Idle(0) Idle->SelectDR(1) SelectDR->CaptureDR(0) CaptureDR->ShiftDR(0)
      int tms_seq[] = {0, 1, 0, 0};
      Serial.print("Shift-DR... ");
      for(int i=0; i<4; i++) {
        digitalWrite(p_tms, tms_seq[i]);
        delayMicroseconds(DELAYUS);
        digitalWrite(p_tck, LOW);
        delayMicroseconds(DELAYUS);
        digitalWrite(p_tck, HIGH);
        delayMicroseconds(DELAYUS);
      }

      // Read 32 bits from TDO (IDCODE or BYPASS)
      uint32_t idcode = 0;
      Serial.print("Reading 32 bits: ");
      for(int j=0; j<32; j++) {
        digitalWrite(p_tdi, LOW);
        delayMicroseconds(DELAYUS);
        digitalWrite(p_tck, LOW);
        delayMicroseconds(DELAYUS);
        int bit = READ_TDO();
        Serial.print(bit);
        if(bit) idcode |= ((uint32_t)1) << j;
        digitalWrite(p_tck, HIGH);
        delayMicroseconds(DELAYUS);
      }
      Serial.println();
      Serial.print("IDCODE: 0x");
      Serial.println(idcode, HEX);

      // Read 32 more bits
      uint32_t idcode2 = 0;
      for(int j=0; j<32; j++) {
        digitalWrite(p_tdi, LOW);
        delayMicroseconds(DELAYUS);
        digitalWrite(p_tck, LOW);
        delayMicroseconds(DELAYUS);
        int bit = READ_TDO();
        if(bit) idcode2 |= ((uint32_t)1) << j;
        digitalWrite(p_tck, HIGH);
        delayMicroseconds(DELAYUS);
      }
      Serial.print("Next 32: 0x");
      Serial.println(idcode2, HEX);

      // BYPASS test: send 1s into TDI, check if they come out on TDO
      // In BYPASS (1-bit register), TDI appears on TDO after 1 clock
      Serial.print("BYPASS test (TDI=1): ");
      for(int j=0; j<16; j++) {
        digitalWrite(p_tdi, HIGH);
        delayMicroseconds(DELAYUS);
        digitalWrite(p_tck, LOW);
        delayMicroseconds(DELAYUS);
        Serial.print(READ_TDO());
        digitalWrite(p_tck, HIGH);
        delayMicroseconds(DELAYUS);
      }
      Serial.println();

      // Now send alternating 1010... pattern
      Serial.print("Alternating TDI:     ");
      for(int j=0; j<16; j++) {
        digitalWrite(p_tdi, j & 1);
        delayMicroseconds(DELAYUS);
        digitalWrite(p_tck, LOW);
        delayMicroseconds(DELAYUS);
        Serial.print(READ_TDO());
        digitalWrite(p_tck, HIGH);
        delayMicroseconds(DELAYUS);
      }
      Serial.println();
      #undef READ_TDO
    }
    else if(strcmp(command, "diag") == 0                              || strcmp(command, "j") == 0)
    {
      // Full JTAG diagnostic
      // Pins: GPIO5=TRST, GPIO14=TCK, GPIO13=TMS, GPIO12=TDI, A0=TDO(analog)
      // D2(GPIO4) = free, used here to try nSRST on pin 11 or 12
      int p_trst = D1, p_tck = D5, p_tms = D7, p_tdi = D6;
      int p_srst = D2; // free pin for nSRST experiment
      const int TH = 300;

      pinMode(p_tck, OUTPUT); digitalWrite(p_tck, LOW);
      pinMode(p_tms, OUTPUT); digitalWrite(p_tms, HIGH);
      pinMode(p_tdi, OUTPUT); digitalWrite(p_tdi, LOW);
      pinMode(p_trst, OUTPUT); digitalWrite(p_trst, HIGH);

      // === TEST 1: TDO wiggle test (50 clocks TMS=1, TRST=H) ===
      Serial.println("=== TEST 1: TDO wiggle (50 clk, TMS=1, TRST=H) ===");
      int mn=1024, mx=0;
      long sum=0;
      for(int i=0;i<50;i++){
        digitalWrite(p_tck,LOW); delayMicroseconds(DELAYUS);
        int v=analogRead(A0); if(v<mn)mn=v; if(v>mx)mx=v; sum+=v;
        digitalWrite(p_tck,HIGH); delayMicroseconds(DELAYUS);
      }
      Serial.print("  TDO min="); Serial.print(mn);
      Serial.print(" max="); Serial.print(mx);
      Serial.print(" avg="); Serial.println(sum/50);

      // === TEST 2: TDO wiggle (50 clocks TMS=0) ===
      Serial.println("=== TEST 2: TDO wiggle (50 clk, TMS=0) ===");
      digitalWrite(p_tms, LOW);
      mn=1024; mx=0; sum=0;
      for(int i=0;i<50;i++){
        digitalWrite(p_tck,LOW); delayMicroseconds(DELAYUS);
        int v=analogRead(A0); if(v<mn)mn=v; if(v>mx)mx=v; sum+=v;
        digitalWrite(p_tck,HIGH); delayMicroseconds(DELAYUS);
      }
      Serial.print("  TDO min="); Serial.print(mn);
      Serial.print(" max="); Serial.print(mx);
      Serial.print(" avg="); Serial.println(sum/50);

      // === TEST 3: TRST=LOW (TAP reset), read TDO ===
      Serial.println("=== TEST 3: TRST=LOW (hold reset) ===");
      digitalWrite(p_trst, LOW); delay(10);
      Serial.print("  TDO raw="); Serial.println(analogRead(A0));

      // === TEST 4: no TRST, only TMS reset -> IDCODE ===
      Serial.println("=== TEST 4: TMS-only reset -> IDCODE ===");
      pinMode(p_trst, INPUT); // float TRST, don't drive it
      digitalWrite(p_tms, HIGH);
      for(int i=0;i<10;i++){
        digitalWrite(p_tck,LOW); delayMicroseconds(DELAYUS);
        digitalWrite(p_tck,HIGH); delayMicroseconds(DELAYUS);
      }
      // Shift-DR: TMS 0,1,0,0
      int seq4[]={0,1,0,0};
      for(int i=0;i<4;i++){
        digitalWrite(p_tms,seq4[i]); delayMicroseconds(DELAYUS);
        digitalWrite(p_tck,LOW); delayMicroseconds(DELAYUS);
        digitalWrite(p_tck,HIGH); delayMicroseconds(DELAYUS);
      }
      uint32_t id4=0;
      Serial.print("  bits: ");
      for(int j=0;j<32;j++){
        digitalWrite(p_tdi,LOW); delayMicroseconds(DELAYUS);
        digitalWrite(p_tck,LOW); delayMicroseconds(DELAYUS);
        int v=analogRead(A0); int b=v>TH?1:0;
        Serial.print(b);
        if(b) id4|=((uint32_t)1)<<j;
        digitalWrite(p_tck,HIGH); delayMicroseconds(DELAYUS);
      }
      Serial.println();
      Serial.print("  IDCODE=0x"); Serial.println(id4,HEX);
      pinMode(p_trst, OUTPUT); digitalWrite(p_trst, HIGH);

      // === TEST 5: nSRST via D2 -> JTAG pin 11 ===
      // User: connect D2 (GPIO4) to JTAG pin 11
      Serial.println("=== TEST 5: nSRST pulse via D2 (connect D2->JTAG pin 11) ===");
      pinMode(p_srst, OUTPUT);
      digitalWrite(p_srst, LOW); delay(100);
      digitalWrite(p_srst, HIGH); delay(100);
      // now try IDCODE with TRST=H
      digitalWrite(p_tms, HIGH);
      for(int i=0;i<5;i++){
        digitalWrite(p_tck,LOW); delayMicroseconds(DELAYUS);
        digitalWrite(p_tck,HIGH); delayMicroseconds(DELAYUS);
      }
      int seq5[]={0,1,0,0};
      for(int i=0;i<4;i++){
        digitalWrite(p_tms,seq5[i]); delayMicroseconds(DELAYUS);
        digitalWrite(p_tck,LOW); delayMicroseconds(DELAYUS);
        digitalWrite(p_tck,HIGH); delayMicroseconds(DELAYUS);
      }
      uint32_t id5=0;
      Serial.print("  bits: ");
      for(int j=0;j<32;j++){
        digitalWrite(p_tdi,LOW); delayMicroseconds(DELAYUS);
        digitalWrite(p_tck,LOW); delayMicroseconds(DELAYUS);
        int v=analogRead(A0); int b=v>TH?1:0;
        Serial.print(b);
        if(b) id5|=((uint32_t)1)<<j;
        digitalWrite(p_tck,HIGH); delayMicroseconds(DELAYUS);
      }
      Serial.println();
      Serial.print("  IDCODE=0x"); Serial.println(id5,HEX);
      pinMode(p_srst, INPUT); // release D2

      // === TEST 6: slow clock (1ms per cycle) ===
      Serial.println("=== TEST 6: slow clock 1ms, TMS reset -> IDCODE ===");
      digitalWrite(p_trst, LOW); delay(50);
      digitalWrite(p_trst, HIGH); delay(50);
      digitalWrite(p_tms, HIGH);
      for(int i=0;i<5;i++){
        digitalWrite(p_tck,LOW); delay(1);
        digitalWrite(p_tck,HIGH); delay(1);
      }
      int seq6[]={0,1,0,0};
      for(int i=0;i<4;i++){
        digitalWrite(p_tms,seq6[i]); delay(1);
        digitalWrite(p_tck,LOW); delay(1);
        digitalWrite(p_tck,HIGH); delay(1);
      }
      uint32_t id6=0;
      Serial.print("  bits: ");
      for(int j=0;j<32;j++){
        digitalWrite(p_tdi,LOW); delay(1);
        digitalWrite(p_tck,LOW); delay(1);
        int v=analogRead(A0); int b=v>TH?1:0;
        Serial.print(b);
        if(b) id6|=((uint32_t)1)<<j;
        digitalWrite(p_tck,HIGH); delay(1);
      }
      Serial.println();
      Serial.print("  IDCODE=0x"); Serial.println(id6,HEX);

      // === TEST 7: D2 digital read of TDO (if still wired) ===
      Serial.println("=== TEST 7: D2 digital read (if wired to TDO) ===");
      pinMode(p_srst, INPUT);
      Serial.print("  D2="); Serial.println(digitalRead(p_srst)?"HIGH":"LOW");
      pinMode(p_srst, INPUT_PULLUP);
      Serial.print("  D2(pullup)="); Serial.println(digitalRead(p_srst)?"HIGH":"LOW");

      Serial.println("=== DONE ===");
    }
    else if(strcmp(command, "help") == 0                             || strcmp(command, "h") == 0)
      help();
    else if(strcmp(command, "list pin names") == 0                   || strcmp(command, "n") == 0)
      list_pin_names();
    else if(strcmp(command, "configure pin") ==  0                   || strcmp(command, "c") == 0)
      configure_pins();
    else
    {
      Serial.println("unknown command");
      help();
    }
    Serial.print("\n> ");
  }
}
