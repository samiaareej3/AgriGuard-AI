# 10-minute demo script

Setup: backend (`uvicorn app.main:app --port 8000`) and frontend (`npm run dev`) running; wait until the
Overview shows the model state as ready (≈1 min after backend start). Sign in as `admin`.

1. **Overview (1 min).** Point out the *Simulator active* and *In-memory DB* badges: the app is honest about
   demo data. Show the live-link indicator, device fleet and the always-visible **Emergency stop**.
2. **Devices (1 min).** Two simulated ESP32-CAMs with live tank/battery/signal. Explain they run the same
   HTTP contract the real firmware will use (`DeviceGateway`).
3. **Disease detection (2 min).** Upload `backend/sample_images/late_blight/late_blight_1.jpg` with target
   device *Greenhouse A — Row 1*. Show probabilities, confidence vs threshold, then the **13-rule safety
   table**: everything passes except operator approval → *Awaiting approval*.
   Then upload `early_blight/early_blight_1.jpg`: confidence 52.6 % < 75 % → **Review required**, no spray.
   Upload with *No device* selected → **Blocked: No registered target device**.
4. **Spray operations (2 min).** Approve the pending operation; note it is **re-evaluated** at approval.
   Watch *Dispatched → Spraying → Completed* live, and the audit trail. Scan again on the same device →
   **Blocked by cooldown**.
5. **Fault injection (1 min).** Devices → *Simulate signal loss* on Row 2; after ~30 s it turns **Offline**
   on Live Monitoring and its scans are blocked. *Fail next command* → approve → operation **Failed**.
6. **Emergency stop (1 min).** Click Emergency stop, give a reason: banner appears, operations abort, STOP
   goes to every device. Only an admin can reset (show the reset form).
7. **Analytics & Insights (1 min).** Charts come only from stored records (table toggle for accessibility).
   Insights shows live Open-Meteo / NASA POWER data with source, retrieval time and freshness, the spray
   weather check, and the data-source licence table.
8. **Settings (1 min).** Policy (versioned, admin-only), model card with real held-out metrics and the
   field-data caveat, audit log.

Close: the model is decision support. Field accuracy is not yet measured, hardware is pending, and the
system defaults to *not spraying* whenever anything is uncertain.
