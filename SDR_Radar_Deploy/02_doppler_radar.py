"""
Step 2 - CW Doppler radar with speed alarm (PlutoSDR).

TX: CW tone at CENTER_FREQ + TONE_HZ
RX: same LO -> mix the tone down to 0 Hz -> decimate to 8 kHz -> FFT
    Doppler shift fd -> speed v = fd * c / (2 * fc)
Alarm: louder with speed, faster beeps with stronger echo (closer target).
Speed camera: each pass's peak speed is held on screen / LED and logged; a pass faster than
--limit is CAPTURED (marked in the log, shown in red, blinking on the LED display).

Run:
  python 02_doppler_radar.py                    # laptop-speaker alarm, limit 60 km/h
  python 02_doppler_radar.py --limit 50         # capture passes faster than 50 km/h
  python 02_doppler_radar.py --max-kmh 10       # bench test (hand / walking)
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
from datetime import datetime
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal as dsp
import adi

C = 3e8

# --- Radar settings ---
PLUTO_URI   = "ip:192.168.2.1"
CENTER_FREQ = 2.482e9     # Hz, top of the 2.4 GHz ISM band (upper edge of Wi-Fi channel 13)
SAMPLE_RATE = 1_000_000   # Pluto sample rate
TONE_HZ     = 100e3       # TX tone offset (keeps the signal away from RX DC offset)
TX_GAIN_DB  = -10         # TX attenuation (0 = max power)
TX_OFF_DB   = -89         # TX attenuation used on exit (mutes the LO leakage too)
RX_GAIN_DB  = 30          # RX gain (0..70); lower it if "CLIPPING" appears
DECIM_1, DECIM_2 = 25, 5  # 1 MS/s -> 40 kS/s -> 8 kS/s
FS_DOPPLER  = SAMPLE_RATE / (DECIM_1 * DECIM_2)
RX_BLOCK    = DECIM_1 * DECIM_2 * 512   # 64000 samples = 64 ms per read
NFFT        = 4096        # 0.5 s window -> ~2 Hz bins -> ~0.12 m/s resolution

# --- Detection settings ---
MIN_DOPPLER_HZ = 15       # ignore |fd| below this (TX leakage, ~0.9 m/s = 3.3 km/h)
MAX_DOPPLER_HZ = 1000     # display/search limit (~218 km/h)
DETECT_DB      = 15       # peak must be this far above the noise floor
STRONG_DB      = 40       # SNR treated as "very close" (proximity 100 %)
MIRROR_DB      = 6        # peak must beat its mirror (-fd) by this much; rejects fans / vibration
CONFIRM_FRAMES = 2        # consecutive detections needed before reporting a target

# --- Last-speed hold ---
PASS_END_FRAMES = 16      # ~1 s without target ends a pass
PASS_MIN_FRAMES = 3       # a pass needs this many detections to count
LOG_FILE = Path(__file__).with_name("speed_log.csv")
LOG_HEADER = "date,time,speed_kmh,direction,limit_kmh,captured"


def doppler_to_kmh(fd):
    return fd * C / (2 * CENTER_FREQ) * 3.6


def peak_offset(p_db, k):
    """Sub-bin position of the peak at bin k (parabola through k-1, k, k+1), in bins (-0.5..0.5)."""
    a, b, c = p_db[k - 1], p_db[k], p_db[k + 1]
    curve = a - 2 * b + c
    return float(np.clip(0.5 * (a - c) / curve, -0.5, 0.5)) if curve < 0 else 0.0


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
    """Configure the Pluto and start the cyclic CW transmission."""
    sdr = adi.Pluto(PLUTO_URI)
    sdr.sample_rate = SAMPLE_RATE
    sdr.rx_lo = int(CENTER_FREQ)
    sdr.tx_lo = int(CENTER_FREQ)
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


def prepare_log():
    """Create the CSV log, or add the limit/captured columns to a log from an older version."""
    if not LOG_FILE.exists():
        LOG_FILE.write_text(LOG_HEADER + "\n")
        return
    lines = LOG_FILE.read_text().splitlines()
    if lines and lines[0] != LOG_HEADER:
        LOG_FILE.write_text("\n".join([LOG_HEADER] + [l + ",," for l in lines[1:] if l]) + "\n")


def log_pass(kmh, limit):
    """Append one pass to the CSV log; return (time string, captured)."""
    now = datetime.now()
    direction = "approaching" if kmh > 0 else "receding"
    captured = abs(kmh) > limit
    with LOG_FILE.open("a") as fh:
        fh.write(f"{now:%Y-%m-%d},{now:%H:%M:%S},{abs(kmh):.1f},{direction},{limit:g},"
                 f"{'yes' if captured else 'no'}\n")
    print(f"[{now:%H:%M:%S}] pass: {abs(kmh):.1f} km/h {direction}"
          + (f"  ** CAPTURED: over {limit:g} km/h **" if captured else ""))
    return f"{now:%H:%M:%S}", captured


def run_radar(sdr, alarm, arduino, args):
    down = Downconverter()
    history = np.zeros(NFFT, complex)
    window = np.hanning(NFFT)
    freqs = np.fft.fftshift(np.fft.fftfreq(NFFT, 1 / FS_DOPPLER))
    band = (np.abs(freqs) >= MIN_DOPPLER_HZ) & (np.abs(freqs) <= MAX_DOPPLER_HZ)
    recent = []
    hits = 0
    pass_peak, pass_frames, lost_frames = 0.0, 0, 0     # current pass
    last_kmh, last_captured = None, False                # last completed pass
    n_captured, top_kmh = 0, 0.0                         # this session
    prepare_log()

    # --- Display ---
    plt.ion()
    fig, (ax_spec, ax_txt) = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={"height_ratios": [3, 1.6]})
    fig.canvas.manager.set_window_title("SDR Doppler Radar - close this window to stop")
    show = np.abs(freqs) <= MAX_DOPPLER_HZ
    kmh_axis = doppler_to_kmh(freqs[show])
    line, = ax_spec.plot(kmh_axis, np.zeros(show.sum()))
    thr_line, = ax_spec.plot(kmh_axis, np.zeros(show.sum()), "r--", lw=0.8, label="detection threshold")
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

    def end_pass(kmh):
        """A pass is over: its peak speed becomes the held 'last speed'; capture it if over the limit."""
        nonlocal last_kmh, last_captured, n_captured, top_kmh
        last_kmh = kmh
        last_time, last_captured = log_pass(kmh, args.limit)
        n_captured += last_captured
        top_kmh = max(top_kmh, abs(kmh))
        last_txt.set_text(f"LAST SPEED: {abs(kmh):.1f} km/h  {'→' if kmh > 0 else '←'}  ({last_time})")
        last_txt.set_color("red" if last_captured else "navy")
        stats_txt.set_text(("CAPTURED - OVER LIMIT!   " if last_captured else "")
                           + f"limit {args.limit:g} km/h   captured {n_captured}   top {top_kmh:.1f} km/h")
        stats_txt.set_color("red" if last_captured else "dimgray")

    try:
        while plt.fignum_exists(fig.number):
            raw = sdr.rx()
            clipping = np.max(np.abs(raw)) > 0.9 * 2**11
            y = down(raw / 2**11)
            history = np.concatenate([history[len(y):], y])

            x = history - history.mean()                # remove TX leakage (DC)
            spec = np.fft.fftshift(np.fft.fft(x * window)) / NFFT
            p_db = 20 * np.log10(np.abs(spec) + 1e-15)

            noise_db = np.median(p_db[band])
            k = np.flatnonzero(band)[np.argmax(p_db[band])]
            snr = p_db[k] - noise_db
            km = NFFT - k                                   # bin of the mirror frequency -fd
            mirror_db = p_db[max(km - 2, 0):km + 3].max()   # +-2 bins tolerance

            hit = snr >= DETECT_DB and p_db[k] - mirror_db >= MIRROR_DB
            hits = hits + 1 if hit else 0

            if hits >= CONFIRM_FRAMES:
                fd = freqs[k] + peak_offset(p_db, k) * FS_DOPPLER / NFFT   # sub-bin precision
                recent = (recent + [doppler_to_kmh(fd)])[-3:]
                kmh = float(np.median(recent))
                # at least 1 %: proximity > 0 is what marks a confirmed target below
                proximity = float(np.clip((snr - DETECT_DB) / (STRONG_DB - DETECT_DB), 0.01, 1) * 100)
                direction = "APPROACHING" if kmh > 0 else "RECEDING"
                msg = f"{abs(kmh):6.1f} km/h  {direction}\nsignal {snr:4.1f} dB  proximity {proximity:3.0f}%"
                color = "red" if abs(kmh) > args.limit else "black"
            else:
                recent = []
                kmh, proximity = 0.0, 0.0
                msg, color = "  ---  no target  ---", "gray"
            if clipping:
                msg += "\nCLIPPING: lower --rx-gain"

            # Track each pass; when it ends, its peak speed becomes the "last speed"
            if proximity > 0:
                if abs(kmh) > abs(pass_peak):
                    pass_peak = kmh
                pass_frames += 1
                lost_frames = 0
            elif pass_frames:
                lost_frames += 1
                if lost_frames >= PASS_END_FRAMES:
                    if pass_frames >= PASS_MIN_FRAMES:
                        end_pass(pass_peak)
                    pass_peak, pass_frames, lost_frames = 0.0, 0, 0

            if alarm:
                alarm.update(kmh, proximity, args.max_kmh)
            if arduino:
                volume = np.clip(abs(kmh) / args.max_kmh, 0.1, 1.0) * 100 if proximity > 0 else 0
                last = abs(last_kmh) if last_kmh is not None else -1
                arduino.write(f"S{abs(kmh):.1f},P{proximity:.0f},V{volume:.0f},L{last:.1f},"
                              f"F{int(last_captured)}\n".encode())

            line.set_ydata(p_db[show])
            thr_line.set_ydata(np.full(show.sum(), noise_db + DETECT_DB))
            speed_txt.set_text(msg)
            speed_txt.set_color(color)
            plt.pause(0.001)
    finally:
        if pass_frames >= PASS_MIN_FRAMES:              # pass still in progress when stopped
            end_pass(pass_peak)
        if arduino:                                     # silence the buzzer, keep the last speed shown
            last = abs(last_kmh) if last_kmh is not None else -1
            arduino.write(f"S0,P0,V0,L{last:.1f},F{int(last_captured)}\n".encode())
        print(f"Session: {n_captured} pass(es) captured over {args.limit:g} km/h, top speed {top_kmh:.1f} km/h")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="Arduino serial port, e.g. COM5, or 'auto' to find it")
    ap.add_argument("--max-kmh", type=float, default=60, help="speed at which the alarm is loudest")
    ap.add_argument("--limit", type=float, help="speed limit: faster passes are captured (default: --max-kmh)")
    ap.add_argument("--no-sound", action="store_true", help="disable laptop-speaker alarm")
    ap.add_argument("--tx-gain", type=float, default=TX_GAIN_DB, help="TX attenuation in dB (0 = max, -89 = min)")
    ap.add_argument("--rx-gain", type=float, default=RX_GAIN_DB, help="RX gain in dB (0..70)")
    args = ap.parse_args()
    if args.limit is None:
        args.limit = args.max_kmh

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
        print(f"Radar running at {CENTER_FREQ/1e9:.3f} GHz, Doppler rate {FS_DOPPLER:.0f} Hz, "
              f"resolution {doppler_to_kmh(FS_DOPPLER / NFFT):.2f} km/h")
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
