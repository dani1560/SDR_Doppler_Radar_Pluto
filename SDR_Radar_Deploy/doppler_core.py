"""
Doppler radar processing shared by the Python radar (02_doppler_radar.py) and the GNU Radio flowgraph
(gnuradio/doppler_radar.grc).

Input: the received CW tone, mixed down to 0 Hz and decimated to FS_DOPPLER (8 kS/s), in frames of
FRAME samples (64 ms). Detector finds the Doppler peak; SpeedCamera turns it into km/h, tracks each
pass, holds its peak speed, captures passes over the speed limit and logs them.
"""
from datetime import datetime
from pathlib import Path
import numpy as np

C = 3e8
FS_DOPPLER = 8000         # Doppler sample rate (Hz)
FRAME = 512               # samples per frame = 64 ms
NFFT = 4096               # 0.5 s window -> 1.95 Hz bins

# --- Detection settings ---
MIN_DOPPLER_HZ = 15       # ignore |fd| below this (TX leakage; 3.3 km/h at 2.482 GHz)
MAX_DOPPLER_LIMIT_HZ = 3400   # the 8 kS/s chain passes up to ~3.5 kHz (740 km/h at 2.482 GHz)
DETECT_DB      = 15       # peak must be this far above the noise floor
STRONG_DB      = 40       # SNR treated as "very close" (proximity 100 %)
MIRROR_DB      = 6        # peak must beat its mirror (-fd) by this much; rejects fans / vibration
CONFIRM_FRAMES = 2        # consecutive detections needed before reporting a target
# Clutter map: the Pluto has spurs at multiples of ~9.8 Hz that fluctuate up to ~24 dB above the noise
# floor. When no target is present, the map learns the mean and spread (dB) of every bin; a peak must
# beat mean + CLUTTER_DB + CLUTTER_K * spread of its own bin. Quiet bins keep the DETECT_DB threshold,
# spur bins get a higher one (~31 dB). Moving targets change bin, spurs never do.
CLUTTER_FRAMES = 60       # ~4 s averaging time of the clutter map
CLUTTER_DB     = 3        # margin above the learned mean of the bin
CLUTTER_K      = 2        # ... plus this many standard deviations of the bin
CLUTTER_RISE_DB = 3       # max rise per update: a short burst (antenna bumped) cannot blind the radar
LEARN_FRAMES   = 30       # ~2 s of learning after the 0.5 s window has filled, before detecting
FREEZE_DB      = 3        # bins this far above their threshold are not learned into the map
CANDIDATES     = 5        # peaks checked per frame (people, limbs, vehicles can be in view together)

# --- Last-speed hold ---
PASS_END_FRAMES = 16      # ~1 s without target ends a pass
PASS_MIN_FRAMES = 3       # a pass needs this many detections to count
LOG_HEADER = "date,time,speed_kmh,direction,limit_kmh,captured"


def doppler_to_kmh(fd, fc):
    """Doppler shift fd (Hz) at carrier fc (Hz) -> radial speed in km/h."""
    return fd * C / (2 * fc) * 3.6


def kmh_to_doppler(kmh, fc):
    return kmh / 3.6 * 2 * fc / C


def max_speed_kmh(fc):
    """Highest speed the 8 kS/s Doppler chain can measure at carrier fc."""
    return doppler_to_kmh(MAX_DOPPLER_LIMIT_HZ, fc)


def peak_offset(p_db, k):
    """Sub-bin position of the peak at bin k (parabola through k-1, k, k+1), in bins (-0.5..0.5)."""
    a, b, c = p_db[k - 1], p_db[k], p_db[k + 1]
    curve = a - 2 * b + c
    return float(np.clip(0.5 * (a - c) / curve, -0.5, 0.5)) if curve < 0 else 0.0


class Detector:
    """Spectrum of the last 0.5 s, clutter map and peak detection; call once per FRAME samples."""

    def __init__(self, max_doppler_hz=1000.0):
        self.window = np.hanning(NFFT)
        self.freqs = np.fft.fftshift(np.fft.fftfreq(NFFT, 1 / FS_DOPPLER))
        self.set_max_doppler(max_doppler_hz)
        self.reset()

    def set_max_doppler(self, hz):
        """Search |fd| from MIN_DOPPLER_HZ up to hz (limited to what the 8 kS/s chain passes)."""
        self.max_doppler_hz = float(np.clip(hz, MIN_DOPPLER_HZ * 2, MAX_DOPPLER_LIMIT_HZ))
        self.band = (np.abs(self.freqs) >= MIN_DOPPLER_HZ) & (np.abs(self.freqs) <= self.max_doppler_hz)

    def reset(self):
        """Forget everything and learn the background again (e.g. after changing the frequency)."""
        self.history = np.zeros(NFFT, complex)
        self.frame = self.learned = self.hits = 0
        self.clutter_db = np.full(NFFT, -300.0)          # clutter map: mean (dB) of every bin
        self.clutter_var = np.zeros(NFFT)                # ... and its variance (dB^2)

    @property
    def ready(self):
        return self.learned >= LEARN_FRAMES

    def __call__(self, y):
        """Add one frame; return (p_db, thr_db, noise_db, k, snr, confirmed)."""
        self.history = np.concatenate([self.history[len(y):], y])
        x = self.history - self.history.mean()          # remove TX leakage (DC)
        spec = np.fft.fftshift(np.fft.fft(x * self.window)) / NFFT
        p_db = 10 * np.log10(np.abs(spec) ** 2 + 1e-30)
        self.frame += 1
        band = self.band

        # threshold per bin: above the noise floor AND above the learned background of that bin
        noise_db = np.median(p_db[band])
        thr_db = np.maximum(noise_db + DETECT_DB,
                            self.clutter_db + CLUTTER_DB + CLUTTER_K * np.sqrt(self.clutter_var))
        excess = p_db - thr_db
        idx = np.flatnonzero(band)
        k = idx[np.argmax(excess[idx])]                  # strongest peak relative to its threshold
        hit = False
        if self.ready:
            # several people / limbs can be in view: take the strongest candidate that passes the mirror test
            for c in idx[np.argsort(excess[idx])[::-1][:CANDIDATES]]:
                if excess[c] < 0:
                    break
                km = NFFT - c                           # bin of the mirror frequency -fd
                if p_db[c] - p_db[max(km - 2, 0):km + 3].max() >= MIRROR_DB:   # +-2 bins tolerance
                    k, hit = c, True
                    break
        snr = p_db[k] - noise_db
        self.hits = self.hits + 1 if hit else 0

        if self.frame > NFFT // len(y):                 # window full: update the clutter map
            self.learned += 1
            if self.learned == 1:
                self.clutter_db, self.clutter_var = p_db.copy(), np.full(NFFT, 25.0)   # 5 dB spread
            else:
                # freeze bins (and +-2 neighbours) holding a strong echo, so targets are never learned
                strong = np.convolve(excess > FREEZE_DB, np.ones(5), "same") > 0 if self.ready else \
                    np.zeros(NFFT, bool)
                a = np.where(strong, 0.0, max(1 / CLUTTER_FRAMES, 1 / self.learned))
                dev = p_db - self.clutter_db
                self.clutter_db += a * np.minimum(dev, CLUTTER_RISE_DB)            # slow rise, fast fall
                self.clutter_var += a * (np.clip(dev, -30, 10) ** 2 - self.clutter_var)
        return p_db, thr_db, noise_db, k, snr, self.hits >= CONFIRM_FRAMES


def prepare_log(log_file):
    """Create the CSV log, or add the limit/captured columns to a log from an older version."""
    log_file = Path(log_file)
    if not log_file.exists():
        log_file.write_text(LOG_HEADER + "\n")
        return
    lines = log_file.read_text().splitlines()
    if lines and lines[0] != LOG_HEADER:
        log_file.write_text("\n".join([LOG_HEADER] + [l + ",," for l in lines[1:] if l]) + "\n")


def log_pass(log_file, kmh, limit):
    """Append one pass to the CSV log; return (time string, captured)."""
    now = datetime.now()
    direction = "approaching" if kmh > 0 else "receding"
    captured = abs(kmh) > limit
    with Path(log_file).open("a") as fh:
        fh.write(f"{now:%Y-%m-%d},{now:%H:%M:%S},{abs(kmh):.1f},{direction},{limit:g},"
                 f"{'yes' if captured else 'no'}\n")
    print(f"[{now:%H:%M:%S}] pass: {abs(kmh):.1f} km/h {direction}"
          + (f"  ** CAPTURED: over {limit:g} km/h **" if captured else ""))
    return f"{now:%H:%M:%S}", captured


class SpeedCamera:
    """Live speed, pass tracking, last-speed hold and capture. Call update() once per frame."""

    def __init__(self, fc, limit, log_file):
        self.fc, self.limit, self.log_file = fc, limit, log_file
        self.recent = []
        self.pass_peak, self.pass_frames, self.lost_frames = 0.0, 0, 0   # current pass
        self.last_kmh, self.last_time, self.last_captured = None, "", False   # last completed pass
        self.n_captured, self.top_kmh = 0, 0.0                            # this session
        prepare_log(log_file)
        self._load_last_pass()

    def _load_last_pass(self):
        """Show the last logged pass at start-up: the Arduino resets when the port opens and forgets it."""
        try:
            rows = [l.split(",") for l in Path(self.log_file).read_text().splitlines()[1:] if l.strip()]
            date, t, kmh, direction, *rest = rows[-1]
            self.last_kmh = float(kmh) * (1 if direction == "approaching" else -1)
            self.last_time = t
            self.last_captured = bool(rest) and rest[-1] == "yes"
        except (OSError, IndexError, ValueError):
            pass                                        # no pass logged yet: display shows ----

    def update(self, det, p_db, k, snr, confirmed):
        """Return (kmh, proximity, pass_ended). kmh is signed (+ approaching), 0 without target."""
        if confirmed:
            fd = det.freqs[k] + peak_offset(p_db, k) * FS_DOPPLER / NFFT   # sub-bin precision
            self.recent = (self.recent + [doppler_to_kmh(fd, self.fc)])[-3:]
            kmh = float(np.median(self.recent))
            # at least 1 %: proximity > 0 is what marks a confirmed target
            proximity = float(np.clip((snr - DETECT_DB) / (STRONG_DB - DETECT_DB), 0.01, 1) * 100)
        else:
            self.recent = []
            kmh, proximity = 0.0, 0.0

        # Track each pass; when it ends, its peak speed becomes the "last speed"
        ended = False
        if proximity > 0:
            if abs(kmh) > abs(self.pass_peak):
                self.pass_peak = kmh
            self.pass_frames += 1
            self.lost_frames = 0
        elif self.pass_frames:
            self.lost_frames += 1
            if self.lost_frames >= PASS_END_FRAMES:
                ended = self._end_pass()
        return kmh, proximity, ended

    def finish(self):
        """Log a pass still in progress (call when stopping)."""
        return self._end_pass()

    def _end_pass(self):
        ended = self.pass_frames >= PASS_MIN_FRAMES
        if ended:
            self.last_kmh = self.pass_peak
            self.last_time, self.last_captured = log_pass(self.log_file, self.pass_peak, self.limit)
            self.n_captured += self.last_captured
            self.top_kmh = max(self.top_kmh, abs(self.pass_peak))
        self.pass_peak, self.pass_frames, self.lost_frames = 0.0, 0, 0
        return ended

    def arduino_line(self, kmh, proximity, max_kmh):
        """Serial line for speed_alarm.ino: S<kmh>,P<proximity>,V<volume>,L<last kmh>,F<captured>."""
        volume = np.clip(abs(kmh) / max_kmh, 0.1, 1.0) * 100 if proximity > 0 else 0
        last = abs(self.last_kmh) if self.last_kmh is not None else -1
        return f"S{abs(kmh):.1f},P{proximity:.0f},V{volume:.0f},L{last:.1f},F{int(self.last_captured)}\n"
