import urequests
import blynklib
from machine import Pin
import network
import time

# ==== Configuration ====
SSID = 'Airtel_satu_6657'
PASSWORD = 'air62452'
BLYNK_AUTH = "rfeCWY--vMXAELkPknjIqiMrnBaqzA7U"
GOOGLE_URL = "https://script.google.com/macros/s/AKfycbzeyxkFXLW_6Gg0ZAOdmQqw5XKNvkJfqTEd3HJuPfPcJEKvP8oL64iCogKEnYs8VvEA/exec"

PULSES_PER_LITRE = 450.0
MONTHLY_LIMIT = 5.0
EXTRA_CHARGE_PER_LITRE = 5
DEBOUNCE_MS = 5

# ==== WiFi Setup ====
wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.connect(SSID, PASSWORD)
print("Connecting to WiFi...")
while not wifi.isconnected():
    time.sleep(1)
print("✅ Connected:", wifi.ifconfig())

# ==== Blynk Setup ====
blynk = blynklib.Blynk(BLYNK_AUTH, insecure=True, port=80)

# ==== Flow Sensor Pins ====
flow1 = Pin(15, Pin.IN, Pin.PULL_UP)
flow2 = Pin(12, Pin.IN, Pin.PULL_UP)

# ==== Tracking Variables ====
pulse_count_flat1 = 0
pulse_count_flat2 = 0
total_litres_flat1 = 0.0
total_litres_flat2 = 0.0
last_pulse_time_flat1 = 0
last_pulse_time_flat2 = 0

# ==== Timing Variables ====
last_calc_update = time.ticks_ms()
last_sheet_update = time.ticks_ms()
last_blynk_update = time.ticks_ms()

# ==== ISR for Flow Sensors ====
def count_pulse_flat1(pin):
    global pulse_count_flat1, last_pulse_time_flat1
    now = time.ticks_ms()
    if time.ticks_diff(now, last_pulse_time_flat1) > DEBOUNCE_MS:
        pulse_count_flat1 += 1
        last_pulse_time_flat1 = now

def count_pulse_flat2(pin):
    global pulse_count_flat2, last_pulse_time_flat2
    now = time.ticks_ms()
    if time.ticks_diff(now, last_pulse_time_flat2) > DEBOUNCE_MS:
        pulse_count_flat2 += 1
        last_pulse_time_flat2 = now

flow1.irq(trigger=Pin.IRQ_RISING, handler=count_pulse_flat1)
flow2.irq(trigger=Pin.IRQ_RISING, handler=count_pulse_flat2)

print("🟢 Flat Usage Monitor Started...")

# ==== Main Loop ====
while True:
    blynk.run()  # Call first to ensure responsiveness

    current_time = time.ticks_ms()

    # Ensure WiFi is connected
    if not wifi.isconnected():
        wifi.connect(SSID, PASSWORD)

    # Update water usage from pulse count every 2 seconds
    if time.ticks_diff(current_time, last_calc_update) >= 2000:
        litres1 = pulse_count_flat1 / PULSES_PER_LITRE
        litres2 = pulse_count_flat2 / PULSES_PER_LITRE
        total_litres_flat1 += litres1
        total_litres_flat2 += litres2
        pulse_count_flat1 = 0
        pulse_count_flat2 = 0
        last_calc_update = current_time

        extra1 = max(0, total_litres_flat1 - MONTHLY_LIMIT)
        extra2 = max(0, total_litres_flat2 - MONTHLY_LIMIT)
        charge1 = extra1 * EXTRA_CHARGE_PER_LITRE
        charge2 = extra2 * EXTRA_CHARGE_PER_LITRE

        print("🚰 Flat 1: {:.2f} L | Extra: {:.2f} L | ₹{:.2f}".format(total_litres_flat1, extra1, charge1))
        print("🚰 Flat 2: {:.2f} L | Extra: {:.2f} L | ₹{:.2f}".format(total_litres_flat2, extra2, charge2))

    # Send data to Google Sheets every 30 seconds
    if time.ticks_diff(current_time, last_sheet_update) >= 30000:
        try:
            response = urequests.post(GOOGLE_URL, json={
                "flat1": "{:.2f}".format(total_litres_flat1),
                "flat2": "{:.2f}".format(total_litres_flat2),
                "extra1": "{:.2f}".format(extra1),
                "charge1": "{:.2f}".format(charge1),
                "extra2": "{:.2f}".format(extra2),
                "charge2": "{:.2f}".format(charge2),
                "source": "flat"
            })
            print("✅ Sheets updated:", response.text)
            response.close()
            time.sleep(0.5)  # allow system to settle
        except Exception as e:
            print("❌ Sheets error:", e)
        last_sheet_update = current_time

    # Send data to Blynk every 2 seconds
    if time.ticks_diff(current_time, last_blynk_update) >= 2000:
        try:
            blynk.virtual_write(1, round(total_litres_flat1, 2))
            blynk.virtual_write(2, round(total_litres_flat2, 2))
            blynk.virtual_write(3, round(charge1, 2))
            blynk.virtual_write(4, round(charge2, 2))
            
            print("✅ Blynk updated")
        except Exception as e:
            print("❌ Blynk error:", e)
        last_blynk_update = current_time
