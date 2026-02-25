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
GOOGLE_SHEET_ID_ORB = os.environ.get('GOOGLE_SHEET_ID_ORB', '')
TIMEZONE_OFFSET = 2

SYMBOL_MAP = {
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "XAUUSD": "XAUUSD",
    "GOLD": "XAUUSD",
    "XAGUSD": "XAGUSD",
    "SILVER": "XAGUSD",
    "BTCUSD": "BTCUSD",
    "ETHUSD": "ETHUSD",
    "NAS100": "NAS100",
    "US100": "NAS100",
    "SPX500": "SPX500",
    "GER40": "GER40",
    "US500": "SPX500",
    "AAPL": "AAPL",
    "AMZN": "AMZN",
    "EURUSD": "EURUSD.m",
    "GBPUSD": "GBPUSD.m",
    "USDJPY": "USDJPY.m",
    "XAUUSD": "XAUUSD.m",
    "GOLD": "XAUUSD.m",
    "XAGUSD": "XAGUSD.m",
    "SILVER": "XAGUSD.m",
    "BTCUSD": "BTCUSD.m",
    "ETHUSD": "ETHUSD.m",
    "NAS100": "US100.std",
    "US100": "US100.std",
    "SPX500": "US500.std",
    "GER40": "DE40.std",
    "US500": "US500.std",
    "AAPL": "AAPL.m",
    "AMZN": "AMZN.m",
}

# ═══════════════════════════════════════════════════════════════════
# GOOGLE SHEETS SETUP
# ═══════════════════════════════════════════════════════════════════

def get_google_spreadsheet(sheet_id=None):
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
# DURATION CALCULATION HELPER
# ═══════════════════════════════════════════════════════════════════

def calculate_duration_from_times(entry_time_str, exit_time_str):
    try:
        entry_dt = None
        exit_dt = None
        
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y.%m.%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
            try:
                entry_dt = datetime.strptime(entry_time_str, fmt)
                break
            except:
                continue
        
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y.%m.%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
            try:
                exit_dt = datetime.strptime(exit_time_str, fmt)
                break
            except:
                continue
        
        if not entry_dt or not exit_dt:
            print(f"[WARNING] Could not parse times: entry={entry_time_str}, exit={exit_time_str}")
            return None
        
        duration = exit_dt - entry_dt
        total_seconds = int(abs(duration.total_seconds()))
        
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
        print(f"[WARNING] Duration calculation error: {e}")
        return None

def parse_dollar_value(value_str):
    try:
        if not value_str:
            return 0
        clean = str(value_str).replace('$', '').replace(',', '').strip()
        return float(clean) if clean else 0
    except:
        return 0

# ═══════════════════════════════════════════════════════════════════
# FIBO SHEET FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def get_or_create_daily_worksheet():
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

def log_entry_to_sheets(signal):
    try:
        sheet = get_or_create_daily_worksheet()
        if not sheet:
            return False
        
        now = datetime.utcnow()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')
        
        risk_percent = 1.0 if signal.get('zone_type') == 'MAJOR' else 1.0
        
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
            '', '', '', '', '', '', '', '', '',
        ]
        
        sheet.append_row(row, value_input_option='USER_ENTERED')
        print(f"[SHEETS] Fibo entry logged to {sheet.title}: {signal.get('trade_id')}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to log Fibo entry: {e}")
        return False

def calculate_duration(outcome, worksheet, row_num, date_col=2, time_col=3):
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
        
        return calculate_duration_from_times(entry_time_str, timestamp)
    
    except Exception as e:
        print(f"[WARNING] Could not calculate duration: {e}")
        return None

def update_trade_outcome(outcome):
    try:
        worksheet, row_num = find_trade_in_all_sheets(outcome.get('trade_id', ''))
        
        if not worksheet or not row_num:
            print(f"[WARNING] Fibo trade ID not found: {outcome.get('trade_id')}")
            return False
        
        event = outcome.get('event', '')
        price = outcome.get('price', 0)
        profit = outcome.get('profit', 0)
        cumulative_profit = outcome.get('cumulative_profit', profit)
        timestamp = outcome.get('timestamp', '')
        
        if 'lot_size' in outcome:
            worksheet.update_cell(row_num, 13, outcome['lot_size'])
        
        if 'new_sl' in outcome:
            worksheet.update_cell(row_num, 8, outcome['new_sl'])
        elif 'stop_loss' in outcome:
            worksheet.update_cell(row_num, 8, outcome['stop_loss'])
        elif 'sl' in outcome:
            worksheet.update_cell(row_num, 8, outcome['sl'])
        
        if event == 'ENTRY':
            worksheet.update_cell(row_num, 7, price)
            worksheet.update_cell(row_num, 15, 'Active')
        
        elif event == 'TP1_HIT':
            worksheet.update_cell(row_num, 15, 'TP1 Hit - Partial')
            worksheet.update_cell(row_num, 16, f"{timestamp} @ {price}")
            if cumulative_profit != 0:
                worksheet.update_cell(row_num, 22, f"${cumulative_profit:.2f}")
        
        elif event == 'TP2_HIT':
            worksheet.update_cell(row_num, 15, 'TP2 Hit - Partial')
            worksheet.update_cell(row_num, 17, f"{timestamp} @ {price}")
            if cumulative_profit != 0:
                worksheet.update_cell(row_num, 22, f"${cumulative_profit:.2f}")
        
        elif event == 'TP3_HIT':
            worksheet.update_cell(row_num, 15, 'TP3 Hit - Partial')
            worksheet.update_cell(row_num, 18, f"{timestamp} @ {price}")
            if cumulative_profit != 0:
                worksheet.update_cell(row_num, 22, f"${cumulative_profit:.2f}")
        
        elif event == 'TP4_HIT':
            worksheet.update_cell(row_num, 15, 'TP4 Hit - Closed')
            worksheet.update_cell(row_num, 19, f"{timestamp} @ {price}")
            worksheet.update_cell(row_num, 23, timestamp)
            worksheet.update_cell(row_num, 21, 'Win')
            if cumulative_profit != 0:
                worksheet.update_cell(row_num, 22, f"${cumulative_profit:.2f}")
            elif profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
            duration = calculate_duration(outcome, worksheet, row_num)
            if duration:
                worksheet.update_cell(row_num, 24, duration)
        
        elif event == 'BE_MOVED':
            worksheet.update_cell(row_num, 20, f"Yes @ {timestamp}")
            if 'be_price' in outcome:
                worksheet.update_cell(row_num, 8, outcome['be_price'])
            elif 'entry_price' in outcome:
                worksheet.update_cell(row_num, 8, outcome['entry_price'])
            elif price != 0:
                worksheet.update_cell(row_num, 8, price)
        
        elif event == 'BE_CLOSED':
            current_stage = outcome.get('current_stage', 1)
            worksheet.update_cell(row_num, 15, 'BE Hit - Closed')
            worksheet.update_cell(row_num, 21, f"Closed at BE (after TP{current_stage})")
            worksheet.update_cell(row_num, 23, timestamp)
            if cumulative_profit != 0:
                worksheet.update_cell(row_num, 22, f"${cumulative_profit:.2f}")
            elif profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
            duration = calculate_duration(outcome, worksheet, row_num)
            if duration:
                worksheet.update_cell(row_num, 24, duration)
        
        elif event == 'SL_TRAILED' or event == 'TRAIL_MOVED':
            if 'new_sl' in outcome:
                worksheet.update_cell(row_num, 8, outcome['new_sl'])
            elif price != 0:
                worksheet.update_cell(row_num, 8, price)
        
        # ═══════════════════════════════════════════════════════════════
        # SL_HIT - FIXED: Use text outcome, not broken R-multiple
        # ═══════════════════════════════════════════════════════════════
        elif event == 'SL_HIT':
            worksheet.update_cell(row_num, 15, 'SL Hit - Closed')
            worksheet.update_cell(row_num, 23, timestamp)
            
            if price != 0:
                worksheet.update_cell(row_num, 8, price)
            
            if profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
            
            # Simple text outcome (removed broken R-multiple calculation)
            if profit == 0 or (profit > -1 and profit < 1):
                worksheet.update_cell(row_num, 21, 'Breakeven')
            elif profit > 0:
                worksheet.update_cell(row_num, 21, 'Win')
            else:
                worksheet.update_cell(row_num, 21, 'Loss')
            
            duration = calculate_duration(outcome, worksheet, row_num)
            if duration:
                worksheet.update_cell(row_num, 24, duration)
        
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
        
        print(f"[SHEETS] Updated {worksheet.title}: {outcome.get('trade_id')} | {event}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to update Fibo outcome: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════
# ORB SHEET FUNCTIONS (FIXED)
# ═══════════════════════════════════════════════════════════════════

def get_or_create_orb_daily_worksheet():
    try:
        spreadsheet = get_google_spreadsheet(GOOGLE_SHEET_ID_ORB)
        if not spreadsheet:
            print("[WARNING] ORB Sheet ID not configured")
            return None
        
        today = datetime.utcnow()
        sheet_name = today.strftime('%Y-%m-%d')
        
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            print(f"[SHEETS] Using existing ORB sheet: {sheet_name}")
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            print(f"[SHEETS] Creating new ORB sheet: {sheet_name}")
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=30)
            
            headers = [
                'Trade ID', 'Date', 'Time', 'Symbol', 'Direction', 'Session',
                'ORB High', 'ORB Low', 'ORB Mid', 'Entry Price', 'Stop Loss',
                'TP1', 'TP2', 'TP3', 'Lot Size', 'Risk (pts)', 'Status',
                'TP1 Hit', 'TP2 Hit', 'TP3 Hit', 'BE Moved', 'Final Outcome',
                'Gross P/L', 'Commission', 'Swap', 'Net P/L', 'Cumulative',
                'Exit Time', 'Duration'
            ]
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            
            worksheet.format('A1:AC1', {
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
    try:
        spreadsheet = get_google_spreadsheet(GOOGLE_SHEET_ID_ORB)
        if not spreadsheet:
            return None, None
        
        worksheets = spreadsheet.worksheets()
        
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
    try:
        sheet = get_or_create_orb_daily_worksheet()
        if not sheet:
            return False
        
        now = datetime.utcnow()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')
        
        row = [
            signal.get('trade_id', ''),
            date_str,
            time_str,
            signal.get('symbol', ''),
            signal.get('direction', ''),
            signal.get('session', ''),
            signal.get('orb_high', ''),
            signal.get('orb_low', ''),
            signal.get('orb_mid', ''),
            '',
            signal.get('stop_loss', ''),
            signal.get('tp1', ''),
            signal.get('tp2', ''),
            signal.get('tp3', ''),
            '',
            signal.get('risk_pts', ''),
            'Pending',
            '', '', '', '', '', '', '', '', '', '', '', ''
        ]
        
        sheet.append_row(row, value_input_option='USER_ENTERED')
        print(f"[SHEETS] ORB signal logged to {sheet.title}: {signal.get('trade_id')}")
        return True
    
    except Exception as e:
        print(f"[ERROR] Failed to log ORB entry: {e}")
        return False

def update_orb_trade_outcome(outcome):
    try:
        event = outcome.get('event', '')
        trade_id = outcome.get('trade_id', '')
        price = outcome.get('price', 0)
        profit = outcome.get('profit', 0)
        commission = outcome.get('commission', 0)
        swap = outcome.get('swap', 0)
        net_pnl = outcome.get('net_pnl', profit + commission + swap)
        cumulative_pnl = outcome.get('cumulative_pnl', 0)
        entry_time = outcome.get('entry_time', '')
        timestamp = outcome.get('timestamp', '')
        
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
        
        duration = None
        if entry_time and timestamp:
            duration = calculate_duration_from_times(entry_time, timestamp)
        
        if event == 'LAYER_FILLED':
            worksheet = get_or_create_orb_daily_worksheet()
            if not worksheet:
                return False
            
            lot_size = outcome.get('lot_size', 0)
            original_worksheet, original_row = find_orb_trade_in_all_sheets(trade_id)
            
            if original_worksheet and original_row:
                symbol = original_worksheet.cell(original_row, 4).value
                direction = original_worksheet.cell(original_row, 5).value
                session = original_worksheet.cell(original_row, 6).value
                orb_high = original_worksheet.cell(original_row, 7).value
                orb_low = original_worksheet.cell(original_row, 8).value
                orb_mid = original_worksheet.cell(original_row, 9).value
                stop_loss = original_worksheet.cell(original_row, 11).value
                tp1 = original_worksheet.cell(original_row, 12).value
                tp2 = original_worksheet.cell(original_row, 13).value
                tp3 = original_worksheet.cell(original_row, 14).value
                risk_pts = original_worksheet.cell(original_row, 16).value
                original_worksheet.update_cell(original_row, 17, 'Active - Layering')
            else:
                symbol = direction = session = ""
                orb_high = orb_low = orb_mid = ""
                stop_loss = tp1 = tp2 = tp3 = risk_pts = ""
            
            row = [
                trade_id, date_str, time_str, symbol, direction, session,
                orb_high, orb_low, orb_mid, price, stop_loss,
                tp1, tp2, tp3, lot_size, risk_pts, 'Active',
                '', '', '', '', '', '', '', '', '', '', '', ''
            ]
            
            worksheet.append_row(row, value_input_option='USER_ENTERED')
            print(f"[SHEETS] ORB layer row added: {trade_id} @ {price} ({lot_size} lots)")
            return True
        
        worksheet, rows = find_all_orb_trade_rows(trade_id)
        
        if not worksheet or not rows:
            print(f"[WARNING] ORB trade ID not found: {trade_id}")
            return False
        
        if event in ['TP1_HIT', 'TP2_HIT', 'TP3_HIT']:
            row_num = rows[0]
            
            try:
                if event == 'TP1_HIT':
                    worksheet.update_cell(row_num, 17, 'TP1 Hit - Partial')
                    worksheet.update_cell(row_num, 18, f"{time_str} @ {price}")
                
                elif event == 'TP2_HIT':
                    worksheet.update_cell(row_num, 17, 'TP2 Hit - Partial')
                    worksheet.update_cell(row_num, 19, f"{time_str} @ {price}")
                
                elif event == 'TP3_HIT':
                    worksheet.update_cell(row_num, 17, 'TP3 Hit - Closed')
                    worksheet.update_cell(row_num, 20, f"{time_str} @ {price}")
                    worksheet.update_cell(row_num, 22, 'Win')
                    worksheet.update_cell(row_num, 28, timestamp)
                    if duration:
                        worksheet.update_cell(row_num, 29, duration)
                
                if cumulative_pnl != 0:
                    worksheet.update_cell(row_num, 27, f"${cumulative_pnl:.2f}")
                
                print(f"[SHEETS] ORB {event} updated first row: {trade_id}")
                return True
                
            except Exception as e:
                print(f"[WARNING] Failed to update TP event: {e}")
                return False
        
        if event == 'BE_MOVED':
            for row_num in rows:
                try:
                    worksheet.update_cell(row_num, 21, f"Yes @ {time_str}")
                    if 'new_sl' in outcome and outcome['new_sl'] > 0:
                        worksheet.update_cell(row_num, 11, outcome['new_sl'])
                    elif price > 0:
                        worksheet.update_cell(row_num, 11, price)
                except Exception as e:
                    print(f"[WARNING] Failed to update BE row {row_num}: {e}")
            
            print(f"[SHEETS] ORB BE_MOVED updated {len(rows)} rows")
            return True
        
        if event in ['SL_HIT', 'CLOSED_EXTERNAL']:
            updated = False
            for row_num in rows:
                try:
                    current_status = worksheet.cell(row_num, 17).value or ''
                    
                    if 'Closed' in current_status:
                        continue
                    
                    if event == 'SL_HIT':
                        worksheet.update_cell(row_num, 17, 'SL Hit - Closed')
                    else:
                        if profit > 0:
                            worksheet.update_cell(row_num, 17, 'BE Hit - Closed')
                        elif profit < 0:
                            worksheet.update_cell(row_num, 17, 'SL Hit - Closed')
                        else:
                            worksheet.update_cell(row_num, 17, 'BE Hit - Closed')
                    
                    worksheet.update_cell(row_num, 28, timestamp)
                    
                    if profit < 0:
                        worksheet.update_cell(row_num, 22, 'Loss')
                    elif profit > 0:
                        worksheet.update_cell(row_num, 22, 'Win')
                    else:
                        worksheet.update_cell(row_num, 22, 'Breakeven')
                    
                    if profit != 0:
                        worksheet.update_cell(row_num, 23, f"${profit:.2f}")
                    if commission != 0:
                        worksheet.update_cell(row_num, 24, f"${commission:.2f}")
                    if swap != 0:
                        worksheet.update_cell(row_num, 25, f"${swap:.2f}")
                    
                    layer_net = profit + commission + swap
                    worksheet.update_cell(row_num, 26, f"${layer_net:.2f}")
                    
                    if cumulative_pnl != 0:
                        worksheet.update_cell(row_num, 27, f"${cumulative_pnl:.2f}")
                    
                    if duration:
                        worksheet.update_cell(row_num, 29, duration)
                    
                    print(f"[SHEETS] ORB {event} updated row {row_num}: ${profit:.2f}")
                    updated = True
                    break
                    
                except Exception as e:
                    print(f"[WARNING] Failed to update row {row_num}: {e}")
                    continue
            
            if not updated:
                print(f"[WARNING] No unclosed row found for {trade_id}")
            
            return updated
        
        if event in ['MANUAL_CLOSE', 'CLOSED']:
            for row_num in rows:
                try:
                    current_status = worksheet.cell(row_num, 17).value or ''
                    
                    if 'Closed' in current_status:
                        continue
                    
                    worksheet.update_cell(row_num, 17, 'Manually Closed')
                    worksheet.update_cell(row_num, 28, timestamp)
                    
                    if profit > 0:
                        worksheet.update_cell(row_num, 22, 'Win (Manual)')
                    elif profit < 0:
                        worksheet.update_cell(row_num, 22, 'Loss (Manual)')
                    else:
                        worksheet.update_cell(row_num, 22, 'Breakeven (Manual)')
                    
                    if profit != 0:
                        worksheet.update_cell(row_num, 23, f"${profit:.2f}")
                    if commission != 0:
                        worksheet.update_cell(row_num, 24, f"${commission:.2f}")
                    if swap != 0:
                        worksheet.update_cell(row_num, 25, f"${swap:.2f}")
                    if cumulative_pnl != 0:
                        worksheet.update_cell(row_num, 26, f"${cumulative_pnl:.2f}")
                    if duration:
                        worksheet.update_cell(row_num, 29, duration)
                    
                    print(f"[SHEETS] ORB MANUAL_CLOSE updated row {row_num}")
                    break
                    
                except Exception as e:
                    print(f"[WARNING] Failed to update row {row_num}: {e}")
                    continue
            
            return True
        
        print(f"[WARNING] Unknown event type: {event}")
        return False
    
    except Exception as e:
        print(f"[ERROR] Failed to update ORB outcome: {e}")
        import traceback
        traceback.print_exc()
        return False

# ═══════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "Trading Webhook Active",
        "version": "3.4 - Fixed SL_HIT R-Multiple Bug",
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
                print(f"[FIBO] Symbol mapped: {original_symbol} -> {data['symbol']}")
        
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
                print(f"[ORB] Symbol mapped: {original_symbol} -> {data['symbol']}")
        
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
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        
        event = data.get('event', 'Unknown')
        trade_id = data.get('trade_id', 'Unknown')
        profit = data.get('profit', 0)
        commission = data.get('commission', 0)
        swap = data.get('swap', 0)
        net_pnl = data.get('net_pnl', profit + commission + swap)
        
        print(f"[ORB_UPDATE] {event} for {trade_id} | Profit: ${profit:.2f} | Comm: ${commission:.2f} | Swap: ${swap:.2f} | Net: ${net_pnl:.2f}")
        
        if ENABLE_GOOGLE_LOGGING and GOOGLE_SHEET_ID_ORB:
            update_orb_trade_outcome(data)
        
        return jsonify({"status": "success", "logged": ENABLE_GOOGLE_LOGGING and bool(GOOGLE_SHEET_ID_ORB)})
    
    except Exception as e:
        print(f"[ERROR] /orb_update error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "running",
        "version": "3.4",
        "google_sheets_fibo": ENABLE_GOOGLE_LOGGING and bool(GOOGLE_SHEET_ID),
        "google_sheets_orb": ENABLE_GOOGLE_LOGGING and bool(GOOGLE_SHEET_ID_ORB),
        "timestamp": datetime.utcnow().isoformat()
    })

# ═══════════════════════════════════════════════════════════════════
# RUN SERVER
# ═══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"[STARTUP] Trading Webhook v3.4 - Fixed SL_HIT R-Multiple Bug")
    print(f"[STARTUP] Starting on port {port}")
    app.run(host='0.0.0.0', port=port)