import urequests
import blynklib
from machine import Pin, time_pulse_us
import network
import time

# ==== Configuration ====
SSID = 'Airtel_satu_6657'
PASSWORD = 'air62452'
BLYNK_AUTH = "rfeCWY--vMXAELkPknjIqiMrnBaqzA7U"
GOOGLE_URL = "https://script.google.com/macros/s/AKfycbzeyxkFXLW_6Gg0ZAOdmQqw5XKNvkJfqTEd3HJuPfPcJEKvP8oL64iCogKEnYs8VvEA/exec"

TANK_HEIGHT = 22
PULSES_PER_LITRE = 450.0
MONTHLY_LIMIT = 5.0
EXTRA_CHARGE_PER_LITRE = 5

# ==== WiFi Setup ====
wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.connect(SSID, PASSWORD)
print("Connecting to WiFi...", end="")
while not wifi.isconnected():
    time.sleep(1)
    print(".", end="")
print("\n✅ Connected to WiFi:", wifi.ifconfig())

# ==== Blynk Init ====
blynk = blynklib.Blynk(BLYNK_AUTH)

# ==== Pin Setup ====
trigger = Pin(5, Pin.OUT)
echo = Pin(4, Pin.IN)
buzzer = Pin(14, Pin.OUT)
flow1 = Pin(15, Pin.IN, Pin.PULL_UP)
flow2 = Pin(12, Pin.IN, Pin.PULL_UP)
relay = Pin(13, Pin.OUT)
relay.value(1)  # Motor OFF

# ==== Variables ====
pulse_count_flat1 = 0
pulse_count_flat2 = 0
total_litres_flat1 = 0.0
total_litres_flat2 = 0.0
last_update = time.ticks_ms()
motor_state = False

# ==== Flow Sensor ISRs ====
def count_pulse_flat1(pin):
    global pulse_count_flat1
    pulse_count_flat1 += 1

def count_pulse_flat2(pin):
    global pulse_count_flat2
    pulse_count_flat2 += 1

flow1.irq(trigger=Pin.IRQ_RISING, handler=count_pulse_flat1)
flow2.irq(trigger=Pin.IRQ_RISING, handler=count_pulse_flat2)

# ==== Distance Measurement ====
def measure_distance():
    trigger.off()
    time.sleep_us(2)
    trigger.on()
    time.sleep_us(10)
    trigger.off()
    try:
        duration = time_pulse_us(echo, 1, 500000)
        distance = (duration / 2) / 29.1
        return round(distance, 2)
    except:
        return -1

print("🟢 Smart Water Monitoring Started...")

# ==== Main Loop ====
while True:
    if not wifi.isconnected():
        print("⚠ Reconnecting WiFi...")
        wifi.connect(SSID, PASSWORD)
        while not wifi.isconnected():
            time.sleep(1)
        print("✅ WiFi Reconnected")

    distance = measure_distance()

    if distance == -1 or distance > 400:
        water_level_cm = 0
        water_level_percent = 0
        buzzer.on()
        relay.value(1)  # motor off on error
        motor_state = False
    else:
        water_level_cm = max(0, TANK_HEIGHT - distance)
        water_level_percent = max(0, min(100, (water_level_cm / TANK_HEIGHT) * 100))
        print("💧 Water Level: {:.2f} cm | {:.2f}%".format(water_level_cm, water_level_percent))

        if water_level_percent <= 8:
            buzzer.on()
            relay.value(0)  # Motor ON
            motor_state = True
        elif water_level_percent >= 90:
            buzzer.on()
            relay.value(1)  # Motor OFF
            motor_state = False
        else:
            buzzer.off()
            relay.value(0 if motor_state else 1)  # maintain previous state

    current_time = time.ticks_ms()
    if time.ticks_diff(current_time, last_update) >= 2000:  # every 2 seconds
        litres1 = pulse_count_flat1 / PULSES_PER_LITRE
        litres2 = pulse_count_flat2 / PULSES_PER_LITRE
        total_litres_flat1 += litres1
        total_litres_flat2 += litres2
        pulse_count_flat1 = 0
        pulse_count_flat2 = 0
        last_update = current_time

        extra1 = max(0, total_litres_flat1 - MONTHLY_LIMIT)
        extra2 = max(0, total_litres_flat2 - MONTHLY_LIMIT)
        charge1 = extra1 * EXTRA_CHARGE_PER_LITRE
        charge2 = extra2 * EXTRA_CHARGE_PER_LITRE

        print("🚰 Flat 1: {:.2f} L | Extra: {:.2f} L | ₹{:.2f}".format(total_litres_flat1, extra1, charge1))
        print("🚰 Flat 2: {:.2f} L | Extra: {:.2f} L | ₹{:.2f}".format(total_litres_flat2, extra2, charge2))

        # Send to Google Sheets
        try:
            response = urequests.post(GOOGLE_URL, json={
                "level_cm": "{:.2f}".format(water_level_cm),
                "level_percent": "{:.2f}".format(water_level_percent),
                "flat1": "{:.2f}".format(total_litres_flat1),
                "flat2": "{:.2f}".format(total_litres_flat2),
                "extra1": "{:.2f}".format(extra1),
                "charge1": "{:.2f}".format(charge1),
                "extra2": "{:.2f}".format(extra2),
                "charge2": "{:.2f}".format(charge2)
            })
            print("✅ Google Sheets updated:", response.text)
            response.close()
        except Exception as e:
            print("❌ Google Sheets error:", e)

        # Send to Blynk
        try:
            blynk.virtual_write(0, round(water_level_percent, 2))
            blynk.virtual_write(1, round(total_litres_flat1, 2))
            blynk.virtual_write(2, round(total_litres_flat2, 2))
            blynk.virtual_write(3, round(charge1, 2))
            blynk.virtual_write(4, round(charge2, 2))
            print("✅ Data sent to Blynk")1
        except Exception as e:
            print("❌ Blynk error:", e)

    blynk.run()
    time.sleep(0.1)
