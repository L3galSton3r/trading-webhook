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

def calculate_duration(outcome, worksheet, row_num):
    """Calculate trade duration from entry to exit"""
    try:
        timestamp = outcome.get('timestamp', '')
        
        # Try to get entry time from outcome
        if 'entry_time' in outcome:
            entry_time_str = outcome['entry_time']
        else:
            # Get entry time from sheet (Column C = 3 for Time, Column B = 2 for Date)
            entry_date = worksheet.cell(row_num, 2).value  # Date
            entry_time = worksheet.cell(row_num, 3).value  # Time
            if entry_date and entry_time:
                entry_time_str = f"{entry_date} {entry_time}"
            else:
                return None
        
        # Parse timestamps
        # Handle different formats
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%H:%M:%S']:
            try:
                if 'T' in entry_time_str or '-' in entry_time_str:
                    entry_dt = datetime.strptime(entry_time_str, fmt)
                else:
                    # If only time, use today's date
                    entry_dt = datetime.strptime(entry_time_str, '%H:%M:%S')
                break
            except:
                continue
        else:
            return None
        
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%H:%M:%S']:
            try:
                if 'T' in timestamp or '-' in timestamp:
                    exit_dt = datetime.strptime(timestamp, fmt)
                else:
                    exit_dt = datetime.strptime(timestamp, '%H:%M:%S')
                break
            except:
                continue
        else:
            return None
        
        # Calculate duration
        duration = exit_dt - entry_dt
        
        # Format nicely
        total_seconds = int(duration.total_seconds())
        if total_seconds < 0:
            total_seconds = abs(total_seconds)
        
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 24:
            days = hours // 24
            hours = hours % 24
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        else:
            return f"{minutes}m {seconds}s"
    
    except Exception as e:
        print(f"[WARNING] Could not calculate duration: {e}")
        return None

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
        
        # ═══════════════════════════════════════════════════════════════
        # ALWAYS UPDATE THESE IF PROVIDED (regardless of event type)
        # ═══════════════════════════════════════════════════════════════
        
        # Lot Size (Column M = 13) - CRITICAL for accurate P&L
        if 'lot_size' in outcome:
            worksheet.update_cell(row_num, 13, outcome['lot_size'])
            print(f"[SHEETS] Lot size updated: {outcome['lot_size']}")
        
        # Stop Loss (Column H = 8) - Update if SL was modified
        if 'new_sl' in outcome:
            worksheet.update_cell(row_num, 8, outcome['new_sl'])
            print(f"[SHEETS] SL updated: {outcome['new_sl']}")
        elif 'stop_loss' in outcome:
            worksheet.update_cell(row_num, 8, outcome['stop_loss'])
        elif 'sl' in outcome:
            worksheet.update_cell(row_num, 8, outcome['sl'])
        
        # ═══════════════════════════════════════════════════════════════
        # EVENT-SPECIFIC UPDATES
        # ═══════════════════════════════════════════════════════════════
        
        if event == 'ENTRY':
            # Entry Price (Column G = 7)
            worksheet.update_cell(row_num, 7, price)
            # Status (Column O = 15)
            worksheet.update_cell(row_num, 15, 'Active')
            print(f"[SHEETS] Entry logged @ {price}")
        
        elif event == 'TP1_HIT':
            # Status (Column O = 15)
            worksheet.update_cell(row_num, 15, 'TP1 Hit - Partial')
            # TP1 Hit (Column P = 16)
            worksheet.update_cell(row_num, 16, f"{timestamp} @ {price}")
            # Partial profit if provided
            if profit != 0:
                current_pnl = worksheet.cell(row_num, 22).value or "$0.00"
                # You could accumulate partial profits here if needed
            print(f"[SHEETS] TP1 hit @ {price}")
        
        elif event == 'TP2_HIT':
            # Status (Column O = 15)
            worksheet.update_cell(row_num, 15, 'TP2 Hit - Partial')
            # TP2 Hit (Column Q = 17)
            worksheet.update_cell(row_num, 17, f"{timestamp} @ {price}")
            print(f"[SHEETS] TP2 hit @ {price}")
        
        elif event == 'TP3_HIT':
            # Status (Column O = 15)
            worksheet.update_cell(row_num, 15, 'TP3 Hit - Partial')
            # TP3 Hit (Column R = 18)
            worksheet.update_cell(row_num, 18, f"{timestamp} @ {price}")
            print(f"[SHEETS] TP3 hit @ {price}")
        
        elif event == 'TP4_HIT':
            # Status (Column O = 15)
            worksheet.update_cell(row_num, 15, 'TP4 Hit - Closed')
            # TP4 Hit (Column S = 19)
            worksheet.update_cell(row_num, 19, f"{timestamp} @ {price}")
            # Exit Time (Column W = 23)
            worksheet.update_cell(row_num, 23, timestamp)
            # Final Outcome (Column U = 21)
            worksheet.update_cell(row_num, 21, 'Win')
            # Profit/Loss (Column V = 22)
            if profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
            # Duration (Column X = 24)
            duration = calculate_duration(outcome, worksheet, row_num)
            if duration:
                worksheet.update_cell(row_num, 24, duration)
            print(f"[SHEETS] TP4 hit - Trade closed @ {price} | Profit: ${profit:.2f}")
        
        elif event == 'BE_MOVED':
            # BE Moved (Column T = 20)
            worksheet.update_cell(row_num, 20, f"Yes @ {timestamp}")
            # Update Stop Loss to BE price (Column H = 8)
            if 'be_price' in outcome:
                worksheet.update_cell(row_num, 8, outcome['be_price'])
                print(f"[SHEETS] BE moved - SL updated to {outcome['be_price']}")
            elif 'entry_price' in outcome:
                worksheet.update_cell(row_num, 8, outcome['entry_price'])
                print(f"[SHEETS] BE moved - SL updated to entry {outcome['entry_price']}")
            elif price != 0:
                worksheet.update_cell(row_num, 8, price)
                print(f"[SHEETS] BE moved - SL updated to {price}")
            else:
                print(f"[SHEETS] BE moved @ {timestamp} (no price provided)")
        
        elif event == 'SL_TRAILED' or event == 'TRAIL_MOVED':
            # Update Stop Loss to new trailed price (Column H = 8)
            if 'new_sl' in outcome:
                worksheet.update_cell(row_num, 8, outcome['new_sl'])
                print(f"[SHEETS] SL trailed to {outcome['new_sl']}")
            elif price != 0:
                worksheet.update_cell(row_num, 8, price)
                print(f"[SHEETS] SL trailed to {price}")
        
        elif event == 'SL_HIT':
            # Status (Column O = 15)
            worksheet.update_cell(row_num, 15, 'SL Hit - Closed')
            # Exit Time (Column W = 23)
            worksheet.update_cell(row_num, 23, timestamp)
            # Exit Price / Actual SL (Column H = 8) - where it actually closed
            if price != 0:
                worksheet.update_cell(row_num, 8, price)
            # Profit/Loss (Column V = 22)
            if profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
            # Final Outcome (Column U = 21)
            r_multiple = outcome.get('r_multiple', 0)
            if r_multiple != 0:
                worksheet.update_cell(row_num, 21, f"{r_multiple:+.2f}R")
            else:
                # Determine if it was BE or Loss
                if profit == 0 or (profit > -1 and profit < 1):
                    worksheet.update_cell(row_num, 21, 'Breakeven')
                else:
                    worksheet.update_cell(row_num, 21, 'Loss')
            # Duration (Column X = 24)
            duration = calculate_duration(outcome, worksheet, row_num)
            if duration:
                worksheet.update_cell(row_num, 24, duration)
            print(f"[SHEETS] SL hit - Trade closed @ {price} | P&L: ${profit:.2f}")
        
        elif event == 'MANUAL_CLOSE' or event == 'CLOSED':
            # Status (Column O = 15)
            worksheet.update_cell(row_num, 15, 'Manually Closed')
            # Exit Time (Column W = 23)
            worksheet.update_cell(row_num, 23, timestamp)
            # Profit/Loss (Column V = 22)
            if profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
            # Final Outcome (Column U = 21)
            if profit > 0:
                worksheet.update_cell(row_num, 21, 'Win (Manual)')
            elif profit < 0:
                worksheet.update_cell(row_num, 21, 'Loss (Manual)')
            else:
                worksheet.update_cell(row_num, 21, 'Breakeven (Manual)')
            # Duration (Column X = 24)
            duration = calculate_duration(outcome, worksheet, row_num)
            if duration:
                worksheet.update_cell(row_num, 24, duration)
            print(f"[SHEETS] Manual close @ {price} | P&L: ${profit:.2f}")
        
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
        "version": "2.3 - Complete Update Fix",
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