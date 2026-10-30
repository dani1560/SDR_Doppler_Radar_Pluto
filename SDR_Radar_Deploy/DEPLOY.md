# Deploying the radar on another laptop

This guide sets up the SDR Doppler radar on a new Windows 10/11 laptop: the Python version (drivers,
packages) and the GNU Radio version (radioconda). It takes about 30 minutes and needs an internet
connection once.

## What you need

- Windows 10 or 11 laptop with two free USB ports
- The PlutoSDR with both antennas (and the SMA extension cable)
- The Arduino Nano with the display, already programmed (optional)
- This project folder (`SDR_Radar_Deploy`)

The Arduino keeps its program when unplugged. A Nano that already works does **not** need to be programmed
again on the new laptop, so the Arduino IDE is only needed to change the sketch.

## Step 1: Copy the project folder

Use either way:

- **USB stick:** copy the whole `SDR_Radar_Deploy` folder (about 35 MB, it includes the drivers) to the
  new laptop, e.g. to `Documents`.
- **GitHub:** open the repository page, click **Code → Download ZIP**, unzip it, and open
  `SDR_Radar_Deploy`. With Git installed you can instead run
  `git clone <repository URL>`.

Keep all the files together. `START_RADAR.bat` needs the `.py` files, `drivers/` and `speed_alarm/`
next to it.

## Step 2: Install Python

1. Download **Python 3.10 or newer** from <https://www.python.org/downloads/>.
2. Run the installer and tick **"Add python.exe to PATH"** on the first screen, then click **Install Now**.

If you skip this, `START_RADAR.bat` tells you and opens the download page.

## Step 3: First run of the launcher

1. **Do not plug in the Pluto yet.**
2. Double-click **`START_RADAR.bat`**. On the first run it:
   - installs the Python packages (needs internet, about 2 minutes)
   - sees that the Pluto driver (libiio) is missing and asks you to keep the Pluto unplugged, then runs
     the two driver installers from `drivers/`. Accept the Windows admin prompts and click through
     with the default options.
3. When it says `PlutoSDR not found`, plug the Pluto into its **middle** micro-USB port (USB symbol,
   not the power port). Wait about 30 seconds until the **Ready** LED is on and a `PlutoSDR` drive
   appears, then press a key. The radar starts, and the window shows:

   ```
   PlutoSDR : connected
   Arduino  : COM5          (any COM number)
   ```

If the driver installers did not run, double-click `TOOLS.bat` and choose **6**.

## Step 4: Connect the Arduino (optional)

Plug in the Nano. If the launcher shows `Arduino : not found`:

- Clone Nanos need the **CH340 driver**: download `CH341SER.EXE` from <https://www.wch-ic.com>, install
  it, then unplug and replug the Nano.
- Some USB cables only charge. Try another cable.

## Step 5: Install GNU Radio (radioconda)

1. Download the Windows installer **`radioconda-<version>-Windows-x86_64.exe`** (about 630 MB) from
   <https://github.com/radioconda/radioconda-installer/releases> (tested: 2025.03.14, GNU Radio 3.10.12).
2. Run it. "Just Me" (installs to `C:\Users\<you>\radioconda`) or "All Users"
   (`C:\ProgramData\radioconda`) both work. **Untick** "Add to PATH" and "Register as default Python",
   so the Python version keeps using its own Python.
3. The first run of `START_GNURADIO.bat` installs **pyserial** (for the Arduino display) automatically.

radioconda contains GNU Radio, the PlutoSDR blocks (gr-iio, libiio 0.26) and its own Python, so nothing
else is needed.

## Step 6: Run

**GNU Radio version (main demo):** double-click **`START_GNURADIO.bat`**. A window opens with the sliders
(Frequency, Max speed, Speed limit, RX gain, TX attenuation, Min signal), the live and held speed, the
Doppler spectrum and the waterfall. Defaults: 2482 MHz, max speed 50 km/h, speed limit 10 km/h, TX
attenuation 20 dB, Min signal 15 dB, RX gain 30 dB. Slider changes are not saved; to change a default,
open `EDIT_GNURADIO.bat`, double-click the slider block, set Default Value, OK, Ctrl+S. Stand still for 3 s while it learns the background. Close the window to stop; the
transmitter is muted automatically. To show the block diagram, double-click **`EDIT_GNURADIO.bat`**
(GNU Radio Companion opens `gnuradio/doppler_radar.grc`; its Run button starts the radar too).

**Python version (backup):** double-click **`START_RADAR.bat`**. It uses the same defaults (speed limit
10 km/h). To change them, open `START_RADAR.bat` in Notepad and edit `LIMIT`, `MAXKMH`, `FREQ_MHZ`,
`MAX_SPEED`, `TX_GAIN` and `MIN_SIGNAL` near the top.

To test or for walking demos, double-click **`TOOLS.bat`**:

| TOOLS.bat option | Expected result |
|---|---|
| **3** Test the Pluto | Plot with a strong peak at **+100 kHz**. Close the window. |
| **4** Test the Arduino display | Display shows `15`, `35`, then `72` blinking |
| **1** Run radar (walking) | Walk toward the antennas: speed on screen and LED, beeps from the laptop; captures over 10 km/h |
| **2** Run radar (cars) | Captures over 50 km/h |

The LED shows whole km/h (`45`); the screen and the log show one decimal (`45.3`).

Close the radar's plot window to stop it. The terminal then shows `Radar stopped. TX is off.`

## Programming a new Nano (only if needed)

1. Install **Arduino IDE 2** from <https://www.arduino.cc/en/software> and close it after the first start.
2. Wire the Nano (see `README.md`, section "Arduino buzzer + LED display").
3. Double-click `TOOLS.bat` and choose **5**. It installs the board support and the TM1637 library and uploads
   the sketch. Success: the display shows `88:88`, then `----`.

## Antenna placement

```
Pluto Tx -- antenna, upright
Pluto Rx -- extension cable (0.5-1 m) -- antenna, upright
```

- Point both antennas along the path of the target. Speed is measured along the line of sight, so a car
  passing at an angle reads lower.
- No ceiling fans or moving objects in front of the antennas.
- `CLIPPING` on screen: move the antennas further apart.

## Common problems

| Problem | Fix |
|---|---|
| `Python is not installed` | Step 2. Tick "Add python.exe to PATH", then open the launcher again |
| `ERROR: installing the Python packages failed` | Check the internet connection and run the launcher again |
| GNU Radio window: `No Pluto device found` | Close other radar windows; the flowgraph uses `ip:192.168.2.1` (variable `pluto_uri`) |
| Only strong targets detected, noisy spectrum | Tighten all SMA connectors by hand; keep the Pluto, cables and antennas off the laptop and away from fans |
| `PlutoSDR : NOT FOUND` | Middle USB port, wait 30 s, close other radar windows, `TOOLS.bat` option 6 for drivers |
| `Arduino : not found` | CH340 driver, other USB cable (Step 4) |
| `Cannot open Arduino port` / `Access is denied` | Close the Arduino IDE and its Serial Monitor |
| Speeds appear with nobody moving | Fans or moving objects in view; point the antennas elsewhere |
| Buzzer quiet or silent | Buzzer between D9 and D10 (or D9 and GND), legs fully in; replug the USB and listen for the chirp |
