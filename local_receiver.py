from flask import Flask, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)

# Path to MT5 signals folder
MT5_FILES_PATH = r"C:\Users\mario\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\MQL5\Files\Signals"

@app.route('/fibo', methods=['POST'])
def receive_fibo():
    """Receive FIBO signal from Render"""
    try:
        data = request.json
        
        print("\n" + "=" * 60)
        print("📐 FIBO Signal Received from Render")
        print("=" * 60)
        print(f"Trade ID: {data.get('trade_id')}")
        print(f"Symbol: {data.get('symbol')}")
        print(f"Direction: {data.get('direction')}")
        print(f"Zone Type: {data.get('zone_type')}")
        print(f"Zone: {data.get('zone_low')} - {data.get('zone_high')}")
        print(f"SL: {data.get('stop_loss')}")
        print(f"TP1: {data.get('tp1')}")
        print("-" * 60)
        
        # Create signals folder if needed
        os.makedirs(MT5_FILES_PATH, exist_ok=True)
        
        # Save FIBO signal file
        signal_file = os.path.join(MT5_FILES_PATH, 'fibo_signal.json')
        
        with open(signal_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✅ FIBO signal saved: {signal_file}")
        print(f"   FIBO EA should pick this up within 2 seconds")
        print("=" * 60 + "\n")
        
        return jsonify({
            "status": "success",
            "message": "FIBO signal saved for MT5",
            "file": signal_file
        }), 200
        
    except Exception as e:
        print(f"❌ FIBO Error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/orb', methods=['POST'])
def receive_orb():
    """Receive ORB signal from Render"""
    try:
        data = request.json
        
        print("\n" + "=" * 60)
        print("📊 ORB Signal Received from Render")
        print("=" * 60)
        print(f"Trade ID: {data.get('trade_id')}")
        print(f"Symbol: {data.get('symbol')}")
        print(f"Direction: {data.get('direction')}")
        print(f"Entry: {data.get('entry')}")
        print(f"SL: {data.get('stop_loss')}")
        print(f"TP: {data.get('take_profit')}")
        print(f"Quality: {data.get('quality', 0)}⭐")
        print("-" * 60)
        
        # Create signals folder if needed
        os.makedirs(MT5_FILES_PATH, exist_ok=True)
        
        # Save ORB signal file
        signal_file = os.path.join(MT5_FILES_PATH, 'orb_signal.json')
        
        with open(signal_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✅ ORB signal saved: {signal_file}")
        print(f"   ORB EA should pick this up within 0.5 seconds")
        print("=" * 60 + "\n")
        
        return jsonify({
            "status": "success",
            "message": "ORB signal saved for MT5",
            "file": signal_file
        }), 200
        
    except Exception as e:
        print(f"❌ ORB Error: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        "status": "running",
        "time": datetime.now().isoformat(),
        "signals_path": MT5_FILES_PATH
    }), 200

if __name__ == '__main__':
    print("=" * 60)
    print("🖥️  Local Signal Receiver Started")
    print("=" * 60)
    print(f"📁 Signals folder: {MT5_FILES_PATH}")
    print(f"🌐 Listening on: http://localhost:5002")
    print(f"📐 FIBO endpoint: http://localhost:5002/fibo")
    print(f"📊 ORB endpoint: http://localhost:5002/orb")
    print(f"💚 Health check: http://localhost:5002/health")
    print("=" * 60)
    print("⏳ Waiting for signals from Render...")
    print("=" * 60 + "\n")
    
    app.run(host='0.0.0.0', port=5002, debug=False)