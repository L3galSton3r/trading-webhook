import os
import json
from flask import Flask, request, jsonify
from datetime import datetime
import requests

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

MT5_SIGNALS_PATH = os.path.join(
    os.getenv('APPDATA'),
    'MetaQuotes',
    'Terminal'
)

def find_mt5_signals_folder():
    if not os.path.exists(MT5_SIGNALS_PATH):
        return None
    
    # ═══════════════════════════════════════════════════════════════
    # ✅ FIX: Use the correct terminal folder
    # ═══════════════════════════════════════════════════════════════
    correct_terminal = "D0E8209F77C8CF37AD8BF550E51FF075"
    signals_path = os.path.join(MT5_SIGNALS_PATH, correct_terminal, 'MQL5', 'Files', 'Signals')
    
    if os.path.exists(signals_path):
        return signals_path
    
    # Fallback: Create the folder if it doesn't exist
    os.makedirs(signals_path, exist_ok=True)
    return signals_path
    # ═══════════════════════════════════════════════════════════════

SIGNALS_FOLDER = find_mt5_signals_folder()
RENDER_URL = "https://trading-webhook-aep9.onrender.com"

print("════════════════════════════════════════════════════════════")
print("🖥️  Local Signal Receiver Started (v2.1 - Google Logging)")
print("════════════════════════════════════════════════════════════")
print(f"📁 Signals folder: {SIGNALS_FOLDER}")
print(f"🌐 Listening on: http://localhost:8080")
print(f"📐 FIBO endpoint: http://localhost:8080/fibo")
print(f"📊 ORB endpoint: http://localhost:8080/orb")
print(f"🔄 UPDATE endpoint: http://localhost:8080/update")
print(f"💚 Health check: http://localhost:8080/health")
print(f"☁️  Render webhook: {RENDER_URL}")
print("════════════════════════════════════════════════════════════")

if not SIGNALS_FOLDER:
    print("⚠️  WARNING: Could not locate MT5 Signals folder!")
    print("   Signals will NOT be saved to MT5")
else:
    print(f"✅ MT5 Signals folder found")

print("⏳ Waiting for signals from Render...")
print()

# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def save_signal_to_file(signal_data, filename):
    if not SIGNALS_FOLDER:
        print("[ERROR] MT5 Signals folder not found")
        return False
    
    try:
        filepath = os.path.join(SIGNALS_FOLDER, filename)
        
        with open(filepath, 'w') as f:
            json.dump(signal_data, f, indent=2)
        
        print(f"✅ Signal saved: {filepath}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to save signal: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "Local Receiver Running",
        "version": "2.1",
        "endpoints": ["/fibo", "/orb", "/update", "/health"],
        "signals_folder": SIGNALS_FOLDER,
        "render_url": RENDER_URL
    })

@app.route('/fibo', methods=['POST'])
def fibo_signal():
    try:
        signal = request.get_json()
        
        print("════════════════════════════════════════════════════════════")
        print("📐 FIBO Signal Received from Render")
        print("════════════════════════════════════════════════════════════")
        print(f"Trade ID: {signal.get('trade_id', 'Unknown')}")
        print(f"Symbol: {signal.get('symbol', 'Unknown')}")
        print(f"Direction: {signal.get('direction', 'Unknown')}")
        print(f"Zone Type: {signal.get('zone_type', 'Unknown')}")
        print(f"Stop Loss: {signal.get('stop_loss', 'N/A')}")
        print(f"TP1: {signal.get('tp1', 'N/A')}")
        print(f"TP2: {signal.get('tp2', 'N/A')}")
        print(f"TP3: {signal.get('tp3', 'N/A')}")
        print(f"TP4: {signal.get('tp4', 'N/A')}")
        
        saved = save_signal_to_file(signal, 'fibo_signal.json')
        
        if saved:
            print("✅ Signal saved to MT5")
        else:
            print("⚠️  Signal received but NOT saved to MT5")
        
        print("════════════════════════════════════════════════════════════")
        print()
        
        return jsonify({"status": "success", "saved": saved})
    
    except Exception as e:
        print(f"[ERROR] /fibo error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/orb', methods=['POST'])
def orb_signal():
    try:
        signal = request.get_json()
        
        print("════════════════════════════════════════════════════════════")
        print("📊 ORB Signal Received from Render")
        print("════════════════════════════════════════════════════════════")
        print(f"Trade ID: {signal.get('trade_id', 'Unknown')}")
        print(f"Symbol: {signal.get('symbol', 'Unknown')}")
        print(f"Direction: {signal.get('direction', 'Unknown')}")
        print(f"Quality: {signal.get('quality', 'N/A')}⭐")
        print(f"Entry: {signal.get('entry', 'N/A')}")
        print(f"Stop Loss: {signal.get('stop_loss', 'N/A')}")
        print(f"Take Profit: {signal.get('take_profit', 'N/A')}")
        
        saved = save_signal_to_file(signal, 'orb_signal.json')
        
        if saved:
            print("✅ Signal saved to MT5")
        else:
            print("⚠️  Signal received but NOT saved to MT5")
        
        print("════════════════════════════════════════════════════════════")
        print()
        
        return jsonify({"status": "success", "saved": saved})
    
    except Exception as e:
        print(f"[ERROR] /orb error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/update', methods=['POST'])
def trade_update():
    try:
        outcome = request.get_json()
        
        print("════════════════════════════════════════════════════════════")
        print("🔄 Trade Outcome Update Received from EA")
        print("════════════════════════════════════════════════════════════")
        print(f"Trade ID: {outcome.get('trade_id', 'Unknown')}")
        print(f"Event: {outcome.get('event', 'Unknown')}")
        print(f"Price: {outcome.get('price', 'N/A')}")
        print(f"Profit: ${outcome.get('profit', 0):.2f}")
        print(f"Timestamp: {outcome.get('timestamp', 'N/A')}")
        
        try:
            response = requests.post(
                f"{RENDER_URL}/update",
                json=outcome,
                timeout=10
            )
            
            if response.status_code == 200:
                print("✅ Forwarded to Render → Google Sheets")
            else:
                print(f"⚠️  Render responded with: {response.status_code}")
        
        except requests.exceptions.RequestException as e:
            print(f"⚠️  Failed to forward to Render: {e}")
            print("   (Outcome received but not logged to Google Sheets)")
        
        print("════════════════════════════════════════════════════════════")
        print()
        
        return jsonify({"status": "success", "forwarded": True})
    
    except Exception as e:
        print(f"[ERROR] /update error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "running",
        "signals_folder": SIGNALS_FOLDER,
        "timestamp": datetime.now().isoformat()
    })

# ═══════════════════════════════════════════════════════════════════
# RUN SERVER
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)