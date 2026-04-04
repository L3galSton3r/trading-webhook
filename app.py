import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
from threading import Thread, Lock

app = Flask(__name__)

sheets_lock = Lock()

TAILSCALE_URL = os.environ.get('TAILSCALE_URL', 'https://hp-mario.tail1a7503.ts.net')
ENABLE_GOOGLE_LOGGING = os.environ.get('ENABLE_GOOGLE_LOGGING', 'true').lower() == 'true'
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '')
GOOGLE_SHEET_ID_ORB = os.environ.get('GOOGLE_SHEET_ID_ORB', '')
GOOGLE_SHEET_ID_MASTER = os.environ.get('GOOGLE_SHEET_ID_MASTER', '')
TIMEZONE_OFFSET = 2

ACCOUNT_MAPPING = {
    2001470183: "JM",
    1512630376: "FTMO",
}

def get_sheet_prefix(account_number):
    prefix = ACCOUNT_MAPPING.get(account_number)
    if prefix:
        return prefix
    return f"ACC{account_number}"

SYMBOL_MAP = {
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY",
    "XAUUSD": "XAUUSD", "GOLD": "XAUUSD", "XAGUSD": "XAGUSD",
    "SILVER": "XAGUSD", "BTCUSD": "BTCUSD", "ETHUSD": "ETHUSD",
    "NAS100": "NAS100", "US100": "NAS100", "SPX500": "SPX500",
    "GER40": "GER40", "US500": "SPX500",
}

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
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(sheet_id)
        return spreadsheet
    except Exception as e:
        print(f"[ERROR] Failed to connect to Google Sheets: {e}")
        return None

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
# MASTER STRATEGY LOG (UNCHANGED - ALREADY CORRECT)
# ═══════════════════════════════════════════════════════════════════

def get_or_create_master_log():
    try:
        if not GOOGLE_SHEET_ID_MASTER:
            return None
        spreadsheet = get_google_spreadsheet(GOOGLE_SHEET_ID_MASTER)
        if not spreadsheet:
            return None
        try:
            return spreadsheet.worksheet("Trade_Master_Log")
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="Trade_Master_Log", rows=10000, cols=20)
            headers = ['Trade ID', 'Symbol', 'Direction', 'Zone/Session', 'Entry Time', 'Entry Price', 'Entry Balance', 'Risk %', 'Close Time', 'Close Price', 'Gross P/L', 'Commission', 'Swap', 'Net P/L', 'R Multiple', 'Duration', 'Entry Day', 'Close Day', 'Status']
            worksheet.update('A1:S1', [headers], value_input_option='USER_ENTERED')
            worksheet.format('A1:S1', {"backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.8}, "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}, "horizontalAlignment": "CENTER"})
            return worksheet
    except Exception as e:
        print(f"[ERROR] Master Log Init: {e}")
        return None

def log_entry_to_master(data):
    if not GOOGLE_SHEET_ID_MASTER:
        return
    try:
        worksheet = get_or_create_master_log()
        if not worksheet:
            return
        trade_id = data.get('trade_id', '')
        entry_time_str = data.get('timestamp', '')
        entry_day = datetime.strptime(entry_time_str.replace('.', '-'), '%Y-%m-%d %H:%M:%S').strftime('%A') if entry_time_str else ""
        
        zone_type = data.get('zone_type', 'MINOR')
        if 'risk_percent' in data:
            risk_pct = data['risk_percent']
            if isinstance(risk_pct, (int, float)):
                risk_display = f"{risk_pct}%"
            else:
                risk_display = str(risk_pct)
        else:
            risk_pct = 0.75 if zone_type == 'MAJOR' else 0.40
            risk_display = f"{risk_pct}%"
        
        row = [trade_id, data.get('symbol', ''), data.get('direction', ''), data.get('zone_type') or data.get('session', ''), entry_time_str, data.get('entry') or data.get('price', ''), data.get('mt5_balance', ''), risk_display, '', '', '', '', '', '', '', '', entry_day, '', 'OPEN']
        worksheet.append_row(row, value_input_option='USER_ENTERED')
        print(f"[SHEETS] ✅ Master Log entry added: {trade_id}")
    except Exception as e:
        print(f"[ERROR] Master entry log: {e}")

def update_master_on_close(data):
    if not GOOGLE_SHEET_ID_MASTER:
        return
    try:
        worksheet = get_or_create_master_log()
        if not worksheet:
            return
        trade_id = data.get('trade_id', '')
        cell = worksheet.find(trade_id)
        if not cell:
            return
        row_num = cell.row
        
        # Get timestamps
        close_time_str = data.get('timestamp', '')
        close_day = ""
        if close_time_str:
            try:
                close_day = datetime.strptime(close_time_str.replace('.', '-'), '%Y-%m-%d %H:%M:%S').strftime('%A')
            except:
                pass
        
        # Calculate duration
        entry_time_str = worksheet.cell(row_num, 5).value
        duration = calculate_duration_from_times(entry_time_str, close_time_str) if entry_time_str else ""
        
        # Get P/L breakdown from EA
        gross_pnl = data.get('gross_profit', 0)
        commission = data.get('commission', 0)
        swap = data.get('swap', 0)
        
        # For final closes, use cumulative profit (total across all partials)
        cumulative = data.get('cumulative_profit', 0)
        is_final = data.get('is_final_close', False)
        
        if is_final and cumulative != 0:
            # Use cumulative for the total trade P/L
            net_pnl = cumulative
        elif gross_pnl != 0 or commission != 0 or swap != 0:
            net_pnl = gross_pnl + commission + swap
        else:
            net_pnl = data.get('profit', 0)
        
        # Calculate R Multiple
        r_multiple = ""
        try:
            entry_balance_str = worksheet.cell(row_num, 7).value
            risk_pct_str = worksheet.cell(row_num, 8).value
            if entry_balance_str and risk_pct_str:
                entry_balance = parse_dollar_value(entry_balance_str)
                risk_pct = float(str(risk_pct_str).replace('%', ''))
                risk_amount = entry_balance * (risk_pct / 100)
                if risk_amount > 0:
                    r_multiple = round(net_pnl / risk_amount, 2)
        except:
            pass
        
        # Show correct status
        event = data.get('event', 'CLOSED')
        if is_final and event in ['TP1_HIT', 'TP2_HIT', 'TP3_HIT']:
            status = f"{event}_FINAL"
        else:
            status = event
        
        # Update all columns
        worksheet.update_cell(row_num, 9, close_time_str)      # Close Time
        worksheet.update_cell(row_num, 10, data.get('price', ''))  # Close Price
        worksheet.update_cell(row_num, 11, gross_pnl)          # Gross P/L
        worksheet.update_cell(row_num, 12, commission)         # Commission
        worksheet.update_cell(row_num, 13, swap)               # Swap
        worksheet.update_cell(row_num, 14, net_pnl)            # Net P/L
        worksheet.update_cell(row_num, 15, r_multiple)         # R Multiple
        worksheet.update_cell(row_num, 16, duration)           # Duration
        worksheet.update_cell(row_num, 18, close_day)          # Close Day
        worksheet.update_cell(row_num, 19, status)             # Status
        
        print(f"[SHEETS] ✅ Master Log updated: {trade_id} | Gross: ${gross_pnl:.2f} | Comm: ${commission:.2f} | Swap: ${swap:.2f} | Net: ${net_pnl:.2f} | R: {r_multiple}")
    except Exception as e:
        print(f"[ERROR] Master close update: {e}")

# ═══════════════════════════════════════════════════════════════════
# DAILY PERFORMANCE SHEETS (COMPLETELY REWRITTEN - LOGS BY CLOSE DATE)
# ═══════════════════════════════════════════════════════════════════

def get_or_create_daily_worksheet_for_date(account_number, target_date):
    """
    Get or create a daily performance sheet for a SPECIFIC date.
    Uses BATCH updates to avoid Google Sheets API rate limits.
    Looks back up to 7 days to find last ending balance.
    """
    try:
        spreadsheet = get_google_spreadsheet(GOOGLE_SHEET_ID)
        if not spreadsheet:
            return None
        
        if account_number:
            prefix = get_sheet_prefix(account_number)
        else:
            prefix = "UNKNOWN"
        
        sheet_name = f"{prefix}-{target_date.strftime('%Y-%m-%d')}"
        
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            print(f"[SHEETS] Using existing daily sheet: {sheet_name}")
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            print(f"[SHEETS] Creating new daily sheet: {sheet_name}")
            
            # ═══════════════════════════════════════════════════════════════
            # ✅ FIX: Look back up to 7 days to find last ending balance
            # ═══════════════════════════════════════════════════════════════
            starting_balance = 0.0
            for days_back in range(1, 8):  # Check up to 7 days back
                try:
                    prev_date = target_date - timedelta(days=days_back)
                    prev_sheet_name = f"{prefix}-{prev_date.strftime('%Y-%m-%d')}"
                    prev_sheet = spreadsheet.worksheet(prev_sheet_name)
                    prev_ending_balance = prev_sheet.cell(3, 2).value
                    if prev_ending_balance:
                        starting_balance = parse_dollar_value(prev_ending_balance)
                        print(f"[SHEETS] ✅ Starting balance from {prev_sheet_name} ({days_back} days back): ${starting_balance:.2f}")
                        break  # Found it, stop searching
                except Exception as e:
                    continue  # Keep looking
            
            if starting_balance == 0:
                print(f"[SHEETS] ⚠️ No previous sheet found within 7 days, starting at $0.00")
            # ═══════════════════════════════════════════════════════════════
            
            # Create worksheet
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
            
            # Prepare all data updates
            updates = []
            
            # Header (A1:T1)
            updates.append({
                'range': 'A1:T1',
                'values': [['📊 DAILY PERFORMANCE - REALIZED P/L ONLY']]
            })
            
            # Balance section (A2:C5)
            updates.append({
                'range': 'A2:C5',
                'values': [
                    ['Starting Balance:', starting_balance, ''],
                    ['Ending Balance:', '=B2+SUM(M9:M)', ''],
                    ['Daily P/L:', '=B3-B2', '=IF(B2>0,TEXT(B4/B2*100,"0.00")&"%","0%")'],
                    ['', '', '']
                ]
            })
            
            # Stats section (D2:E5)
            updates.append({
                'range': 'D2:E5',
                'values': [
                    ['Closed Trades:', '=COUNTIF(I:I,"Final TP4")+COUNTIF(I:I,"Stop Loss")+COUNTIF(I:I,"Manual Close")+COUNTIF(I:I,"BE Close")'],
                    ['Wins:', '=SUMPRODUCT((I:I="Final TP4")*(M:M>0))+SUMPRODUCT((I:I="Stop Loss")*(M:M>0))+SUMPRODUCT((I:I="BE Close")*(M:M>0))+SUMPRODUCT((I:I="Manual Close")*(M:M>0))'],
                    ['Losses:', '=SUMPRODUCT((I:I="Final TP4")*(M:M<0))+SUMPRODUCT((I:I="Stop Loss")*(M:M<0))+SUMPRODUCT((I:I="BE Close")*(M:M<0))+SUMPRODUCT((I:I="Manual Close")*(M:M<0))'],
                    ['Win Rate:', '=IF(E2>0,TEXT(E3/E2*100,"0.0")&"%","0%")']
                ]
            })
            
            # Separator (A6:T6)
            updates.append({
                'range': 'A6:T6',
                'values': [['═══════════════════════════════════════════════════════════════════════════']]
            })
            
            # Column headers (A8:N8)
            updates.append({
                'range': 'A8:N8',
                'values': [['Trade ID', 'Symbol', 'Direction', 'Zone', 'Entry Time', 'Entry Price', 
                           'Close Time', 'Close Price', 'Event Type', 'Lot Size', 'Risk %', 
                           'Duration', 'Realized P/L', 'Balance After']]
            })
            
            # Apply all data updates in ONE batch
            worksheet.batch_update(updates, value_input_option='USER_ENTERED')
            
            # Apply formatting in ONE batch
            worksheet.batch_format([
                {
                    'range': 'A1:T1',
                    'format': {
                        'backgroundColor': {'red': 0.2, 'green': 0.4, 'blue': 0.8},
                        'textFormat': {'bold': True, 'fontSize': 14, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}},
                        'horizontalAlignment': 'CENTER'
                    }
                },
                {
                    'range': 'A2:A4',
                    'format': {'textFormat': {'bold': True}}
                },
                {
                    'range': 'B2:B4',
                    'format': {
                        'textFormat': {'bold': True},
                        'numberFormat': {'type': 'CURRENCY', 'pattern': '$#,##0.00'}
                    }
                },
                {
                    'range': 'D2:D5',
                    'format': {'textFormat': {'bold': True}}
                },
                {
                    'range': 'A8:N8',
                    'format': {
                        'backgroundColor': {'red': 0.2, 'green': 0.4, 'blue': 0.8},
                        'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}},
                        'horizontalAlignment': 'CENTER'
                    }
                }
            ])
            
            # Merge cells
            worksheet.merge_cells('A1:T1')
            worksheet.merge_cells('A6:T6')
            
            print(f"[SHEETS] ✅ Daily sheet created: {sheet_name} | Starting: ${starting_balance:.2f}")
            return worksheet
            
    except Exception as e:
        print(f"[ERROR] Failed to create daily sheet: {e}")
        import traceback
        traceback.print_exc()
        return None

def log_entry_to_sheets(signal):
    """
    ENTRY events are logged to MASTER ONLY.
    Daily sheets only get rows when trades CLOSE.
    """
    with sheets_lock:
        try:
            # Log to master
            log_entry_to_master(signal)
            
            # ✅ NEW BEHAVIOR: Do NOT create row in daily sheet on entry
            print(f"[SHEETS] ℹ️ Entry logged to Master only (daily sheet will log on close): {signal.get('trade_id')}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to log entry: {e}")
            return False

def log_close_to_daily_sheet(outcome):
    """
    Log a close/partial close to the CLOSE DATE's daily sheet.
    FIXED: Balance calculation now uses last row's balance, not sum of all rows.
    """
    with sheets_lock:
        try:
            trade_id = outcome.get('trade_id', '')
            event = outcome.get('event', '')
            timestamp = outcome.get('timestamp', '')
            
            # Parse close date from timestamp
            try:
                close_dt = datetime.strptime(timestamp.replace('.', '-'), '%Y-%m-%d %H:%M:%S')
            except:
                close_dt = datetime.utcnow()
            
            account_number = outcome.get('account_number')
            sheet = get_or_create_daily_worksheet_for_date(account_number, close_dt)
            
            if not sheet:
                return False
            
            # Extract data
            symbol = outcome.get('symbol', '')
            direction = outcome.get('direction', '')
            zone_type = outcome.get('zone_type', '')
            entry_time = outcome.get('entry_time', '')
            entry_price = outcome.get('entry_price', 0)
            close_price = outcome.get('price', 0)
            close_time = timestamp
            lot_size = outcome.get('lot_size', '')
            
            # Determine event type
            if event == 'TP1_HIT':
                event_type = 'Partial TP1'
            elif event == 'TP2_HIT':
                event_type = 'Partial TP2'
            elif event == 'TP3_HIT':
                event_type = 'Partial TP3'
            elif event == 'TP4_HIT':
                event_type = 'Final TP4'
            elif event == 'SL_HIT':
                event_type = 'Stop Loss'
            elif event == 'BE_CLOSED':
                event_type = 'BE Close'
            elif event in ['MANUAL_CLOSE', 'CLOSED']:
                event_type = 'Manual Close'
            else:
                event_type = event
            
            # Get realized P/L (Net = Gross + Commission + Swap)
            gross_pnl = outcome.get('gross_profit', 0)
            commission = outcome.get('commission', 0)
            swap = outcome.get('swap', 0)
            
            # Calculate net P/L
            if gross_pnl != 0 or commission != 0 or swap != 0:
                realized_pnl = gross_pnl + commission + swap
            else:
                realized_pnl = outcome.get('profit', 0)
            
            # Get risk %
            if 'risk_percent' in outcome:
                risk_pct = outcome['risk_percent']
            else:
                risk_pct = 0.75 if zone_type == 'MAJOR' else 0.40
            risk_display = f"{risk_pct}%"
            
            # Calculate duration
            duration = ""
            if entry_time and close_time:
                duration = calculate_duration_from_times(entry_time, close_time)
            
            # ═══════════════════════════════════════════════════════════════
            # ✅ FIX: Use MT5 balance directly (most accurate)
            # ═══════════════════════════════════════════════════════════════
            
            # Get the actual MT5 balance AFTER this close (most accurate)
            if 'mt5_balance' in outcome:
                balance_after = outcome['mt5_balance']
            else:
                # Fallback: calculate from last row
                all_values = sheet.get_all_values()
                starting_balance_cell = sheet.cell(2, 2).value
                starting_balance = parse_dollar_value(starting_balance_cell)
                
                if len(all_values) > 8:
                    last_row_idx = len(all_values)
                    last_balance_cell = sheet.cell(last_row_idx, 14).value
                    if last_balance_cell:
                        balance_after = parse_dollar_value(last_balance_cell) + realized_pnl
                    else:
                        balance_after = starting_balance + realized_pnl
                else:
                    balance_after = starting_balance + realized_pnl
            # ═══════════════════════════════════════════════════════════════
            
            # Build row
            row = [
                trade_id,
                symbol,
                direction,
                zone_type,
                entry_time,
                entry_price,
                close_time,
                close_price,
                event_type,
                lot_size,
                risk_display,
                duration,
                realized_pnl,
                balance_after
            ]
            
            sheet.append_row(row, value_input_option='USER_ENTERED')
            
            print(f"[SHEETS] ✅ Close logged to {sheet.title}: {trade_id} | {event_type} | P/L: ${realized_pnl:.2f} | Balance: ${balance_after:.2f}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to log close to daily sheet: {e}")
            import traceback
            traceback.print_exc()
            return False

def update_trade_outcome(outcome):
    """
    REWRITTEN: On close events, log to daily sheet by CLOSE DATE.
    FIXED: Master updates on ANY final close (including TP1 when position fully closes)
    """
    try:
        event = outcome.get('event', '')
        trade_id = outcome.get('trade_id', '')
        is_final = outcome.get('is_final_close', False)
        
        # Update master log on FINAL close events
        if event in ['TP4_HIT', 'SL_HIT', 'MANUAL_CLOSE', 'BE_CLOSED', 'CLOSED']:
            update_master_on_close(outcome)
        elif event in ['TP1_HIT', 'TP2_HIT', 'TP3_HIT'] and is_final:
            # Position fully closed at early TP (e.g., 0.01 lots can't partial)
            update_master_on_close(outcome)
            print(f"[SHEETS] ✅ Master updated on early final close: {trade_id} | {event}")
        
        # Log to daily sheet by CLOSE DATE (ALL close events)
        if event in ['TP1_HIT', 'TP2_HIT', 'TP3_HIT', 'TP4_HIT', 'SL_HIT', 'BE_CLOSED', 'MANUAL_CLOSE', 'CLOSED']:
            log_close_to_daily_sheet(outcome)
        
        # Update ending balance on final closes
        if event in ['TP4_HIT', 'SL_HIT', 'MANUAL_CLOSE', 'BE_CLOSED', 'CLOSED'] or (event in ['TP1_HIT', 'TP2_HIT', 'TP3_HIT'] and is_final):
            if 'mt5_balance' in outcome:
                try:
                    timestamp = outcome.get('timestamp', '')
                    close_dt = datetime.strptime(timestamp.replace('.', '-'), '%Y-%m-%d %H:%M:%S')
                    account_number = outcome.get('account_number')
                    sheet = get_or_create_daily_worksheet_for_date(account_number, close_dt)
                    if sheet:
                        sheet.update_cell(3, 2, outcome['mt5_balance'])
                except:
                    pass
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to update trade outcome: {e}")
        return False 

# ═══════════════════════════════════════════════════════════════════
# ORB SHEET FUNCTIONS (UNCHANGED)
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
            headers = ['Trade ID', 'Date', 'Time', 'Symbol', 'Direction', 'Session', 'ORB High', 'ORB Low', 'ORB Mid', 'Entry Price', 'Stop Loss', 'TP1', 'TP2', 'TP3', 'Lot Size', 'Risk (pts)', 'Status', 'TP1 Hit', 'TP2 Hit', 'TP3 Hit', 'BE Moved', 'Final Outcome', 'Gross P/L', 'Commission', 'Swap', 'Net P/L', 'Cumulative', 'Exit Time', 'Duration']
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            worksheet.format('A1:AC1', {"backgroundColor": {"red": 0.0, "green": 0.6, "blue": 0.4}, "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}, "horizontalAlignment": "CENTER"})
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
    with sheets_lock:
        try:
            sheet = get_or_create_orb_daily_worksheet()
            if not sheet:
                return False
            now = datetime.utcnow()
            date_str = now.strftime('%Y-%m-%d')
            time_str = now.strftime('%H:%M:%S')
            if 'timestamp' in signal:
                try:
                    ts = signal['timestamp']
                    if ' ' in ts:
                        date_str = ts.split(' ')[0]
                        time_str = ts.split(' ')[1]
                except:
                    pass
            entry_price = signal.get('entry', signal.get('price', ''))
            lot_size = signal.get('lot_size', '')
            row = [signal.get('trade_id', ''), date_str, time_str, signal.get('symbol', ''), signal.get('direction', ''), signal.get('session', ''), signal.get('orb_high', ''), signal.get('orb_low', ''), signal.get('orb_mid', ''), entry_price, signal.get('stop_loss', ''), signal.get('tp1', ''), signal.get('tp2', ''), signal.get('tp3', ''), lot_size, signal.get('risk_pts', ''), 'Active', '', '', '', '', '', '', '', '', '', '', '', '']
            all_values = sheet.get_all_values()
            next_row = len(all_values) + 1
            sheet.insert_row(row, next_row, value_input_option='USER_ENTERED')
            print(f"[SHEETS] ✅ ORB ENTRY logged to {sheet.title} (row {next_row}): {signal.get('trade_id')} | Entry: {entry_price} | Lots: {lot_size}")
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
            row = [trade_id, date_str, time_str, symbol, direction, session, orb_high, orb_low, orb_mid, price, stop_loss, tp1, tp2, tp3, lot_size, risk_pts, 'Active', '', '', '', '', '', '', '', '', '', '', '', '']
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
# BACKGROUND PROCESSING
# ═══════════════════════════════════════════════════════════════════

def process_fibo_background(data):
    try:
        print(f"[Background] Processing FIBO: {data.get('trade_id')}")
        try:
            response = requests.post(f"{TAILSCALE_URL}/fibo", json=data, timeout=30)
            print(f"[Background] Forwarded FIBO to local: {response.status_code}")
        except Exception as e:
            print(f"[Background] Failed to forward FIBO: {e}")
    except Exception as e:
        print(f"[Background] Error processing FIBO: {e}")

def process_orb_background(data):
    try:
        print(f"[Background] Processing ORB: {data.get('trade_id')}")
        try:
            response = requests.post(f"{TAILSCALE_URL}/orb", json=data, timeout=30)
            print(f"[Background] Forwarded ORB to local: {response.status_code}")
        except Exception as e:
            print(f"[Background] Failed to forward ORB: {e}")
    except Exception as e:
        print(f"[Background] Error processing ORB: {e}")

def process_update_background(data):
    try:
        event = data.get('event', 'Unknown')
        trade_id = data.get('trade_id', 'Unknown')
        print(f"[Background] Processing UPDATE: {event} for {trade_id}")
        if ENABLE_GOOGLE_LOGGING:
            if event == 'ENTRY':
                log_entry_to_sheets(data)
            else:
                update_trade_outcome(data)
    except Exception as e:
        print(f"[Background] Error processing UPDATE: {e}")

def process_orb_update_background(data):
    try:
        event = data.get('event', 'Unknown')
        trade_id = data.get('trade_id', 'Unknown')
        print(f"[Background] Processing ORB_UPDATE: {event} for {trade_id}")
        if ENABLE_GOOGLE_LOGGING and GOOGLE_SHEET_ID_ORB:
            if event == 'ENTRY':
                log_orb_entry_to_sheets(data)
            else:
                update_orb_trade_outcome(data)
    except Exception as e:
        print(f"[Background] Error processing ORB_UPDATE: {e}")

# ═══════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "Trading Webhook Active",
        "version": "5.0 - Close Date Logging",
        "endpoints": {"fibo": "/fibo", "orb": "/orb", "update": "/update", "orb_update": "/orb_update", "health": "/health"},
        "forwards_to": TAILSCALE_URL,
        "google_logging": ENABLE_GOOGLE_LOGGING,
        "fibo_sheet_id": GOOGLE_SHEET_ID if GOOGLE_SHEET_ID else "Not configured",
        "orb_sheet_id": GOOGLE_SHEET_ID_ORB if GOOGLE_SHEET_ID_ORB else "Not configured",
        "master_sheet_id": GOOGLE_SHEET_ID_MASTER if GOOGLE_SHEET_ID_MASTER else "Not configured",
        "symbol_mappings": len(SYMBOL_MAP)
    })

@app.route('/fibo', methods=['POST'])
def fibo_webhook():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        trade_id = data.get('trade_id', 'Unknown')
        print(f"[FIBO] Received: {trade_id}")
        if 'symbol' in data:
            original_symbol = data['symbol']
            data['symbol'] = SYMBOL_MAP.get(original_symbol, original_symbol)
            if original_symbol != data['symbol']:
                print(f"[FIBO] Symbol mapped: {original_symbol} -> {data['symbol']}")
        response = jsonify({"status": "received", "trade_id": trade_id, "timestamp": datetime.utcnow().isoformat()})
        thread = Thread(target=process_fibo_background, args=(data,))
        thread.daemon = True
        thread.start()
        return response, 200
    except Exception as e:
        print(f"[ERROR] /fibo error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/orb', methods=['POST'])
def orb_webhook():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        trade_id = data.get('trade_id', 'Unknown')
        print(f"[ORB] Received: {trade_id}")
        if 'symbol' in data:
            original_symbol = data['symbol']
            data['symbol'] = SYMBOL_MAP.get(original_symbol, original_symbol)
            if original_symbol != data['symbol']:
                print(f"[ORB] Symbol mapped: {original_symbol} -> {data['symbol']}")
        response = jsonify({"status": "received", "trade_id": trade_id, "timestamp": datetime.utcnow().isoformat()})
        thread = Thread(target=process_orb_background, args=(data,))
        thread.daemon = True
        thread.start()
        return response, 200
    except Exception as e:
        print(f"[ERROR] /orb error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/update', methods=['POST'])
def update_webhook():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        event = data.get('event', 'Unknown')
        trade_id = data.get('trade_id', 'Unknown')
        print(f"[UPDATE] Received: {event} for {trade_id}")
        response = jsonify({"status": "received", "event": event, "trade_id": trade_id, "timestamp": datetime.utcnow().isoformat()})
        thread = Thread(target=process_update_background, args=(data,))
        thread.daemon = True
        thread.start()
        return response, 200
    except Exception as e:
        print(f"[ERROR] /update error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/orb_update', methods=['POST'])
def orb_update_webhook():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400
        event = data.get('event', 'Unknown')
        trade_id = data.get('trade_id', 'Unknown')
        profit = data.get('profit', 0)
        print(f"[ORB_UPDATE] Received: {event} for {trade_id} | P/L: ${profit:.2f}")
        response = jsonify({"status": "received", "event": event, "trade_id": trade_id, "timestamp": datetime.utcnow().isoformat()})
        thread = Thread(target=process_orb_update_background, args=(data,))
        thread.daemon = True
        thread.start()
        return response, 200
    except Exception as e:
        print(f"[ERROR] /orb_update error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "running",
        "version": "5.0 - Close Date Logging",
        "google_sheets_fibo": ENABLE_GOOGLE_LOGGING and bool(GOOGLE_SHEET_ID),
        "google_sheets_orb": ENABLE_GOOGLE_LOGGING and bool(GOOGLE_SHEET_ID_ORB),
        "google_sheets_master": ENABLE_GOOGLE_LOGGING and bool(GOOGLE_SHEET_ID_MASTER),
        "timestamp": datetime.utcnow().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"[STARTUP] Trading Webhook v5.0 - Close Date Logging")
    print(f"[STARTUP] Daily sheets now log by CLOSE date (realized P/L only)")
    print(f"[STARTUP] Starting on port {port}")
    app.run(host='0.0.0.0', port=port)