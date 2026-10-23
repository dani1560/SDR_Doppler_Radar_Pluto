# SDR_Doppler_Radar_Pluto
Low-cost SDR-based CW Doppler radar using ADALM-PLUTO at 2.48 GHz to measure vehicle speed in real time. Python DSP extracts the Doppler shift via FFT, rejects fan/Wi-Fi clutter, and logs each pass. An Arduino drives a buzzer that grows louder with speed and faster as targets approach, and an LED display holds the last measured speed.
