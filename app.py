<<<<<<< HEAD
import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

TAILSCALE_URL = os.environ.get('TAILSCALE_URL', 'https://hp-mario.tail1a7503.ts.net')
ENABLE_GOOGLE_LOGGING = os.environ.get('ENABLE_GOOGLE_LOGGING', 'true').lower() == 'true'
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '')  # You'll add this later
TIMEZONE_OFFSET = 2  # GMT+2 for South Africa

# Symbol mappings
SYMBOL_MAP = {
    "EURUSD": "EURUSD.m",
    "GBPUSD": "GBPUSD.m",
    "USDJPY": "USDJPY.m",
    "XAUUSD": "XAUUSD.m",
    "XAGUSD": "XAGUSD.m",
    "BTCUSD": "BTCUSD.m",
    "NAS100": "US100.std",
    "US100": "US100.std",
    "SPX500": "US500.std",
    "US500": "US500.std",
    "AAPL": "AAPL.m",
    "AMZN": "AMZN.m",
}

# ═══════════════════════════════════════════════════════════════════
# GOOGLE SHEETS SETUP
# ═══════════════════════════════════════════════════════════════════

def get_google_sheet():
    """Connect to Google Sheets"""
    if not ENABLE_GOOGLE_LOGGING or not GOOGLE_SHEET_ID:
        return None
    
    try:
        # Load credentials from environment variable (JSON string)
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if not creds_json:
            print("[WARNING] GOOGLE_CREDENTIALS_JSON not set")
            return None
        
        creds_dict = json.loads(creds_json)
        
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
        worksheet = spreadsheet.sheet1  # Use first sheet
        
        return worksheet
    
    except Exception as e:
        print(f"[ERROR] Failed to connect to Google Sheets: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════
# GOOGLE SHEETS LOGGING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def log_entry_to_sheets(signal):
    """Log trade entry to Google Sheets"""
    try:
        sheet = get_google_sheet()
        if not sheet:
            return False
        
        # Parse timestamp
        now = datetime.utcnow()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')
        
        # Calculate risk percentage
        risk_percent = 1.0 if signal.get('zone_type') == 'MAJOR' else 0.5
        
        # Prepare row data (matching your column layout)
        row = [
            signal.get('trade_id', ''),           # A: Trade ID
            date_str,                              # B: Date
            time_str,                              # C: Time
            signal.get('symbol', ''),              # D: Symbol
            signal.get('direction', ''),           # E: Direction
            signal.get('zone_type', ''),           # F: Zone Type
            '',                                    # G: Entry Price (filled by EA)
            signal.get('stop_loss', ''),           # H: Stop Loss
            signal.get('tp1', ''),                 # I: TP1
            signal.get('tp2', ''),                 # J: TP2
            signal.get('tp3', ''),                 # K: TP3
            signal.get('tp4', ''),                 # L: TP4
            '',                                    # M: Lot Size (filled by EA)
            f"{risk_percent}%",                    # N: Risk %
            'Active',                              # O: Status
            '',                                    # P: TP1 Hit
            '',                                    # Q: TP2 Hit
            '',                                    # R: TP3 Hit
            '',                                    # S: TP4 Hit
            '',                                    # T: BE Moved
            '',                                    # U: Final Outcome
            '',                                    # V: Profit/Loss
            '',                                    # W: Exit Time
            '',                                    # X: Duration
        ]
        
        # Append row
        sheet.append_row(row, value_input_option='USER_ENTERED')
        
        print(f"[SHEETS] Entry logged: {signal.get('trade_id')}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to log entry: {e}")
        return False

def update_trade_outcome(outcome):
    """Update trade outcome in Google Sheets"""
    try:
        sheet = get_google_sheet()
        if not sheet:
            return False
        
        trade_id = outcome.get('trade_id', '')
        event = outcome.get('event', '')
        price = outcome.get('price', 0)
        profit = outcome.get('profit', 0)
        timestamp = outcome.get('timestamp', '')
        
        # Find the row with this trade_id
        cell = sheet.find(trade_id)
        if not cell:
            print(f"[WARNING] Trade ID not found: {trade_id}")
            return False
        
        row_num = cell.row
        
        # Update based on event type
        if event == 'ENTRY':
            # Update entry price (column G) and lot size (column M)
            sheet.update_cell(row_num, 7, price)  # Entry Price
            if 'lot_size' in outcome:
                sheet.update_cell(row_num, 13, outcome['lot_size'])  # Lot Size
        
        elif event == 'TP1_HIT':
            sheet.update_cell(row_num, 15, 'TP1 Hit')  # Status (column O)
            sheet.update_cell(row_num, 16, f"{timestamp} @ {price}")  # TP1 Hit (column P)
        
        elif event == 'TP2_HIT':
            sheet.update_cell(row_num, 15, 'TP2 Hit')  # Status
            sheet.update_cell(row_num, 17, f"{timestamp} @ {price}")  # TP2 Hit (column Q)
        
        elif event == 'TP3_HIT':
            sheet.update_cell(row_num, 15, 'TP3 Hit')  # Status
            sheet.update_cell(row_num, 18, f"{timestamp} @ {price}")  # TP3 Hit (column R)
        
        elif event == 'TP4_HIT':
            sheet.update_cell(row_num, 15, 'TP4 Hit - Closed')  # Status
            sheet.update_cell(row_num, 19, f"{timestamp} @ {price}")  # TP4 Hit (column S)
            sheet.update_cell(row_num, 23, timestamp)  # Exit Time (column W)
            if profit != 0:
                sheet.update_cell(row_num, 22, f"${profit:.2f}")  # Profit/Loss (column V)
        
        elif event == 'BE_MOVED':
            sheet.update_cell(row_num, 20, f"Yes @ {timestamp}")  # BE Moved (column T)
        
        elif event == 'SL_HIT':
            sheet.update_cell(row_num, 15, 'SL Hit - Closed')  # Status
            sheet.update_cell(row_num, 23, timestamp)  # Exit Time
            if profit != 0:
                sheet.update_cell(row_num, 22, f"${profit:.2f}")  # Profit/Loss
                r_multiple = outcome.get('r_multiple', 0)
                sheet.update_cell(row_num, 21, f"{r_multiple:+.2f}R")  # Final Outcome (column U)
        
        print(f"[SHEETS] Updated: {trade_id} | {event}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to update outcome: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "Trading Webhook Active",
        "version": "2.1 - Google Sheets Logging",
        "endpoints": {
            "fibo": "/fibo",
            "orb": "/orb",
            "update": "/update",
            "health": "/health"
        },
        "forwards_to": TAILSCALE_URL,
        "google_logging": ENABLE_GOOGLE_LOGGING,
        "symbol_mappings": len(SYMBOL_MAP)
    })

@app.route('/fibo', methods=['POST'])
def fibo_webhook():
    """Receive FIBO signals from TradingView"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        print(f"[FIBO] Received: {data.get('trade_id', 'Unknown')}")
        
        # Map symbol
        if 'symbol' in data:
            original_symbol = data['symbol']
            data['symbol'] = SYMBOL_MAP.get(original_symbol, original_symbol)
            if original_symbol != data['symbol']:
                print(f"[FIBO] Symbol mapped: {original_symbol} → {data['symbol']}")
        
        # Log to Google Sheets
        if ENABLE_GOOGLE_LOGGING:
            log_entry_to_sheets(data)
        
        # Forward to local receiver
        try:
            response = requests.post(
                f"{TAILSCALE_URL}/fibo",
                json=data,
                timeout=10
            )
            print(f"[FIBO] Forwarded to local: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Failed to forward: {e}")
        
        return jsonify({"status": "success", "forwarded": True, "logged": ENABLE_GOOGLE_LOGGING})
    
    except Exception as e:
        print(f"[ERROR] /fibo error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/orb', methods=['POST'])
def orb_webhook():
    """Receive ORB signals from TradingView"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        print(f"[ORB] Received: {data.get('trade_id', 'Unknown')}")
        
        # Map symbol
        if 'symbol' in data:
            original_symbol = data['symbol']
            data['symbol'] = SYMBOL_MAP.get(original_symbol, original_symbol)
            if original_symbol != data['symbol']:
                print(f"[ORB] Symbol mapped: {original_symbol} → {data['symbol']}")
        
        # Forward to local receiver
        try:
            response = requests.post(
                f"{TAILSCALE_URL}/orb",
                json=data,
                timeout=10
            )
            print(f"[ORB] Forwarded to local: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Failed to forward: {e}")
        
        return jsonify({"status": "success", "forwarded": True})
    
    except Exception as e:
        print(f"[ERROR] /orb error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/update', methods=['POST'])
def update_webhook():
    """Receive trade outcome updates from EA"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        print(f"[UPDATE] Received: {data.get('event', 'Unknown')} for {data.get('trade_id', 'Unknown')}")
        
        # Update Google Sheets
        if ENABLE_GOOGLE_LOGGING:
            update_trade_outcome(data)
        
        return jsonify({"status": "success", "logged": ENABLE_GOOGLE_LOGGING})
    
    except Exception as e:
        print(f"[ERROR] /update error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "running",
        "google_sheets": ENABLE_GOOGLE_LOGGING,
        "timestamp": datetime.utcnow().isoformat()
    })

# ═══════════════════════════════════════════════════════════════════
# RUN SERVER
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
=======
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
    'GER40': 'DE40.std',
    'AAPL': 'AAPL.m',
    'AMZN': 'AMZN.m'
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
    """ORB signal endpoint - Enhanced for multi-TP system (backwards compatible)"""
    try:
        data = request.json
        log_signal("ORB", data)
        
        # Validate ORB required fields (works for both old and new ORB)
        required = ['trade_id', 'symbol', 'direction', 'entry', 'stop_loss', 'magic']
        
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
        
        # Log details - handle both old (single TP) and new (multi-TP) format
        print(f"Entry: {data.get('entry', 0)}")
        print(f"SL: {data.get('stop_loss', 0)}")
        
        # New ORB format has tp1, tp2, tp3
        if 'tp1' in data:
            print(f"Session: {data.get('session', 'N/A')}")
            print(f"TP1: {data.get('tp1', 0)} ({data.get('rr_tp1', 0)}R)")
            print(f"TP2: {data.get('tp2', 0)} ({data.get('rr_tp2', 0)}R)")
            print(f"TP3: {data.get('tp3', 0)} ({data.get('rr_tp3', 0)}R)")
            print(f"ORB Range: {data.get('orb_low', 0)} - {data.get('orb_high', 0)}")
            print(f"Retests: {data.get('retests', 0)}")
            print(f"Risk: {data.get('risk_pts', 0)} points")
        # Old ORB format has single take_profit
        elif 'take_profit' in data:
            print(f"TP: {data.get('take_profit', 0)}")
            print(f"Quality: {data.get('quality', 0)}⭐")
        
        # Forward to PC
        success, message = forward_to_pc('/orb', data)
        
        if success:
            return jsonify({
                "status": "success",
                "message": "ORB signal forwarded to MT5",
                "session": data.get('session', 'Unknown'),
                "direction": data.get('direction')
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
>>>>>>> f67fb232efa539df76f8db87c84e16721084ae8f
