from flask import Flask, request, jsonify
import requests
import os
import json
from datetime import datetime

app = Flask(__name__)

# Environment variable for your PC's URL
LOCAL_RECEIVER_URL = os.environ.get('LOCAL_RECEIVER_URL', 'http://localhost:5002')

# Symbol mappings (shared between both systems)
SYMBOL_MAPPINGS = {
    'XAUUSD': 'XAUUSD.m',
    'XPTUSD': 'XPTUSD.m',
    'XAGUSD': 'XAGUSD.m',
    'OIL_CRUDE': 'WTI.m',
    'EURUSD': 'EURUSD.m',
    'GBPUSD': 'GBPUSD.m',
    'USDJPY': 'USDJPY.m',
    'BTCUSD': 'BTCUSD.m',
    'NAS100': 'US100.std',
    'US30': 'US30.std',
    'US500': 'US500.std',
    'GER40': 'DE40.std'
}

def map_symbol(tv_symbol):
    """Map TradingView symbol to broker symbol"""
    return SYMBOL_MAPPINGS.get(tv_symbol, tv_symbol)

def log_signal(strategy, data):
    """Log signal details"""
    print("=" * 60)
    print(f"📊 {strategy} Signal Received from TradingView")
    print("=" * 60)
    print(f"Trade ID: {data.get('trade_id', 'N/A')}")
    print(f"Symbol: {data.get('symbol', 'N/A')}")
    print(f"Direction: {data.get('direction', 'N/A')}")
    print("-" * 60)

def validate_signal(data, required_fields):
    """Validate required fields in signal"""
    missing = [field for field in required_fields if field not in data]
    if missing:
        print(f"❌ Missing fields: {', '.join(missing)}")
        return False, missing
    return True, []

def forward_to_pc(endpoint, data):
    """Forward signal to local PC"""
    try:
        url = f"{LOCAL_RECEIVER_URL}{endpoint}"
        print(f"Forwarding to: {url}")
        
        response = requests.post(url, json=data, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Successfully forwarded to PC")
            return True, "Success"
        else:
            print(f"❌ PC responded with error: {response.status_code}")
            return False, f"PC error: {response.status_code}"
            
    except requests.exceptions.Timeout:
        print(f"❌ Timeout connecting to PC")
        return False, "PC timeout"
        
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to PC")
        return False, "PC unreachable"
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False, str(e)

@app.route('/', methods=['GET'])
def home():
    """Status page"""
    return jsonify({
        "status": "Trading Webhook Active",
        "version": "2.0",
        "endpoints": {
            "fibo": "/fibo",
            "orb": "/orb",
            "health": "/health"
        },
        "forwards_to": LOCAL_RECEIVER_URL,
        "symbol_mappings": len(SYMBOL_MAPPINGS)
    }), 200

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        "status": "online",
        "time": datetime.now().isoformat(),
        "pc_url": LOCAL_RECEIVER_URL
    }), 200

@app.route('/fibo', methods=['POST'])
def fibo_webhook():
    """FIBO signal endpoint"""
    try:
        data = request.json
        log_signal("FIBO", data)
        
        # Validate FIBO required fields
        required = ['trade_id', 'symbol', 'direction', 'zone_type', 
                   'zone_low', 'zone_high', 'stop_loss', 'tp1']
        
        valid, missing = validate_signal(data, required)
        if not valid:
            return jsonify({
                "status": "error",
                "message": f"Missing fields: {', '.join(missing)}"
            }), 400
        
        # Map symbol
        data['symbol'] = map_symbol(data.get('symbol', ''))
        
        # Forward to PC
        success, message = forward_to_pc('/fibo', data)
        
        if success:
            return jsonify({
                "status": "success",
                "message": "FIBO signal forwarded to MT5"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": message
            }), 503
            
    except Exception as e:
        print(f"❌ FIBO Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/orb', methods=['POST'])
def orb_webhook():
    """ORB signal endpoint"""
    try:
        data = request.json
        log_signal("ORB", data)
        
        # Validate ORB required fields
        required = ['trade_id', 'symbol', 'direction', 'entry', 'stop_loss', 'take_profit', 'magic']
        
        valid, missing = validate_signal(data, required)
        if not valid:
            return jsonify({
                "status": "error",
                "message": f"Missing fields: {', '.join(missing)}"
            }), 400
        
        # Validate ORB trade_id format
        if not data['trade_id'].startswith('ORB_'):
            print(f"⚠️ Not an ORB signal: {data['trade_id']}")
            return jsonify({
                "status": "rejected",
                "reason": "Not an ORB signal"
            }), 400
        
        # Map symbol
        data['symbol'] = map_symbol(data.get('symbol', ''))
        
        # Forward to PC
        success, message = forward_to_pc('/orb', data)
        
        if success:
            return jsonify({
                "status": "success",
                "message": "ORB signal forwarded to MT5"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": message
            }), 503
            
    except Exception as e:
        print(f"❌ ORB Error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    app.run(host='0.0.0.0', port=port)




