"""
Step 2 - CW Doppler radar with speed alarm (PlutoSDR), Python version.
The GNU Radio version is gnuradio/doppler_radar.grc; both use doppler_core.py for the processing.

TX: CW tone at fc + TONE_HZ
RX: same LO -> mix the tone down to 0 Hz -> decimate to 8 kHz -> FFT
    Doppler shift fd -> speed v = fd * c / (2 * fc)
Alarm: louder with speed, faster beeps with stronger echo (closer target).
Speed camera: each pass's peak speed is held on screen / LED and logged; a pass faster than
--limit is CAPTURED (marked in the log, shown in red, blinking on the LED display).

Run:
  python 02_doppler_radar.py                    # laptop-speaker alarm, limit 60 km/h
  python 02_doppler_radar.py --limit 50         # capture passes faster than 50 km/h
  python 02_doppler_radar.py --max-kmh 10       # bench test (hand / walking)
  python 02_doppler_radar.py --freq-mhz 2450    # carrier frequency (antennas must suit it)
  python 02_doppler_radar.py --max-speed 400    # highest speed searched (up to ~740 km/h at 2.48 GHz)
  python 02_doppler_radar.py --min-signal 15 --tx-gain -10   # long range (default is short range ~1-2 m)
  python 02_doppler_radar.py --port COM5        # also send speed to Arduino Nano
  python 02_doppler_radar.py --port auto        # find the Arduino's COM port automatically
  python 02_doppler_radar.py --no-sound         # display only
  python 02_doppler_radar.py --rx-gain 20       # if "CLIPPING" is shown
Close the plot window (or press Ctrl+C) to stop. TX is always switched off on exit.
"""
import argparse
import signal
import sys
import time
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal as dsp
import adi
from doppler_core import (Detector, SpeedCamera, FS_DOPPLER, NFFT, FRAME, doppler_to_kmh, kmh_to_doppler,
                          max_speed_kmh)

# --- Radar settings ---
PLUTO_URI   = "ip:192.168.2.1"
FREQ_MHZ    = 2482        # carrier, top of the 2.4 GHz ISM band (upper edge of Wi-Fi channel 13)
MAX_SPEED   = 50          # highest speed searched (km/h); --max-speed changes it (up to ~740)
MIN_SIGNAL  = 20          # dB above the noise floor a target needs (measured: still room max 19 dB, walking 24-47 dB)
SAMPLE_RATE = 1_000_000   # Pluto sample rate
TONE_HZ     = 100e3       # TX tone offset (keeps the signal away from RX DC offset)
TX_GAIN_DB  = -30         # TX attenuation (0 = max power); -30 = short range, -10 = long range
TX_OFF_DB   = -89         # TX attenuation used on exit (mutes the LO leakage too)
RX_GAIN_DB  = 30          # RX gain (0..70); lower it if "CLIPPING" appears
DECIM_1, DECIM_2 = 25, 5  # 1 MS/s -> 40 kS/s -> 8 kS/s
RX_BLOCK    = DECIM_1 * DECIM_2 * FRAME   # 64000 samples = 64 ms per read
BLOCK_S     = RX_BLOCK / SAMPLE_RATE
DRAW_S      = 0.25        # redraw the window every 0.25 s; every 64 ms block is still processed
LAG_BLOCKS  = 6           # more blocks behind real time than this = the Pluto dropped data
LOG_FILE = Path(__file__).with_name("speed_log.csv")


class Downconverter:
    """Mix the received tone to 0 Hz and decimate to FS_DOPPLER, keeping filter state between blocks."""

    def __init__(self):
        # RX_BLOCK holds a whole number of tone periods, so one mixer table keeps phase continuous
        self.mixer = np.exp(-2j * np.pi * TONE_HZ * np.arange(RX_BLOCK) / SAMPLE_RATE)
        self.h2 = dsp.firwin(101, 3.5e3, fs=SAMPLE_RATE / DECIM_1)
        self.z2 = np.zeros(len(self.h2) - 1, complex)

    def __call__(self, x):
        x = x * self.mixer
        y = x.reshape(-1, DECIM_1).mean(axis=1)     # stage 1: block average (nulls at multiples of 40 kHz)
        y, self.z2 = dsp.lfilter(self.h2, 1, y, zi=self.z2)
        return y[::DECIM_2]


class AudioAlarm:
    """Laptop-speaker alarm: volume follows speed, beep rate follows proximity."""

    def __init__(self):
        import sounddevice as sd
        self.fs = 44100
        self.volume = 0.0      # 0..1
        self.beeps_per_s = 1.0
        self.pitch = 800.0
        self.phase = 0.0
        self.t = 0.0
        self.stream = sd.OutputStream(samplerate=self.fs, channels=1, callback=self._callback)
        self.stream.start()

    def _callback(self, out, frames, time_info, status):
        t = self.t + np.arange(frames) / self.fs
        gate = ((t * self.beeps_per_s) % 1.0) < 0.5           # 50 % on / off
        ph = self.phase + 2 * np.pi * self.pitch * np.arange(frames) / self.fs
        out[:, 0] = self.volume * gate * np.sin(ph)
        self.phase = (ph[-1] + 2 * np.pi * self.pitch / self.fs) % (2 * np.pi)
        self.t = t[-1] + 1 / self.fs

    def update(self, kmh, proximity, max_kmh):
        if proximity <= 0:
            self.volume = 0.0
            return
        self.volume = float(np.clip(abs(kmh) / max_kmh, 0.1, 1.0))
        self.beeps_per_s = 1.0 + 9.0 * proximity / 100
        self.pitch = 600.0 + 600.0 * min(abs(kmh) / max_kmh, 1.0)

    def close(self):
        self.stream.stop()
        self.stream.close()


def start_pluto(args):
    """Configure the Pluto (TX is started by the caller)."""
    sdr = adi.Pluto(PLUTO_URI)
    sdr.sample_rate = SAMPLE_RATE
    sdr.rx_lo = int(args.fc)
    sdr.tx_lo = int(args.fc)
    sdr.rx_rf_bandwidth = SAMPLE_RATE
    sdr.tx_rf_bandwidth = SAMPLE_RATE
    sdr.gain_control_mode_chan0 = "manual"
    sdr.rx_hardwaregain_chan0 = args.rx_gain
    sdr.tx_hardwaregain_chan0 = args.tx_gain
    sdr.rx_buffer_size = RX_BLOCK
    return sdr


def stop_pluto(sdr):
    """Stop TX and mute the transmitter, even if one of the steps fails."""
    for step in (lambda: sdr.tx_destroy_buffer(),
                 lambda: setattr(sdr, "tx_hardwaregain_chan0", TX_OFF_DB),
                 lambda: sdr.rx_destroy_buffer()):
        try:
            step()
        except Exception as e:
            print(f"Warning while stopping the Pluto: {e}")


def open_arduino(port):
    import serial
    try:
        arduino = serial.Serial(port, 115200, timeout=0)
    except serial.SerialException as e:
        sys.exit(f"Cannot open Arduino port {port}: {e}\n"
                 f"Check the COM port, and close the Arduino IDE / Serial Monitor.")
    time.sleep(2)                                   # Nano resets when the port opens
    print(f"Sending speed to Arduino on {port}")
    return arduino


def run_radar(sdr, alarm, arduino, args):
    down = Downconverter()
    det = Detector(kmh_to_doppler(args.max_speed, args.fc), args.min_signal)
    cam = SpeedCamera(args.fc, args.limit, LOG_FILE)
    freqs = det.freqs

    # --- Display ---
    plt.ion()
    fig, (ax_spec, ax_txt) = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={"height_ratios": [3, 1.6]})
    fig.canvas.manager.set_window_title("SDR Doppler Radar - close this window to stop")
    show = np.abs(freqs) <= det.max_doppler_hz
    kmh_axis = doppler_to_kmh(freqs[show], args.fc)
    line, = ax_spec.plot(kmh_axis, np.zeros(show.sum()))
    thr_line, = ax_spec.plot(kmh_axis, np.zeros(show.sum()), "r--", lw=0.8, label="detection threshold")
    ax_spec.set_title(f"{args.fc / 1e6:.0f} MHz   max {doppler_to_kmh(det.max_doppler_hz, args.fc):.0f} km/h   "
                      f"resolution {doppler_to_kmh(FS_DOPPLER / NFFT, args.fc):.2f} km/h", fontsize=10)
    ax_spec.set_xlabel("Speed (km/h)   [+ approaching / - receding]")
    ax_spec.set_ylabel("Power (dB)")
    ax_spec.set_ylim(-140, -40)
    ax_spec.grid(True)
    ax_spec.legend(loc="upper right")
    ax_txt.axis("off")
    speed_txt = ax_txt.text(0.5, 0.85, "", ha="center", va="center", fontsize=22, family="monospace")
    last_txt = ax_txt.text(0.5, 0.38, "LAST SPEED:  --", ha="center", va="center", fontsize=36,
                           family="monospace", weight="bold", color="navy")
    stats_txt = ax_txt.text(0.5, 0.02, f"limit {args.limit:g} km/h   captured 0", ha="center",
                            va="center", fontsize=14, family="monospace", color="dimgray")

    def show_last_pass():
        """A pass is over: show its peak speed as the held 'last speed'; red if captured."""
        kmh, captured = cam.last_kmh, cam.last_captured
        last_txt.set_text(f"LAST SPEED: {abs(kmh):.1f} km/h  {'→' if kmh > 0 else '←'}  ({cam.last_time})")
        last_txt.set_color("red" if captured else "navy")
        stats_txt.set_text(("CAPTURED - OVER LIMIT!   " if captured else "")
                           + f"limit {args.limit:g} km/h   captured {cam.n_captured}   top {cam.top_kmh:.1f} km/h")
        stats_txt.set_color("red" if captured else "dimgray")

    plt.pause(0.001)                                     # open the window now: the first draw is slow
    next_draw, lost_until = 0.0, 0.0
    t_ref, blocks = None, 0                              # to detect blocks the Pluto had to drop
    try:
        while plt.fignum_exists(fig.number):
            raw = sdr.rx()
            now = time.perf_counter()
            if t_ref is None:
                t_ref = now
            blocks += 1
            # each block is 64 ms of signal: if fewer blocks arrive than time has passed, data was lost
            behind = (now - t_ref) / BLOCK_S - blocks
            if behind > LAG_BLOCKS:
                print(f"WARNING: computer too slow, about {behind:.0f} blocks of radar data lost "
                      f"(plug in the charger / close other programs)")
                lost_until, t_ref, blocks = now + 3.0, now, 0
            clipping = np.max(np.abs(raw)) > 0.9 * 2**11
            p_db, thr_db, noise_db, k, snr, confirmed = det(down(raw / 2**11))
            kmh, proximity, ended = cam.update(det, p_db, k, snr, confirmed)

            if proximity > 0:
                direction = "APPROACHING" if kmh > 0 else "RECEDING"
                msg = f"{abs(kmh):6.1f} km/h  {direction}\nsignal {snr:4.1f} dB  proximity {proximity:3.0f}%"
                color = "red" if abs(kmh) > args.limit else "black"
            else:
                msg = "  ---  no target  ---" if det.ready else "  learning background ...  "
                color = "gray"
            if clipping:
                msg += "\nCLIPPING: lower --rx-gain"
            if now < lost_until:
                msg += "\nDATA LOST: computer too slow (charger?)"
            if ended:
                show_last_pass()

            if alarm:
                alarm.update(kmh, proximity, args.max_kmh)
            if arduino:
                arduino.write(cam.arduino_line(kmh, proximity, args.max_kmh).encode())

            # Redraw only a few times per second: drawing is slow, but every block must be processed
            if now >= next_draw:
                line.set_ydata(p_db[show])
                thr_line.set_ydata(thr_db[show])
                speed_txt.set_text(msg)
                speed_txt.set_color(color)
                plt.pause(0.001)
                next_draw = time.perf_counter() + DRAW_S
    finally:
        cam.finish()                                    # pass still in progress when stopped
        if arduino:                                     # silence the buzzer, keep the last speed shown
            arduino.write(cam.arduino_line(0, 0, args.max_kmh).encode())
        print(f"Session: {cam.n_captured} pass(es) captured over {args.limit:g} km/h, "
              f"top speed {cam.top_kmh:.1f} km/h")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="Arduino serial port, e.g. COM5, or 'auto' to find it")
    ap.add_argument("--max-kmh", type=float, default=60, help="speed at which the alarm is loudest")
    ap.add_argument("--limit", type=float, help="speed limit: faster passes are captured (default: --max-kmh)")
    ap.add_argument("--freq-mhz", type=float, default=FREQ_MHZ, help="carrier frequency in MHz (325..3800)")
    ap.add_argument("--max-speed", type=float, default=MAX_SPEED, help="highest speed searched in km/h")
    ap.add_argument("--min-signal", type=float, default=MIN_SIGNAL,
                    help="min target signal in dB (higher = only closer targets; 15 = longest range, default 20)")
    ap.add_argument("--no-sound", action="store_true", help="disable laptop-speaker alarm")
    ap.add_argument("--tx-gain", type=float, default=TX_GAIN_DB, help="TX attenuation in dB (0 = max, -89 = min)")
    ap.add_argument("--rx-gain", type=float, default=RX_GAIN_DB, help="RX gain in dB (0..70)")
    args = ap.parse_args()
    if args.limit is None:
        args.limit = args.max_kmh
    if not 325 <= args.freq_mhz <= 3800:
        sys.exit("--freq-mhz must be between 325 and 3800 (PlutoSDR range)")
    args.fc = args.freq_mhz * 1e6
    if args.max_speed > max_speed_kmh(args.fc):
        print(f"Note: at {args.freq_mhz:g} MHz the highest measurable speed is {max_speed_kmh(args.fc):.0f} km/h")
        args.max_speed = max_speed_kmh(args.fc)

    port = args.port
    if port and port.lower() == "auto":
        from arduino_port import find_arduino_port
        port = find_arduino_port()
        print(f"Arduino found on {port}" if port else "No Arduino found - running without the LED display")

    # Closing the console window raises SIGBREAK on Windows: turn it into Ctrl+C so cleanup still runs
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)

    sdr = alarm = arduino = None
    try:
        if port:
            arduino = open_arduino(port)
        if not args.no_sound:
            alarm = AudioAlarm()
        sdr = start_pluto(args)
        n = np.arange(RX_BLOCK)
        sdr.tx_cyclic_buffer = True
        sdr.tx(0.5 * np.exp(2j * np.pi * TONE_HZ * n / SAMPLE_RATE) * 2**14)
        time.sleep(1)
        print(f"Radar running at {args.freq_mhz:g} MHz, speeds up to {args.max_speed:.0f} km/h, "
              f"resolution {doppler_to_kmh(FS_DOPPLER / NFFT, args.fc):.2f} km/h")
        run_radar(sdr, alarm, arduino, args)
    except KeyboardInterrupt:
        pass
    finally:
        if sdr:
            stop_pluto(sdr)
        if alarm:
            alarm.close()
        if arduino:
            arduino.close()
        print("Radar stopped. TX is off.")


if __name__ == "__main__":
    main()
