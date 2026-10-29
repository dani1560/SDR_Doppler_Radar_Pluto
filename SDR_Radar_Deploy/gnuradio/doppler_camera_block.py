"""
Doppler Speed Camera - GNU Radio embedded Python block (source of the epy_block in doppler_radar.grc).

Input : complex Doppler signal at 8 kS/s (the received CW tone mixed to 0 Hz and decimated).
Display: live_text() and held_text() return the readouts; Function Probe blocks poll them for QT GUI Labels.
Processing is shared with the Python radar (../doppler_core.py): clutter map, mirror test,
sub-bin peak, pass tracking, capture over the speed limit, speed_log.csv, Arduino LED/buzzer.
"""
import os
import sys
import numpy as np
from gnuradio import gr


def _import_core():
    """doppler_core.py lives in SDR_Radar_Deploy, one folder above this flowgraph."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:                                   # GRC loads the block source without __file__
        here = os.getcwd()
    for d in (here, os.path.dirname(here), os.getcwd(), os.path.dirname(os.getcwd())):
        if os.path.exists(os.path.join(d, "doppler_core.py")):
            if d not in sys.path:
                sys.path.insert(0, d)
            import doppler_core
            return doppler_core, d
    raise ImportError("doppler_core.py not found: keep the gnuradio folder inside SDR_Radar_Deploy")


CLIP_LEVEL = 0.9    # leakage tone above 90 % of ADC full scale = receiver overload


class blk(gr.sync_block):
    """Doppler Speed Camera: speed in km/h, last-speed hold, capture over the limit, log, Arduino"""

    def __init__(self, freq_mhz=2482.0, max_kmh=220.0, limit_kmh=50.0, alarm_kmh=60.0, arduino_port="auto",
                 pluto_uri="ip:192.168.2.1"):
        gr.sync_block.__init__(self, name="Doppler Speed Camera", in_sig=[np.complex64], out_sig=None)
        # GRC updates these attributes when the sliders move; work() applies them
        self.freq_mhz, self.max_kmh, self.limit_kmh = freq_mhz, max_kmh, limit_kmh
        self.alarm_kmh, self.arduino_port, self.pluto_uri = alarm_kmh, arduino_port, pluto_uri
        self.dc, base = _import_core()
        self.log_file = os.path.join(base, "speed_log.csv")
        self.det = self.cam = None
        self.applied = None
        self.buf = np.zeros(0, np.complex64)
        self.kmh = self.snr = 0.0                       # latest frame, for the display
        self.level = 0.0                                # TX->RX leakage level (1.0 = ADC full scale)
        self.arduino = None

    # --- GNU Radio start/stop --------------------------------------------------------------------
    def start(self):
        self._apply_settings()
        port = str(self.arduino_port).strip()
        if port.lower() == "auto":
            try:
                from arduino_port import find_arduino_port
                port = find_arduino_port() or ""
            except ImportError:
                port = ""
        if port and port.lower() != "none":
            try:
                import serial
                import time
                self.arduino = serial.Serial(port, 115200, timeout=0)
                time.sleep(2)                           # Nano resets when the port opens
                print(f"Doppler camera: sending speed to Arduino on {port}")
            except Exception as e:                      # radar keeps running without the display
                print(f"Doppler camera: Arduino on {port} not available ({e})")
                self.arduino = None
        return True

    def stop(self):
        if self.cam:
            self.cam.finish()                           # log a pass still in progress
        if self.arduino:
            try:
                self.arduino.write(self.cam.arduino_line(0, 0, self.alarm_kmh).encode())
                self.arduino.close()
            except Exception:
                pass
            self.arduino = None
        self._mute_tx()
        return True

    def _mute_tx(self):
        """The PlutoSDR Sink leaves the TX LO on when the flowgraph stops: set -89 dB so nothing radiates."""
        try:
            import iio
            phy = iio.Context(str(self.pluto_uri)).find_device("ad9361-phy")
            phy.find_channel("voltage0", True).attrs["hardwaregain"].value = "-89"
            print("Doppler camera: transmitter muted (-89 dB)")
        except Exception as e:
            print(f"Doppler camera: could not mute the transmitter ({e})")

    # --- settings from the GUI sliders ------------------------------------------------------------
    def _apply_settings(self):
        fc = float(self.freq_mhz) * 1e6
        settings = (fc, float(self.max_kmh), float(self.limit_kmh))
        if settings == self.applied:
            return
        dc = self.dc
        max_doppler = dc.kmh_to_doppler(min(float(self.max_kmh), dc.max_speed_kmh(fc)), fc)
        if self.det is None:
            self.det = dc.Detector(max_doppler)
            self.cam = dc.SpeedCamera(fc, float(self.limit_kmh), self.log_file)
        else:
            if self.applied[0] != fc:
                self.det.reset()                        # new frequency: learn the background again
            self.det.set_max_doppler(max_doppler)
            self.cam.fc, self.cam.limit = fc, float(self.limit_kmh)
        self.applied = settings
        print(f"Doppler camera: {fc / 1e6:g} MHz, speeds up to "
              f"{dc.doppler_to_kmh(self.det.max_doppler_hz, fc):.0f} km/h "
              f"(max possible {dc.max_speed_kmh(fc):.0f}), resolution "
              f"{dc.doppler_to_kmh(dc.FS_DOPPLER / dc.NFFT, fc):.2f} km/h, limit {float(self.limit_kmh):g} km/h")

    # --- processing --------------------------------------------------------------------------------
    def work(self, input_items, output_items):
        self._apply_settings()
        dc, n = self.dc, len(input_items[0])
        self.buf = np.concatenate([self.buf, input_items[0]])
        while len(self.buf) >= dc.FRAME:
            frame, self.buf = self.buf[:dc.FRAME], self.buf[dc.FRAME:]
            p_db, thr_db, noise_db, k, snr, confirmed = self.det(frame.astype(complex))
            kmh, proximity, ended = self.cam.update(self.det, p_db, k, snr, confirmed)
            self.kmh, self.snr = kmh, snr
            self.level = float(np.abs(frame).mean())
            if self.arduino:
                try:
                    self.arduino.write(self.cam.arduino_line(kmh, proximity, float(self.alarm_kmh)).encode())
                except Exception:
                    self.arduino = None
        return n

    # --- display (polled by Function Probe blocks) ---------------------------------------------------
    def live_text(self):
        # receiver overload: more TX power or RX gain than the ADC can take
        warn = "   !! CLIPPING: raise TX attenuation or lower RX gain" if self.level > CLIP_LEVEL else ""
        if self.det is None or not self.det.ready:
            return "learning background ... stand still" + warn
        if self.kmh == 0:
            return "no target" + warn
        way = "approaching" if self.kmh > 0 else "receding"
        flag = "   OVER LIMIT" if abs(self.kmh) > float(self.limit_kmh) else ""
        return f"{abs(self.kmh):.1f} km/h {way}   (signal {self.snr:.0f} dB){flag}{warn}"

    def held_text(self):
        cam = self.cam
        if cam is None or cam.last_kmh is None:
            return "--   (no pass yet)"
        way = "approaching" if cam.last_kmh > 0 else "receding"
        tag = f"   CAPTURED - OVER {float(self.limit_kmh):g} km/h" if cam.last_captured else ""
        return (f"{abs(cam.last_kmh):.1f} km/h {way} at {cam.last_time}{tag}   |   "
                f"top {cam.top_kmh:.1f} km/h, captured {cam.n_captured}")
