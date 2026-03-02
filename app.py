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
    except:
        return None

def parse_dollar_value(value_str):
    try:
        if not value_str:
            return 0
        clean = str(value_str).replace('$', '').replace(',', '').strip()
        return float(clean) if clean else 0
    except:
        return 0

def get_or_create_daily_worksheet(account_number=None):
    try:
        spreadsheet = get_google_spreadsheet(GOOGLE_SHEET_ID)
        if not spreadsheet:
            return None
        if account_number:
            prefix = get_sheet_prefix(account_number)
        else:
            prefix = "UNKNOWN"
        today = datetime.utcnow()
        sheet_name = f"{prefix}-{today.strftime('%Y-%m-%d')}"
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            print(f"[SHEETS] Using existing Fibo sheet: {sheet_name}")
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            print(f"[SHEETS] Creating new Fibo sheet: {sheet_name}")
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=24)
            starting_balance = 0.0
            try:
                yesterday = f"{prefix}-{(datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')}"
                yesterday_sheet = spreadsheet.worksheet(yesterday)
                yesterday_balance = yesterday_sheet.cell(3, 2).value
                if yesterday_balance:
                    starting_balance = parse_dollar_value(yesterday_balance)
            except:
                pass
            worksheet.update('A1:X1', [['📊 DAILY PERFORMANCE SUMMARY']], value_input_option='USER_ENTERED')
            worksheet.merge_cells('A1:X1')
            worksheet.format('A1', {"backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8}, "textFormat": {"bold": True, "fontSize": 14, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}, "horizontalAlignment": "CENTER"})
            worksheet.update('A2', [['Starting Balance:']], value_input_option='USER_ENTERED')
            worksheet.update('B2', [[starting_balance]], value_input_option='USER_ENTERED')
            worksheet.format('A2:B2', {"textFormat": {"bold": True}})
            worksheet.format('B2', {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}})
            worksheet.update('A3', [['Current Balance:']], value_input_option='USER_ENTERED')
            worksheet.update('B3', [['=B2+SUMPRODUCT((LEN(V9:V)>0)*VALUE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(V9:V,"$",""),",","")," ","")))']], value_input_option='USER_ENTERED')
            worksheet.format('A3:B3', {"textFormat": {"bold": True}})
            worksheet.format('B3', {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}})
            worksheet.update('A4', [['Daily P/L:']], value_input_option='USER_ENTERED')
            worksheet.update('B4', [['=B3-B2']], value_input_option='USER_ENTERED')
            worksheet.update('C4', [['=IF(B2>0,TEXT(B4/B2*100,"0.00")&"%","0%")']], value_input_option='USER_ENTERED')
            worksheet.format('A4:C4', {"textFormat": {"bold": True}})
            worksheet.format('B4', {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}})
            worksheet.update('D2', [['Total Trades:']], value_input_option='USER_ENTERED')
            worksheet.update('E2', [['=COUNTIF(O9:O,"*Closed*")']], value_input_option='USER_ENTERED')
            worksheet.update('D3', [['Wins:']], value_input_option='USER_ENTERED')
            worksheet.update('E3', [['=COUNTIF(U9:U,"Win")+COUNTIF(U9:U,"Closed at BE*")']], value_input_option='USER_ENTERED')
            worksheet.update('D4', [['Losses:']], value_input_option='USER_ENTERED')
            worksheet.update('E4', [['=COUNTIF(U9:U,"Loss")']], value_input_option='USER_ENTERED')
            worksheet.update('D5', [['Win Rate:']], value_input_option='USER_ENTERED')
            worksheet.update('E5', [['=IF(E2>0,TEXT(E3/E2*100,"0.0")&"%","0%")']], value_input_option='USER_ENTERED')
            headers = ['Trade ID', 'Date', 'Time', 'Symbol', 'Direction', 'Zone Type', 'Entry Price', 'Stop Loss', 'TP1', 'TP2', 'TP3', 'TP4', 'Lot Size', 'Risk %', 'Status', 'TP1 Hit', 'TP2 Hit', 'TP3 Hit', 'TP4 Hit', 'BE Moved', 'Final Outcome', 'Profit/Loss', 'Exit Time', 'Duration']
            worksheet.update('A8:X8', [headers], value_input_option='USER_ENTERED')
            worksheet.format('A8:X8', {"backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8}, "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}, "horizontalAlignment": "CENTER"})
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
                    return worksheet, cell.row
            except:
                continue
        return None, None
    except:
        return None, None

def log_entry_to_sheets(signal):
    with sheets_lock:
        try:
            account_number = signal.get('account_number')
            sheet = get_or_create_daily_worksheet(account_number)
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
            zone_type = signal.get('zone_type', 'MINOR')
            risk_percent = 0.75 if zone_type == 'MAJOR' else 0.40
            entry_price = signal.get('entry', signal.get('price', ''))
            lot_size = signal.get('lot_size', '')
            row = [signal.get('trade_id', ''), date_str, time_str, signal.get('symbol', ''), signal.get('direction', ''), zone_type, entry_price, signal.get('stop_loss', ''), signal.get('tp1', ''), signal.get('tp2', ''), signal.get('tp3', ''), signal.get('tp4', ''), lot_size, f"{risk_percent}%", 'Active', '', '', '', '', '', '', '', '', '']
            sheet.append_row(row, value_input_option='USER_ENTERED')
            print(f"[SHEETS] ✅ ENTRY logged to {sheet.title}: {signal.get('trade_id')} | Entry: {entry_price} | Lots: {lot_size}")
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
    except:
        return None

def update_trade_outcome(outcome):
    try:
        worksheet, row_num = find_trade_in_all_sheets(outcome.get('trade_id', ''))
        if not worksheet or not row_num:
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
            elif price != 0:
                worksheet.update_cell(row_num, 8, price)
        elif event == 'BE_CLOSED':
            current_stage = outcome.get('current_stage', 1)
            worksheet.update_cell(row_num, 15, 'BE Hit - Closed')
            worksheet.update_cell(row_num, 21, f"Closed at BE (after TP{current_stage})")
            worksheet.update_cell(row_num, 23, timestamp)
            if cumulative_profit != 0:
                worksheet.update_cell(row_num, 22, f"${cumulative_profit:.2f}")
            duration = calculate_duration(outcome, worksheet, row_num)
            if duration:
                worksheet.update_cell(row_num, 24, duration)
        elif event == 'SL_HIT':
            worksheet.update_cell(row_num, 15, 'SL Hit - Closed')
            worksheet.update_cell(row_num, 23, timestamp)
            if profit != 0:
                worksheet.update_cell(row_num, 22, f"${profit:.2f}")
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
        print(f"[SHEETS] Updated: {outcome.get('trade_id')} | {event}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to update Fibo outcome: {e}")
        return False

def get_or_create_orb_daily_worksheet():
    try:
        spreadsheet = get_google_spreadsheet(GOOGLE_SHEET_ID_ORB)
        if not spreadsheet:
            return None
        today = datetime.utcnow()
        sheet_name = today.strftime('%Y-%m-%d')
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=30)
            headers = ['Trade ID', 'Date', 'Time', 'Symbol', 'Direction', 'Session', 'ORB High', 'ORB Low', 'ORB Mid', 'Entry Price', 'Stop Loss', 'TP1', 'TP2', 'TP3', 'Lot Size', 'Risk (pts)', 'Status', 'TP1 Hit', 'TP2 Hit', 'TP3 Hit', 'BE Moved', 'Final Outcome', 'Gross P/L', 'Commission', 'Swap', 'Net P/L', 'Cumulative', 'Exit Time', 'Duration']
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            worksheet.format('A1:AC1', {"backgroundColor": {"red": 0.0, "green": 0.6, "blue": 0.4}, "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}, "horizontalAlignment": "CENTER"})
            return worksheet
    except:
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
                    return worksheet, cell.row
            except:
                continue
        return None, None
    except:
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
                    return worksheet, rows
            except:
                continue
        return None, []
    except:
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
            sheet.append_row(row, value_input_option='USER_ENTERED')
            print(f"[SHEETS] ✅ ORB ENTRY logged: {signal.get('trade_id')}")
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
        timestamp = outcome.get('timestamp', '')
        worksheet, rows = find_all_orb_trade_rows(trade_id)
        if not worksheet or not rows:
            return False
        row_num = rows[0]
        if event == 'TP1_HIT':
            worksheet.update_cell(row_num, 17, 'TP1 Hit - Partial')
            worksheet.update_cell(row_num, 18, f"{timestamp} @ {price}")
        elif event == 'TP2_HIT':
            worksheet.update_cell(row_num, 17, 'TP2 Hit - Partial')
            worksheet.update_cell(row_num, 19, f"{timestamp} @ {price}")
        elif event == 'TP3_HIT':
            worksheet.update_cell(row_num, 17, 'TP3 Hit - Closed')
            worksheet.update_cell(row_num, 20, f"{timestamp} @ {price}")
            worksheet.update_cell(row_num, 22, 'Win')
            worksheet.update_cell(row_num, 28, timestamp)
        elif event == 'SL_HIT':
            worksheet.update_cell(row_num, 17, 'SL Hit - Closed')
            worksheet.update_cell(row_num, 28, timestamp)
            worksheet.update_cell(row_num, 22, 'Loss' if profit < 0 else 'Breakeven')
            if profit != 0:
                worksheet.update_cell(row_num, 23, f"${profit:.2f}")
        elif event == 'BE_MOVED':
            worksheet.update_cell(row_num, 21, f"Yes @ {timestamp}")
        print(f"[SHEETS] ORB {event} updated: {trade_id}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to update ORB outcome: {e}")
        return False

def process_fibo_background(data):
    try:
        requests.post(f"{TAILSCALE_URL}/fibo", json=data, timeout=10)
    except:
        pass

def process_orb_background(data):
    try:
        requests.post(f"{TAILSCALE_URL}/orb", json=data, timeout=10)
    except:
        pass

def process_update_background(data):
    try:
        event = data.get('event', 'Unknown')
        if ENABLE_GOOGLE_LOGGING:
            if event == 'ENTRY':
                log_entry_to_sheets(data)
            else:
                update_trade_outcome(data)
    except Exception as e:
        print(f"[ERROR] Background UPDATE: {e}")

def process_orb_update_background(data):
    try:
        event = data.get('event', 'Unknown')
        if ENABLE_GOOGLE_LOGGING and GOOGLE_SHEET_ID_ORB:
            if event == 'ENTRY':
                log_orb_entry_to_sheets(data)
            else:
                update_orb_trade_outcome(data)
    except Exception as e:
        print(f"[ERROR] Background ORB_UPDATE: {e}")

@app.route('/', methods=['GET'])
def home():
    return jsonify({"status": "Trading Webhook Active", "version": "4.1 - Stable"})

@app.route('/fibo', methods=['POST'])
def fibo_webhook():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error"}), 400
        if 'symbol' in data:
            data['symbol'] = SYMBOL_MAP.get(data['symbol'], data['symbol'])
        Thread(target=process_fibo_background, args=(data,), daemon=True).start()
        return jsonify({"status": "received"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/orb', methods=['POST'])
def orb_webhook():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error"}), 400
        if 'symbol' in data:
            data['symbol'] = SYMBOL_MAP.get(data['symbol'], data['symbol'])
        Thread(target=process_orb_background, args=(data,), daemon=True).start()
        return jsonify({"status": "received"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/update', methods=['POST'])
def update_webhook():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error"}), 400
        print(f"[UPDATE] Received: {data.get('event')} for {data.get('trade_id')}")
        Thread(target=process_update_background, args=(data,), daemon=True).start()
        return jsonify({"status": "received"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/orb_update', methods=['POST'])
def orb_update_webhook():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error"}), 400
        print(f"[ORB_UPDATE] Received: {data.get('event')} for {data.get('trade_id')}")
        Thread(target=process_orb_update_background, args=(data,), daemon=True).start()
        return jsonify({"status": "received"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "running", "version": "4.1"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"[STARTUP] Trading Webhook v4.1 - Stable")
    app.run(host='0.0.0.0', port=port)