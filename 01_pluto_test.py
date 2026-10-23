"""
Step 1 - PlutoSDR TX/RX test.

Transmits a CW tone and shows the received spectrum live.
If TX and RX work, you will see a strong peak at +TONE_HZ (TX leaking into RX).

Run:  python 01_pluto_test.py
Close the plot window to stop (TX is switched off automatically).
"""
import time
import numpy as np
import matplotlib.pyplot as plt
import adi

PLUTO_URI   = "ip:192.168.2.1"
CENTER_FREQ = 2.482e9     # Hz, top of the 2.4 GHz ISM band, above the Wi-Fi channels
SAMPLE_RATE = 1e6         # samples/s
TONE_HZ     = 100e3       # TX tone offset from the carrier (avoids DC/LO leakage at 0 Hz)
TX_GAIN_DB  = -10         # TX attenuation in dB (0 = max power, -89 = min)
RX_GAIN_DB  = 50          # RX gain in dB (0..70)
N_SAMPLES   = 2**14

# --- Connect and configure ---
sdr = adi.Pluto(PLUTO_URI)
sdr.sample_rate = int(SAMPLE_RATE)
sdr.rx_lo = int(CENTER_FREQ)
sdr.tx_lo = int(CENTER_FREQ)
sdr.rx_rf_bandwidth = int(SAMPLE_RATE)
sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
sdr.gain_control_mode_chan0 = "manual"
sdr.rx_hardwaregain_chan0 = RX_GAIN_DB
sdr.tx_hardwaregain_chan0 = TX_GAIN_DB
sdr.rx_buffer_size = N_SAMPLES
print(f"Connected to Pluto at {PLUTO_URI}")

# --- Start continuous CW transmission ---
n = np.arange(N_SAMPLES)
tone = 0.5 * np.exp(2j * np.pi * TONE_HZ * n / SAMPLE_RATE) * 2**14
sdr.tx_cyclic_buffer = True
sdr.tx(tone)
time.sleep(1)             # let TX start before reading RX
print(f"Transmitting CW at {(CENTER_FREQ + TONE_HZ)/1e9:.4f} GHz")

# --- Live spectrum ---
freqs = np.fft.fftshift(np.fft.fftfreq(N_SAMPLES, 1 / SAMPLE_RATE)) / 1e3
window = np.hanning(N_SAMPLES)
plt.ion()
fig, ax = plt.subplots(figsize=(10, 5))
line, = ax.plot(freqs, np.zeros(N_SAMPLES))
ax.set_xlabel("Frequency offset (kHz)")
ax.set_ylabel("Power (dBFS)")
ax.set_ylim(-120, 0)
ax.grid(True)
title = ax.set_title("")

try:
    while plt.fignum_exists(fig.number):
        rx = sdr.rx() / 2**11
        spec = np.fft.fftshift(np.fft.fft(rx * window)) / (N_SAMPLES * window.mean())
        p_db = 20 * np.log10(np.abs(spec) + 1e-12)
        line.set_ydata(p_db)
        peak = np.argmax(p_db)
        title.set_text(f"Peak: {freqs[peak]:.1f} kHz at {p_db[peak]:.1f} dBFS "
                       f"(expected +{TONE_HZ/1e3:.0f} kHz)")
        plt.pause(0.05)
finally:
    sdr.tx_destroy_buffer()
    sdr.rx_destroy_buffer()
    print("TX stopped.")
