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
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '')
TIMEZONE_OFFSET = 2

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

def get_google_spreadsheet():
    """Get the main spreadsheet object"""
    if not ENABLE_GOOGLE_LOGGING or not GOOGLE_SHEET_ID:
        return None
    
    try:
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
        
        return spreadsheet
    
    except Exception as e:
        print(f"[ERROR] Failed to connect to Google Sheets: {e}")
        return None

def get_or_create_daily_worksheet():
    """Get today's worksheet or create it if it doesn't exist"""
    try:
        spreadsheet = get_google_spreadsheet()
        if not spreadsheet:
            return None
        
        # Get today's date in South Africa timezone (GMT+2)
        today = datetime.utcnow()
        sheet_name = today.strftime('%Y-%m-%d')
        
        # Try to get existing worksheet
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            print(f"[SHEETS] Using existing sheet: {sheet_name}")
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            # Create new worksheet for today
            print(f"[SHEETS] Creating new sheet: {sheet_name}")
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=24)
            
            # Add headers
            headers = [
                'Trade ID', 'Date', 'Time', 'Symbol', 'Direction', 'Zone Type',
                'Entry Price', 'Stop Loss', 'TP1', 'TP2', 'TP3', 'TP4',
                'Lot Size', 'Risk %', 'Status', 'TP1 Hit', 'TP2 Hit', 'TP3 Hit',
                'TP4 Hit', 'BE Moved', 'Final Outcome', 'Profit/Loss', 'Exit Time', 'Duration'
            ]
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            
            # Format header row
            worksheet.format('A1:X1', {
                "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER"
            })
            
            print(f"[SHEETS] New sheet created with headers: {sheet_name}")
            return worksheet
    
    except Exception as e:
        print(f"[ERROR] Failed to get/create daily worksheet: {e}")
        return None

def find_trade_in_all_sheets(trade_id):
    """Search for a trade ID across all worksheets"""
    try:
        spreadsheet = get_google_spreadsheet()
        if not spreadsheet:
            return None, None
        
        # Get all worksheets
        worksheets = spreadsheet.worksheets()
        
        # Search each worksheet for the trade ID
        for worksheet in worksheets:
            try:
                cell = worksheet.find(trade_id)
                if cell:
                    print(f"[SHEETS] Found trade in sheet: {worksheet.title}")
                    return worksheet, cell.row
            except:
                continue
        
        print(f"[WARNING] Trade ID not found in any sheet: {trade_id}")
        return None, None
    
    except Exception as e:
        print(f"[ERROR] Failed to search for trade: {e}")
        return None, None

# ═══════════════════════════════════════════════════════════════════
# GOOGLE SHEETS LOGGING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def log_entry_to_sheets(signal):
    """Log trade entry to today's worksheet"""
    try:
        sheet = get_or_create_daily_worksheet()
        if not sheet:
            return False
        
        now = datetime.utcnow()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')
        
        # Determine risk based on zone type (update these values to match your EA)
        risk_percent = 2.0 if signal.get('zone_type') == 'MAJOR' else 0.5
        
        row = [
            signal.get('trade_id', ''),
            date_str,
            time_str,
            signal.get('symbol', ''),
            signal.get('direction', ''),
            signal.get('zone_type', ''),
            '',
            signal.get('stop_loss', ''),
            signal.get('tp1', ''),
            signal.get('tp2', ''),
            signal.get('tp3', ''),
            signal.get('tp4', ''),
            '',
            f"{risk_percent}%",
            'Active',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
        ]
        
        sheet.append_row(row, value_input_option='USER_ENTERED')
        
        print(f"[SHEETS] Entry logged to {sheet.title}: {signal.get('trade_id')}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to log entry: {e}")
        return False

def update_trade_outcome(outcome):
    """Update trade outcome across all worksheets"""
    try:
        # Find the trade in any worksheet
        worksheet, row_num = find_trade_in_all_sheets(outcome.get('trade_id', ''))
        
        if not worksheet or not row_num:
            print(f"[WARNING] Trade ID not found: {outcome.get('trade_id')}")
            return False
        
        event = outcome.get('event', '')
        price = outcome.get('price', 0)
        profit = outcome.get('profit', 0)
        timestamp = outcome.get('timestamp', '')
        
        if event == 'ENTRY':
            worksheet.update_cell(row_num, 7, price)
            if 'lot_size' in outcome:
                worksheet.update_cell(row_num, 13, outcome['lot_size'])
        
        elif event == 'TP1_HIT':
            worksheet.update_cell(row_num, 15, 'TP1 Hit')
            worksheet.update_cell(row_num, 16, f"{timestamp} @ {price}")
        
        elif event == 'TP2_HIT':
            worksheet.update_cell(row_num, 15, 'TP2 Hit')
            worksheet.update_cell(row_num, 17, f"{timestamp} @ {price}")
        
        elif event == 'TP3_HIT':
            worksheet.update_cell(row_num, 15, 'TP3 Hit')
            worksheet.update_cell(row_num, 18, f"{timestamp} @ {price}")
        
        elif event == 'TP4_HIT':
            worksheet.update_cell(row_num, 15, 'TP4 Hit - Closed')
            worksheet.update_cell(row_num, 19, f"{timestamp} @ {price}")
            worksheet.update_cell(row_num, 23, timestamp)
            if profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
        
        elif event == 'BE_MOVED':
            worksheet.update_cell(row_num, 20, f"Yes @ {timestamp}")
        
        elif event == 'SL_HIT':
            worksheet.update_cell(row_num, 15, 'SL Hit - Closed')
            worksheet.update_cell(row_num, 23, timestamp)
            if profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
                r_multiple = outcome.get('r_multiple', 0)
                worksheet.update_cell(row_num, 21, f"{r_multiple:+.2f}R")
        
        print(f"[SHEETS] Updated {worksheet.title}: {outcome.get('trade_id')} | {event}")
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
        "version": "2.2 - Daily Sheets Auto-Creation",
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
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        print(f"[FIBO] Received: {data.get('trade_id', 'Unknown')}")
        
        if 'symbol' in data:
            original_symbol = data['symbol']
            data['symbol'] = SYMBOL_MAP.get(original_symbol, original_symbol)
            if original_symbol != data['symbol']:
                print(f"[FIBO] Symbol mapped: {original_symbol} → {data['symbol']}")
        
        if ENABLE_GOOGLE_LOGGING:
            log_entry_to_sheets(data)
        
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
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        print(f"[ORB] Received: {data.get('trade_id', 'Unknown')}")
        
        if 'symbol' in data:
            original_symbol = data['symbol']
            data['symbol'] = SYMBOL_MAP.get(original_symbol, original_symbol)
            if original_symbol != data['symbol']:
                print(f"[ORB] Symbol mapped: {original_symbol} → {data['symbol']}")
        
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
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        print(f"[UPDATE] Received: {data.get('event', 'Unknown')} for {data.get('trade_id', 'Unknown')}")
        
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