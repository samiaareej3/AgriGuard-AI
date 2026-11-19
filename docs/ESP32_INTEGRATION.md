# ESP32-CAM integration guide (for the hardware team)

**Status:** firmware written to the device contract (`esp32_firmware/src/main.cpp`) but **not yet compiled
or run on hardware**. The contract itself is verified end to end over HTTP by
`esp32_firmware/tools/device_contract_client.py`.

## Hardware (planned)

AI-Thinker ESP32-CAM (OV2640), 5 V relay module, mini pump + nozzle, separate pump supply.

| Signal | ESP32-CAM pin | Note |
|---|---|---|
| Relay IN | **GPIO14** (configurable `RELAY_PIN`) | Avoid GPIO12 (boot strapping pin); GPIO4 is the flash LED |
| Relay VCC/GND | 5 V / GND | Common ground with ESP32 |
| Pump | Relay NO/COM on the **pump's own supply** | Never power the pump from the ESP32 3.3 V rail; add a flyback diode on DC pumps |

Most relay boards are active-low (`RELAY_ACTIVE_LOW true`). The firmware drives the relay **OFF at boot**.

## Firmware setup

```powershell
cd D:\AMAANz\Agri-Guard\esp32_firmware
Copy-Item include\config.example.h include\config.h   # git-ignored
# edit WIFI_SSID / WIFI_PASSWORD / API_BASE_URL (LAN IP of the backend) / DEVICE_TOKEN
pio run; pio run -t upload; pio device monitor
```

Get `DEVICE_TOKEN` from the dashboard: **Devices → Register hardware** (shown once; rotate if lost).
Start the backend with `--host 0.0.0.0` so the board can reach it on the LAN, and allow the port through the
Windows firewall.

## What the firmware does

1. Heartbeat every 5 s with RSSI and pump state; reads `emergency_stop_active` and forces the pump off if set.
2. Polls `/device/commands/next` every second; acks, executes `SPRAY` for `min(duration_s, MAX_SPRAY_MS)`,
   reports the result; `STOP` always switches the pump off.
3. Optional periodic capture (`CAPTURE_EVERY_MS`) → multipart upload with an `Idempotency-Key`, retried with
   backoff.
4. Fail-safes: local hard cap, pump off on Wi-Fi loss or when backend contact is lost mid-spray, refuses
   SPRAY while e-stop is active, ignores re-delivered command ids.

**Tank level and battery sensors are not fitted yet.** The firmware therefore sends them as unknown, and the
safety engine will **block** spraying on real hardware (`DEVICE_HEALTHY: unknown`). This is intentional.
Add the sensors (e.g. a float switch / ultrasonic sensor, battery voltage divider on an ADC pin) and report
`tank_level_pct` / `battery_pct`, or consciously relax the policy for a supervised bench test.

## Swapping the simulator for hardware

Nothing in the dashboard, API, database or safety engine changes. Both paths go through `DeviceGateway`:

| Simulator | Real device |
|---|---|
| `SimulatorManager` → `DeviceGateway` in-process | Firmware → HTTP `/api/v1/device/*` → same `DeviceGateway` |
| `source: "simulator"`, labelled **Simulated** | `source: "esp32"`, labelled **Hardware** |

Steps: register the device, flash, confirm it shows **Online** on the Devices page with live telemetry,
run a scan targeting it, approve, and confirm the command lifecycle in the operation's audit trail.
Optionally set `SIMULATOR_ENABLED=false`.

## Bench test checklist (water only)

- [ ] Relay off at power-up and after reset
- [ ] Heartbeats visible; unplugging Wi-Fi marks the device offline within 30 s
- [ ] SPRAY runs for the requested time and never exceeds `MAX_SPRAY_MS`
- [ ] Emergency stop in the dashboard switches the pump off within one heartbeat/poll interval
- [ ] Killing the backend mid-spray switches the pump off (lost-contact fail-safe)
- [ ] Duplicate command delivery does not restart the pump
