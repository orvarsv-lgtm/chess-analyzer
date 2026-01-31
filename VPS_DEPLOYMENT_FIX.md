# Stockfish VPS Fix - Deployment Guide

## Problem Summary

The Stockfish analysis server on the VPS (72.60.185.247:8000) was running but returning 404 errors:

```
Jan 31 07:07:52 srv1240097 uvicorn[258830]: WARNING: Invalid HTTP request received.
Jan 31 07:07:53 srv1240097 uvicorn[258830]: INFO: 64.227.131.195:54228 - "GET / HTTP/1.1" 404 Not Found
Jan 31 07:07:53 srv1240097 uvicorn[258830]: INFO: 64.227.131.195:36192 - "GET /login HTTP/1.1" 404 Not Found
```

**Root Cause**: The FastAPI app (`engine_api.py`) is running but the `/analyze_game` route is not defined, causing:
- POST requests to `/analyze_game` → 404 Not Found
- GET requests to `/` → 404 Not Found
- Game analysis in Streamlit app → **Fails completely**

---

## Solution

### Part 1: Deploy Fixed Backend to VPS

1. **Copy the new `engine_api.py` to VPS**:
   ```bash
   scp engine_api.py root@72.60.185.247:/root/
   ```

2. **SSH into VPS and restart the service**:
   ```bash
   ssh root@72.60.185.247
   
   # Stop the old service
   systemctl stop chess-analyzer
   
   # Verify the new file
   cat /root/engine_api.py | head -20
   
   # Restart the service (systemd will auto-start from /root/venv/bin/uvicorn)
   systemctl start chess-analyzer
   
   # Verify it's running
   systemctl status chess-analyzer
   
   # Check the logs
   journalctl -u chess-analyzer -f
   ```

3. **Test the VPS endpoint locally**:
   ```bash
   # From your local machine:
   curl -X POST http://72.60.185.247:8000/analyze_game \
     -H "Content-Type: application/json" \
     -d '{"pgn":"1.e4 e5 2.Nf3 Nc6", "max_games":1}'
   
   # Should return:
   # {
   #   "success": true,
   #   "games_analyzed": 1,
   #   "total_moves": 4,
   #   "analysis": [...],
   #   ...
   # }
   ```

4. **Test health endpoint**:
   ```bash
   curl http://72.60.185.247:8000/
   # Should return: {"status": "ok", "service": "chess-analyzer-engine", "version": "1.0"}
   ```

---

### Part 2: Local Fallback (Already Implemented)

The Streamlit app now has an automatic fallback mechanism:

1. **When analyzing games**:
   - Tries VPS endpoint first (`POST /analyze_game` to 72.60.185.247:8000)
   - If VPS is down, unreachable, or returns error → automatically falls back to local Stockfish
   - Local analysis runs on the Streamlit Cloud machine (or your local machine)

2. **Fallback activation**:
   - Missing VPS_ANALYSIS_URL → uses local
   - VPS connection timeout → uses local
   - VPS returns 404, 403, 500, etc. → uses local
   - No action needed—just works!

3. **Configuration**:
   - Set `STOCKFISH_PATH` env var for custom Stockfish location
   - Otherwise auto-detects: `/usr/games/stockfish`, `/usr/bin/stockfish`, etc.
   - Or `stockfish` in PATH

---

## Testing After Deployment

### Test 1: VPS Backend Working
```bash
# From Streamlit app terminal:
import requests
resp = requests.post(
    "http://72.60.185.247:8000/analyze_game",
    json={"pgn": "1.e4 e5 2.Nf3 Nc6", "max_games": 1},
    timeout=30
)
print(resp.status_code, resp.json()["success"])
# Should print: 200 True
```

### Test 2: Streamlit App Analysis (VPS Enabled)
1. Go to Streamlit app
2. Enter a Lichess username
3. Run analysis
4. Should see: "✅ Done! Used X cached games, analyzed Y new games."

### Test 3: Local Fallback (Simulate VPS Down)
1. Unset `VPS_ANALYSIS_URL` in Streamlit secrets
2. Run analysis again
3. Should see: "Backend status: 200 OK" (and uses local Stockfish)

---

## File Changes

### New File: `engine_api.py`
- FastAPI backend with `/analyze_game` endpoint
- Handles PGN parsing and Stockfish analysis
- Returns JSON response compatible with Streamlit app

### Modified: `streamlit_app.py`
- Added `_find_stockfish_path_for_local()` → finds local Stockfish
- Added `_local_engine_analyze_pgn()` → runs local analysis
- Modified `_post_to_engine()` → captures errors and retries locally
- All changes are backward compatible

---

## Troubleshooting

### If VPS is still returning 404 after deployment:

1. Check that `engine_api.py` is in `/root/`:
   ```bash
   ls -la /root/engine_api.py
   ```

2. Check systemd service configuration:
   ```bash
   cat /etc/systemd/system/chess-analyzer.service
   # Should show: ExecStart=/root/venv/bin/uvicorn engine_api:app --host 0.0.0.0 --port 8000
   ```

3. Verify Stockfish is installed:
   ```bash
   which stockfish
   /usr/games/stockfish --version
   ```

4. Restart service and check logs:
   ```bash
   systemctl restart chess-analyzer
   journalctl -u chess-analyzer -n 50
   ```

### If local fallback isn't working:

1. Check Stockfish is installed locally:
   ```bash
   which stockfish
   stockfish --version
   ```

2. Set `STOCKFISH_PATH` if needed:
   ```bash
   export STOCKFISH_PATH=/path/to/stockfish
   ```

3. Verify Streamlit secrets aren't overriding fallback logic:
   - Remove/clear `VPS_ANALYSIS_URL` to force local analysis

---

## Expected Behavior After Fix

| Scenario | VPS Status | Result |
|----------|-----------|--------|
| VPS running, healthy | ✓ Online | Uses VPS (fast, remote) |
| VPS down, local Stockfish installed | ✗ Offline | Uses local (slower, but works) |
| VPS down, no local Stockfish | ✗ Offline | Error message with clear explanation |
| VPS + local both available | - | Uses VPS first, falls back to local on error |

---

## Summary

✅ **What's fixed**:
- VPS backend now properly handles `/analyze_game` requests
- Root endpoint `/` responds with health check
- Streamlit app can analyze games remotely again
- Automatic local fallback if VPS is unavailable

✅ **Result**: Game analysis works even if VPS is down (via local Stockfish)

🎯 **Next steps**: Deploy `engine_api.py` to VPS and restart the service.
