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
GOOGLE_SHEET_ID_ORB = os.environ.get('GOOGLE_SHEET_ID_ORB', '')  # NEW: Separate ORB sheet
TIMEZONE_OFFSET = 2

SYMBOL_MAP = {
    "EURUSD": "EURUSD.m",
    "GBPUSD": "GBPUSD.m",
    "USDJPY": "USDJPY.m",
    "XAUUSD": "XAUUSD.m",
    "XAGUSD": "XAGUSD.m",
    "BTCUSD": "BTCUSD.m",
    "ETHUSD": "ETHUSD.m",
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

def get_google_spreadsheet(sheet_id=None):
    """Get a spreadsheet object by ID"""
    if not ENABLE_GOOGLE_LOGGING:
        return None
    
    if sheet_id is None:
        sheet_id = GOOGLE_SHEET_ID
    
    if not sheet_id:
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
        
        spreadsheet = client.open_by_key(sheet_id)
        
        return spreadsheet
    
    except Exception as e:
        print(f"[ERROR] Failed to connect to Google Sheets: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════
# FIBO SHEET FUNCTIONS (Existing - Daily Worksheets)
# ═══════════════════════════════════════════════════════════════════

def get_or_create_daily_worksheet():
    """Get today's FIBO worksheet or create it if it doesn't exist"""
    try:
        spreadsheet = get_google_spreadsheet(GOOGLE_SHEET_ID)
        if not spreadsheet:
            return None
        
        today = datetime.utcnow()
        sheet_name = today.strftime('%Y-%m-%d')
        
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            print(f"[SHEETS] Using existing Fibo sheet: {sheet_name}")
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            print(f"[SHEETS] Creating new Fibo sheet: {sheet_name}")
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=24)
            
            headers = [
                'Trade ID', 'Date', 'Time', 'Symbol', 'Direction', 'Zone Type',
                'Entry Price', 'Stop Loss', 'TP1', 'TP2', 'TP3', 'TP4',
                'Lot Size', 'Risk %', 'Status', 'TP1 Hit', 'TP2 Hit', 'TP3 Hit',
                'TP4 Hit', 'BE Moved', 'Final Outcome', 'Profit/Loss', 'Exit Time', 'Duration'
            ]
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            
            worksheet.format('A1:X1', {
                "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER"
            })
            
            print(f"[SHEETS] New Fibo sheet created: {sheet_name}")
            return worksheet
    
    except Exception as e:
        print(f"[ERROR] Failed to get/create Fibo daily worksheet: {e}")
        return None

def find_trade_in_all_sheets(trade_id):
    """Search for a trade ID across all FIBO worksheets"""
    try:
        spreadsheet = get_google_spreadsheet(GOOGLE_SHEET_ID)
        if not spreadsheet:
            return None, None
        
        worksheets = spreadsheet.worksheets()
        
        for worksheet in worksheets:
            try:
                cell = worksheet.find(trade_id)
                if cell:
                    print(f"[SHEETS] Found Fibo trade in sheet: {worksheet.title}")
                    return worksheet, cell.row
            except:
                continue
        
        print(f"[WARNING] Fibo trade ID not found in any sheet: {trade_id}")
        return None, None
    
    except Exception as e:
        print(f"[ERROR] Failed to search for Fibo trade: {e}")
        return None, None

# ═══════════════════════════════════════════════════════════════════
# ORB SHEET FUNCTIONS (Daily Worksheets - Same as Fibo)
# ═══════════════════════════════════════════════════════════════════

def get_or_create_orb_daily_worksheet():
    """Get today's ORB worksheet or create it if it doesn't exist"""
    try:
        spreadsheet = get_google_spreadsheet(GOOGLE_SHEET_ID_ORB)
        if not spreadsheet:
            print("[WARNING] ORB Sheet ID not configured")
            return None
        
        # Get today's date
        today = datetime.utcnow()
        sheet_name = today.strftime('%Y-%m-%d')
        
        # Try to get existing worksheet
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            print(f"[SHEETS] Using existing ORB sheet: {sheet_name}")
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            # Create new worksheet for today
            print(f"[SHEETS] Creating new ORB sheet: {sheet_name}")
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=26)
            
            # Add headers
            headers = [
                'Trade ID', 'Date', 'Time', 'Symbol', 'Direction', 'Session',
                'ORB High', 'ORB Low', 'ORB Mid', 'Entry Price', 'Stop Loss',
                'TP1', 'TP2', 'TP3', 'Lot Size', 'Risk (pts)', 'Status',
                'TP1 Hit', 'TP2 Hit', 'TP3 Hit', 'BE Moved',
                'Final Outcome', 'Profit/Loss', 'R-Multiple', 'Exit Time', 'Duration'
            ]
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            
            # Format header row (green theme for ORB)
            worksheet.format('A1:Z1', {
                "backgroundColor": {"red": 0.0, "green": 0.6, "blue": 0.4},
                "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER"
            })
            
            print(f"[SHEETS] New ORB sheet created with headers: {sheet_name}")
            return worksheet
    
    except Exception as e:
        print(f"[ERROR] Failed to get/create ORB daily worksheet: {e}")
        return None

def find_orb_trade_in_all_sheets(trade_id):
    """Search for an ORB trade ID across all worksheets"""
    try:
        spreadsheet = get_google_spreadsheet(GOOGLE_SHEET_ID_ORB)
        if not spreadsheet:
            return None, None
        
        # Get all worksheets
        worksheets = spreadsheet.worksheets()
        
        # Search each worksheet for the trade ID
        for worksheet in worksheets:
            try:
                cell = worksheet.find(trade_id)
                if cell:
                    print(f"[SHEETS] Found ORB trade in sheet: {worksheet.title}")
                    return worksheet, cell.row
            except:
                continue
        
        print(f"[WARNING] ORB trade ID not found in any sheet: {trade_id}")
        return None, None
    
    except Exception as e:
        print(f"[ERROR] Failed to search for ORB trade: {e}")
        return None, None

def find_all_orb_trade_rows(trade_id):
    """Find ALL rows matching a trade ID (for updating all layers)"""
    try:
        spreadsheet = get_google_spreadsheet(GOOGLE_SHEET_ID_ORB)
        if not spreadsheet:
            return None, []
        
        worksheets = spreadsheet.worksheets()
        
        for worksheet in worksheets:
            try:
                cells = worksheet.findall(trade_id)
                if cells:
                    rows = [cell.row for cell in cells]
                    print(f"[SHEETS] Found {len(rows)} rows for {trade_id} in {worksheet.title}")
                    return worksheet, rows
            except:
                continue
        
        return None, []
    
    except Exception as e:
        print(f"[ERROR] Failed to search for ORB trade rows: {e}")
        return None, []

def log_orb_entry_to_sheets(signal):
    """Log ORB trade entry to today's worksheet"""
    try:
        sheet = get_or_create_orb_daily_worksheet()
        if not sheet:
            return False
        
        now = datetime.utcnow()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')
        
        row = [
            signal.get('trade_id', ''),           # A
            date_str,                              # B
            time_str,                              # C
            signal.get('symbol', ''),              # D
            signal.get('direction', ''),           # E
            signal.get('session', ''),             # F
            signal.get('orb_high', ''),            # G
            signal.get('orb_low', ''),             # H
            signal.get('orb_mid', ''),             # I
            '',                                    # J - Entry Price (filled on LAYER_FILLED)
            signal.get('stop_loss', ''),           # K
            signal.get('tp1', ''),                 # L
            signal.get('tp2', ''),                 # M
            signal.get('tp3', ''),                 # N
            '',                                    # O - Lot Size (filled on LAYER_FILLED)
            signal.get('risk_pts', ''),            # P
            'Pending',                             # Q - Status (waiting for layers)
            '',                                    # R - TP1 Hit
            '',                                    # S - TP2 Hit
            '',                                    # T - TP3 Hit
            '',                                    # U - BE Moved
            '',                                    # V - Final Outcome
            '',                                    # W - Profit/Loss
            '',                                    # X - R-Multiple
            '',                                    # Y - Exit Time
            '',                                    # Z - Duration
        ]
        
        sheet.append_row(row, value_input_option='USER_ENTERED')
        
        print(f"[SHEETS] ORB signal logged to {sheet.title}: {signal.get('trade_id')}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to log ORB entry: {e}")
        return False

def update_orb_trade_outcome(outcome):
    """Update ORB trade outcome - LAYER_FILLED creates new rows, other events update all matching rows"""
    try:
        event = outcome.get('event', '')
        trade_id = outcome.get('trade_id', '')
        price = outcome.get('price', 0)
        profit = outcome.get('profit', 0)
        timestamp = outcome.get('timestamp', '')
        
        # Parse timestamp
        try:
            time_parts = timestamp.split(' ')
            if len(time_parts) >= 2:
                date_str = time_parts[0]
                time_str = time_parts[1]
            else:
                now = datetime.utcnow()
                date_str = now.strftime('%Y-%m-%d')
                time_str = now.strftime('%H:%M:%S')
        except:
            now = datetime.utcnow()
            date_str = now.strftime('%Y-%m-%d')
            time_str = now.strftime('%H:%M:%S')
        
        # ═══════════════════════════════════════════════════════════════
        # LAYER_FILLED - Creates a NEW row for each layer
        # ═══════════════════════════════════════════════════════════════
        if event == 'LAYER_FILLED':
            worksheet = get_or_create_orb_daily_worksheet()
            if not worksheet:
                return False
            
            lot_size = outcome.get('lot_size', 0)
            
            # Find the original signal row to get setup details
            original_worksheet, original_row = find_orb_trade_in_all_sheets(trade_id)
            
            if original_worksheet and original_row:
                # Get data from original row
                symbol = original_worksheet.cell(original_row, 4).value  # D: Symbol
                direction = original_worksheet.cell(original_row, 5).value  # E: Direction
                session = original_worksheet.cell(original_row, 6).value  # F: Session
                orb_high = original_worksheet.cell(original_row, 7).value  # G: ORB High
                orb_low = original_worksheet.cell(original_row, 8).value  # H: ORB Low
                orb_mid = original_worksheet.cell(original_row, 9).value  # I: ORB Mid
                stop_loss = original_worksheet.cell(original_row, 11).value  # K: Stop Loss
                tp1 = original_worksheet.cell(original_row, 12).value  # L: TP1
                tp2 = original_worksheet.cell(original_row, 13).value  # M: TP2
                tp3 = original_worksheet.cell(original_row, 14).value  # N: TP3
                risk_pts = original_worksheet.cell(original_row, 16).value  # P: Risk pts
                
                # Update original row status to show it's active now
                original_worksheet.update_cell(original_row, 17, 'Active - Layering')
            else:
                # Fallback if original not found
                symbol = ""
                direction = ""
                session = ""
                orb_high = ""
                orb_low = ""
                orb_mid = ""
                stop_loss = ""
                tp1 = ""
                tp2 = ""
                tp3 = ""
                risk_pts = ""
            
            # Create new row for this layer
            row = [
                trade_id,                              # A: Trade ID
                date_str,                              # B: Date
                time_str,                              # C: Time
                symbol,                                # D: Symbol
                direction,                             # E: Direction
                session,                               # F: Session
                orb_high,                              # G: ORB High
                orb_low,                               # H: ORB Low
                orb_mid,                               # I: ORB Mid
                price,                                 # J: Entry Price (THIS LAYER)
                stop_loss,                             # K: Stop Loss
                tp1,                                   # L: TP1
                tp2,                                   # M: TP2
                tp3,                                   # N: TP3
                lot_size,                              # O: Lot Size (THIS LAYER)
                risk_pts,                              # P: Risk pts
                'Active',                              # Q: Status
                '',                                    # R: TP1 Hit
                '',                                    # S: TP2 Hit
                '',                                    # T: TP3 Hit
                '',                                    # U: BE Moved
                '',                                    # V: Final Outcome
                '',                                    # W: Profit/Loss
                '',                                    # X: R-Multiple
                '',                                    # Y: Exit Time
                '',                                    # Z: Duration
            ]
            
            worksheet.append_row(row, value_input_option='USER_ENTERED')
            
            print(f"[SHEETS] ORB layer row added: {trade_id} @ {price} ({lot_size} lots)")
            return True
        
        # ═══════════════════════════════════════════════════════════════
        # TP1_HIT, TP2_HIT, TP3_HIT, BE_MOVED, SL_HIT - Update ALL matching rows
        # ═══════════════════════════════════════════════════════════════
        worksheet, rows = find_all_orb_trade_rows(trade_id)
        
        if not worksheet or not rows:
            print(f"[WARNING] ORB trade ID not found: {trade_id}")
            return False
        
        # Update each row
        for row_num in rows:
            try:
                if event == 'TP1_HIT':
                    worksheet.update_cell(row_num, 17, 'TP1 Hit - Partial')  # Q: Status
                    worksheet.update_cell(row_num, 18, f"{time_str} @ {price}")  # R: TP1 Hit
                
                elif event == 'TP2_HIT':
                    worksheet.update_cell(row_num, 17, 'TP2 Hit - Partial')  # Q: Status
                    worksheet.update_cell(row_num, 19, f"{time_str} @ {price}")  # S: TP2 Hit
                
                elif event == 'TP3_HIT':
                    worksheet.update_cell(row_num, 17, 'TP3 Hit - Closed')  # Q: Status
                    worksheet.update_cell(row_num, 20, f"{time_str} @ {price}")  # T: TP3 Hit
                    worksheet.update_cell(row_num, 25, timestamp)  # Y: Exit Time
                    worksheet.update_cell(row_num, 22, 'Win')  # V: Final Outcome
                    if profit != 0:
                        worksheet.update_cell(row_num, 23, f"${profit:.2f}")  # W: Profit/Loss
                
                elif event == 'BE_MOVED':
                    worksheet.update_cell(row_num, 21, f"Yes @ {time_str}")  # U: BE Moved
                    if 'new_sl' in outcome:
                        worksheet.update_cell(row_num, 11, outcome['new_sl'])  # K: Stop Loss
                    elif price != 0:
                        worksheet.update_cell(row_num, 11, price)
                
                elif event == 'SL_HIT':
                    worksheet.update_cell(row_num, 17, 'SL Hit - Closed')  # Q: Status
                    worksheet.update_cell(row_num, 25, timestamp)  # Y: Exit Time
                    worksheet.update_cell(row_num, 22, 'Loss')  # V: Final Outcome
                    if profit != 0:
                        worksheet.update_cell(row_num, 23, f"${profit:.2f}")  # W: Profit/Loss
                
                elif event == 'MANUAL_CLOSE' or event == 'CLOSED':
                    worksheet.update_cell(row_num, 17, 'Manually Closed')  # Q: Status
                    worksheet.update_cell(row_num, 25, timestamp)  # Y: Exit Time
                    if profit != 0:
                        worksheet.update_cell(row_num, 23, f"${profit:.2f}")  # W: Profit/Loss
                    if profit > 0:
                        worksheet.update_cell(row_num, 22, 'Win (Manual)')
                    elif profit < 0:
                        worksheet.update_cell(row_num, 22, 'Loss (Manual)')
                    else:
                        worksheet.update_cell(row_num, 22, 'Breakeven (Manual)')
                
            except Exception as row_error:
                print(f"[WARNING] Failed to update row {row_num}: {row_error}")
                continue
        
        print(f"[SHEETS] ORB updated {len(rows)} rows: {trade_id} | {event}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to update ORB outcome: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════
# FIBO LOGGING FUNCTIONS (Existing)
# ═══════════════════════════════════════════════════════════════════

def log_entry_to_sheets(signal):
    """Log FIBO trade entry to today's worksheet"""
    try:
        sheet = get_or_create_daily_worksheet()
        if not sheet:
            return False
        
        now = datetime.utcnow()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')
        
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
        
        print(f"[SHEETS] Fibo entry logged to {sheet.title}: {signal.get('trade_id')}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to log Fibo entry: {e}")
        return False

def calculate_duration(outcome, worksheet, row_num, date_col=2, time_col=3):
    """Calculate trade duration from entry to exit"""
    try:
        timestamp = outcome.get('timestamp', '')
        
        if 'entry_time' in outcome:
            entry_time_str = outcome['entry_time']
        else:
            entry_date = worksheet.cell(row_num, date_col).value
            entry_time = worksheet.cell(row_num, time_col).value
            if entry_date and entry_time:
                entry_time_str = f"{entry_date} {entry_time}"
            else:
                return None
        
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%H:%M:%S']:
            try:
                if 'T' in entry_time_str or '-' in entry_time_str:
                    entry_dt = datetime.strptime(entry_time_str, fmt)
                else:
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
        
        duration = exit_dt - entry_dt
        
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
    """Update FIBO trade outcome across all worksheets"""
    try:
        worksheet, row_num = find_trade_in_all_sheets(outcome.get('trade_id', ''))
        
        if not worksheet or not row_num:
            print(f"[WARNING] Fibo trade ID not found: {outcome.get('trade_id')}")
            return False
        
        event = outcome.get('event', '')
        price = outcome.get('price', 0)
        profit = outcome.get('profit', 0)
        timestamp = outcome.get('timestamp', '')
        
        if 'lot_size' in outcome:
            worksheet.update_cell(row_num, 13, outcome['lot_size'])
            print(f"[SHEETS] Lot size updated: {outcome['lot_size']}")
        
        if 'new_sl' in outcome:
            worksheet.update_cell(row_num, 8, outcome['new_sl'])
            print(f"[SHEETS] SL updated: {outcome['new_sl']}")
        elif 'stop_loss' in outcome:
            worksheet.update_cell(row_num, 8, outcome['stop_loss'])
        elif 'sl' in outcome:
            worksheet.update_cell(row_num, 8, outcome['sl'])
        
        if event == 'ENTRY':
            worksheet.update_cell(row_num, 7, price)
            worksheet.update_cell(row_num, 15, 'Active')
            print(f"[SHEETS] Entry logged @ {price}")
        
        elif event == 'TP1_HIT':
            worksheet.update_cell(row_num, 15, 'TP1 Hit - Partial')
            worksheet.update_cell(row_num, 16, f"{timestamp} @ {price}")
            print(f"[SHEETS] TP1 hit @ {price}")
        
        elif event == 'TP2_HIT':
            worksheet.update_cell(row_num, 15, 'TP2 Hit - Partial')
            worksheet.update_cell(row_num, 17, f"{timestamp} @ {price}")
            print(f"[SHEETS] TP2 hit @ {price}")
        
        elif event == 'TP3_HIT':
            worksheet.update_cell(row_num, 15, 'TP3 Hit - Partial')
            worksheet.update_cell(row_num, 18, f"{timestamp} @ {price}")
            print(f"[SHEETS] TP3 hit @ {price}")
        
        elif event == 'TP4_HIT':
            worksheet.update_cell(row_num, 15, 'TP4 Hit - Closed')
            worksheet.update_cell(row_num, 19, f"{timestamp} @ {price}")
            worksheet.update_cell(row_num, 23, timestamp)
            worksheet.update_cell(row_num, 21, 'Win')
            if profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
            duration = calculate_duration(outcome, worksheet, row_num)
            if duration:
                worksheet.update_cell(row_num, 24, duration)
            print(f"[SHEETS] TP4 hit - Trade closed @ {price}")
        
        elif event == 'BE_MOVED':
            worksheet.update_cell(row_num, 20, f"Yes @ {timestamp}")
            if 'be_price' in outcome:
                worksheet.update_cell(row_num, 8, outcome['be_price'])
                print(f"[SHEETS] BE moved - SL updated to {outcome['be_price']}")
            elif 'entry_price' in outcome:
                worksheet.update_cell(row_num, 8, outcome['entry_price'])
                print(f"[SHEETS] BE moved - SL updated to entry")
            elif price != 0:
                worksheet.update_cell(row_num, 8, price)
                print(f"[SHEETS] BE moved - SL updated to {price}")
        
        elif event == 'SL_TRAILED' or event == 'TRAIL_MOVED':
            if 'new_sl' in outcome:
                worksheet.update_cell(row_num, 8, outcome['new_sl'])
                print(f"[SHEETS] SL trailed to {outcome['new_sl']}")
            elif price != 0:
                worksheet.update_cell(row_num, 8, price)
                print(f"[SHEETS] SL trailed to {price}")
        
        elif event == 'SL_HIT':
            worksheet.update_cell(row_num, 15, 'SL Hit - Closed')
            worksheet.update_cell(row_num, 23, timestamp)
            if price != 0:
                worksheet.update_cell(row_num, 8, price)
            if profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
            r_multiple = outcome.get('r_multiple', 0)
            if r_multiple != 0:
                worksheet.update_cell(row_num, 21, f"{r_multiple:+.2f}R")
            else:
                if profit == 0 or (profit > -1 and profit < 1):
                    worksheet.update_cell(row_num, 21, 'Breakeven')
                else:
                    worksheet.update_cell(row_num, 21, 'Loss')
            duration = calculate_duration(outcome, worksheet, row_num)
            if duration:
                worksheet.update_cell(row_num, 24, duration)
            print(f"[SHEETS] SL hit - Trade closed @ {price}")
        
        elif event == 'MANUAL_CLOSE' or event == 'CLOSED':
            worksheet.update_cell(row_num, 15, 'Manually Closed')
            worksheet.update_cell(row_num, 23, timestamp)
            if profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
            if profit > 0:
                worksheet.update_cell(row_num, 21, 'Win (Manual)')
            elif profit < 0:
                worksheet.update_cell(row_num, 21, 'Loss (Manual)')
            else:
                worksheet.update_cell(row_num, 21, 'Breakeven (Manual)')
            duration = calculate_duration(outcome, worksheet, row_num)
            if duration:
                worksheet.update_cell(row_num, 24, duration)
            print(f"[SHEETS] Manual close @ {price}")
        
        print(f"[SHEETS] Updated {worksheet.title}: {outcome.get('trade_id')} | {event}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to update Fibo outcome: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "Trading Webhook Active",
        "version": "2.5 - Layered ORB Support",
        "endpoints": {
            "fibo": "/fibo",
            "orb": "/orb",
            "update": "/update",
            "orb_update": "/orb_update",
            "health": "/health"
        },
        "forwards_to": TAILSCALE_URL,
        "google_logging": ENABLE_GOOGLE_LOGGING,
        "fibo_sheet_id": GOOGLE_SHEET_ID if GOOGLE_SHEET_ID else "Not configured",
        "orb_sheet_id": GOOGLE_SHEET_ID_ORB if GOOGLE_SHEET_ID_ORB else "Not configured",
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
        
        # Log ORB to dedicated sheet with daily tabs
        if ENABLE_GOOGLE_LOGGING and GOOGLE_SHEET_ID_ORB:
            log_orb_entry_to_sheets(data)
        
        try:
            response = requests.post(
                f"{TAILSCALE_URL}/orb",
                json=data,
                timeout=10
            )
            print(f"[ORB] Forwarded to local: {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Failed to forward: {e}")
        
        return jsonify({"status": "success", "forwarded": True, "logged": ENABLE_GOOGLE_LOGGING and bool(GOOGLE_SHEET_ID_ORB)})
    
    except Exception as e:
        print(f"[ERROR] /orb error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/update', methods=['POST'])
def update_webhook():
    """Update endpoint for FIBO trades"""
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

@app.route('/orb_update', methods=['POST'])
def orb_update_webhook():
    """Update endpoint for ORB trades"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        print(f"[ORB_UPDATE] Received: {data.get('event', 'Unknown')} for {data.get('trade_id', 'Unknown')}")
        
        if ENABLE_GOOGLE_LOGGING and GOOGLE_SHEET_ID_ORB:
            update_orb_trade_outcome(data)
        
        return jsonify({"status": "success", "logged": ENABLE_GOOGLE_LOGGING and bool(GOOGLE_SHEET_ID_ORB)})
    
    except Exception as e:
        print(f"[ERROR] /orb_update error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "running",
        "google_sheets_fibo": ENABLE_GOOGLE_LOGGING and bool(GOOGLE_SHEET_ID),
        "google_sheets_orb": ENABLE_GOOGLE_LOGGING and bool(GOOGLE_SHEET_ID_ORB),
        "timestamp": datetime.utcnow().isoformat()
    })

# ═══════════════════════════════════════════════════════════════════
# RUN SERVER
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)