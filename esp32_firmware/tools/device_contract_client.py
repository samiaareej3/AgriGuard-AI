"""Reference HTTP device client: behaves exactly like the planned ESP32-CAM firmware.

Use it to test the device <-> backend contract (docs/DEVICE_API.md) against a
running backend WITHOUT hardware, or as a readable spec for the firmware team.
Stdlib only (no extra dependencies).

    # register a new device with operator credentials, then run 1 cycle
    python esp32_firmware/tools/device_contract_client.py --register --user admin --password agriguard-dev \
        --image backend/sample_images/late_blight/late_blight_1.jpg --approve

    # or reuse an existing device token
    python esp32_firmware/tools/device_contract_client.py --token agd_... --cycles 5

``--approve`` uses the operator account to approve the resulting operation, so
the full detect -> approve -> SPRAY command -> ack -> result loop is exercised.
Nothing physical is actuated: this client only *reports* a simulated spray.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
import uuid

UA = "AgriGuard-DeviceContractClient/1.0"


class Http:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, *, headers: dict | None = None, body: bytes | None = None,
             json_body: dict | None = None, retries: int = 3) -> tuple[int, dict | None]:
        hdrs = {"User-Agent": UA, **(headers or {})}
        if json_body is not None:
            body = json.dumps(json_body).encode()
            hdrs["Content-Type"] = "application/json"
        for attempt in range(retries):
            req = urllib.request.Request(self.base + path, data=body, method=method, headers=hdrs)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read()
                    return resp.status, (json.loads(raw) if raw else None)
            except urllib.error.HTTPError as e:
                raw = e.read()
                if e.code in (429, 502, 503, 504) and attempt < retries - 1:
                    time.sleep(2 ** attempt)  # retry with backoff (contract: safe for idempotent calls)
                    continue
                return e.code, (json.loads(raw) if raw else None)
            except urllib.error.URLError:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise RuntimeError("unreachable")


def multipart(field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(filename)[0] or "image/jpeg"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000/api/v1")
    ap.add_argument("--token")
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password")
    ap.add_argument("--image")
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--cycles", type=int, default=20)
    args = ap.parse_args()
    http = Http(args.api)
    op_headers: dict[str, str] = {}

    if args.register or args.approve:
        st, res = http.call("POST", "/auth/login", json_body={"username": args.user, "password": args.password})
        assert st == 200, f"login failed: {st} {res}"
        op_headers = {"Authorization": f"Bearer {res['access_token']}"}
    token = args.token
    if args.register:
        st, res = http.call("POST", "/devices", headers=op_headers,
                            json_body={"name": f"Contract client {uuid.uuid4().hex[:4]}", "source": "esp32",
                                       "firmware_version": "contract-client-1.0"})
        assert st == 201, f"register failed: {st} {res}"
        token = res["device_token"]
        print(f"[register] device {res['device']['id']} (token shown once)")
    if not token:
        ap.error("--token or --register required")
    dev = {"X-Device-Token": token}

    st, hb = http.call("POST", "/device/heartbeat", headers=dev, json_body={
        "status": "ok", "firmware_version": "contract-client-1.0", "uptime_s": 1,
        "telemetry": {"temperature_c": 27.0, "humidity_pct": 60, "battery_pct": 90, "tank_level_pct": 80,
                      "rssi_dbm": -60, "pump_state": "idle"}})
    assert st == 200, f"heartbeat failed {st} {hb}"
    print(f"[heartbeat] ok | e-stop={hb['emergency_stop_active']} | next in {hb['next_heartbeat_s']}s")

    if args.image:
        data = open(args.image, "rb").read()
        body, ctype = multipart("image", args.image.replace("\\", "/").split("/")[-1], data)
        key = uuid.uuid4().hex
        st, scan = http.call("POST", "/device/scans", headers={**dev, "Content-Type": ctype, "Idempotency-Key": key}, body=body)
        assert st == 201, f"scan upload failed {st} {scan}"
        st2, again = http.call("POST", "/device/scans", headers={**dev, "Content-Type": ctype, "Idempotency-Key": key}, body=body)
        assert st2 == 200 and again["id"] == scan["id"], "idempotent retry did not return the same scan"
        print(f"[scan] {scan['id']} -> {scan['prediction']['display_label']} "
              f"({scan['prediction']['confidence']}) | decision {scan['decision']['outcome']} | retry deduplicated OK")
        if args.approve and scan.get("spray_operation_id"):
            st, op = http.call("POST", f"/spray/operations/{scan['spray_operation_id']}/approve",
                               headers=op_headers, json_body={"note": "contract client test"})
            print(f"[approve] operation -> {op.get('status') if op else st}")

    for i in range(args.cycles):
        st, cmd = http.call("GET", "/device/commands/next", headers=dev)
        if st == 204:
            time.sleep(1)
            http.call("POST", "/device/heartbeat", headers=dev, json_body={"status": "ok", "telemetry": {
                "battery_pct": 90, "tank_level_pct": 80, "pump_state": "idle"}})
            continue
        assert st == 200, f"poll failed {st} {cmd}"
        print(f"[command] {cmd['type']} {cmd['id']} params={cmd['params']}")
        st, ack = http.call("POST", f"/device/commands/{cmd['id']}/ack", headers=dev)
        st_again, _ = http.call("POST", f"/device/commands/{cmd['id']}/ack", headers=dev)
        print(f"[ack] {ack['status']} (repeat ack -> HTTP {st_again}, idempotent)")
        dur = float(cmd["params"].get("duration_s", 0))
        time.sleep(min(dur, 10))  # firmware would drive the relay here (hard-capped)
        st, res = http.call("POST", f"/device/commands/{cmd['id']}/result", headers=dev,
                            json_body={"success": True, "message": "contract client: simulated spray done",
                                       "actual_duration_s": dur})
        print(f"[result] {res['status']}")
        if cmd["type"] == "SPRAY":
            break
    http.call("POST", "/device/disconnect", headers=dev)
    print("[disconnect] graceful")
    return 0


if __name__ == "__main__":
    sys.exit(main())
