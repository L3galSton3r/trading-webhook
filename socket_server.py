import json
import socket
import threading
from flask import Flask, request, jsonify
from datetime import datetime
from queue import Queue
import time
import struct

app = Flask(__name__)

import logging
logging.getLogger('werkzeug').setLevel(logging.WARNING)
FLASK_PORT = 9091
SOCKET_PORT = 9090
SIGNAL_QUEUE = Queue()

print("════════════════════════════════════════════════════════════")
print("🚀 SOCKET SERVER v2.0 - HTTP HYBRID EDITION")
print("════════════════════════════════════════════════════════════")
print(f"🌐 Webhook: http://localhost:{FLASK_PORT}")
print(f"🔌 Socket: localhost:{SOCKET_PORT}")
print(f"📡 HTTP Signal: http://localhost:{FLASK_PORT}/get_signal")
print("════════════════════════════════════════════════════════════\n")

def socket_server():
    """Legacy socket server (kept for compatibility)"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind(('127.0.0.1', SOCKET_PORT))
        server.listen(5)
        
        print(f"✅ Socket listening on port {SOCKET_PORT}\n")
        
        while True:
            try:
                client, address = server.accept()
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                client.settimeout(5.0)
                
                try:
                    data = client.recv(1024)
                    
                    if not data:
                        client.close()
                        continue
                    
                    request_str = data.decode('utf-8', errors='ignore').strip()
                    
                    if not SIGNAL_QUEUE.empty():
                        signal = SIGNAL_QUEUE.get()
                        response = json.dumps(signal)
                    else:
                        response = "NONE"
                    
                    response_bytes = response.encode('utf-8')
                    
                    total_sent = 0
                    while total_sent < len(response_bytes):
                        sent = client.send(response_bytes[total_sent:])
                        if sent == 0:
                            raise RuntimeError("Socket connection broken")
                        total_sent += sent
                    
                    client.shutdown(socket.SHUT_WR)
                    time.sleep(0.1)
                    
                except:
                    pass
                finally:
                    try:
                        client.close()
                    except:
                        pass
            
            except:
                pass
    
    except Exception as e:
        print(f"[SERVER] Socket error: {e}")
    finally:
        server.close()

# ═══════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route('/', methods=['GET'])
def home():
    """Status check"""
    return jsonify({
        "status": "running",
        "version": "2.0-HTTP-HYBRID",
        "queue_size": SIGNAL_QUEUE.qsize()
    })

@app.route('/fibo', methods=['POST'])
def fibo():
    """Receive signals from TradingView"""
    try:
        signal = request.get_json()
        
        print("════════════════════════════════════════════════════════════")
        print("📐 FIBO Signal Received")
        print("════════════════════════════════════════════════════════════")
        print(f"⏱️  Time: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        print(f"🆔 Trade ID: {signal.get('trade_id', 'Unknown')}")
        print(f"📊 Symbol: {signal.get('symbol', 'Unknown')}")
        print(f"📈 Direction: {signal.get('direction', 'Unknown')}")
        print(f"🎯 Zone Type: {signal.get('zone_type', 'Unknown')}")
        print(f"🛑 Stop Loss: {signal.get('stop_loss', 'N/A')}")
        print(f"✅ TP1: {signal.get('tp1', 'N/A')}")
        print(f"✅ TP2: {signal.get('tp2', 'N/A')}")
        print(f"✅ TP3: {signal.get('tp3', 'N/A')}")
        print(f"✅ TP4: {signal.get('tp4', 'N/A')}")
        print("────────────────────────────────────────────────────────────")
        
        SIGNAL_QUEUE.put(signal)
        
        print(f"✅ Signal queued (Queue size: {SIGNAL_QUEUE.qsize()})")
        print("⏳ Waiting for EA to retrieve...")
        print("════════════════════════════════════════════════════════════")
        print()
        
        return jsonify({"status": "success", "queued": True}), 200
    
    except Exception as e:
        print(f"[ERROR] /fibo error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/orb', methods=['POST'])
def orb():
    """Receive ORB signals from TradingView"""
    try:
        signal = request.get_json()
        
        print("════════════════════════════════════════════════════════════")
        print("📊 ORB Signal Received")
        print("════════════════════════════════════════════════════════════")
        print(f"⏱️  Time: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        print(f"🆔 Trade ID: {signal.get('trade_id', 'Unknown')}")
        print(f"📊 Symbol: {signal.get('symbol', 'Unknown')}")
        print(f"📈 Direction: {signal.get('direction', 'Unknown')}")
        print("────────────────────────────────────────────────────────────")
        
        SIGNAL_QUEUE.put(signal)
        
        print(f"✅ Signal queued (Queue size: {SIGNAL_QUEUE.qsize()})")
        print("════════════════════════════════════════════════════════════")
        print()
        
        return jsonify({"status": "success", "queued": True}), 200
    
    except Exception as e:
        print(f"[ERROR] /orb error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "running",
        "queue_size": SIGNAL_QUEUE.qsize(),
        "timestamp": datetime.now().isoformat()
    })

# ═══════════════════════════════════════════════════════════════════
# 🌐 NEW: HTTP SIGNAL ENDPOINT (For MT5 EA)
# ═══════════════════════════════════════════════════════════════════
@app.route('/get_signal', methods=['GET'])
def get_signal():
    """
    HTTP endpoint for MT5 to poll for signals.
    Returns the next signal in queue, or {"status":"NONE"} if empty.
    """
    try:
        if not SIGNAL_QUEUE.empty():
            signal = SIGNAL_QUEUE.get()
            print(f"[HTTP] 📤 Sending signal to MT5: {signal.get('trade_id', 'Unknown')}")
            return jsonify(signal), 200
        else:
            # No signal in queue
            return jsonify({"status": "NONE"}), 200
    
    except Exception as e:
        print(f"[HTTP ERROR] {e}")
        return jsonify({"error": str(e)}), 500
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    # Start socket server in background (legacy support)
    socket_thread = threading.Thread(target=socket_server, daemon=True)
    socket_thread.start()
    
    # Start Flask HTTP server (primary method)
    print("⏳ Starting Flask HTTP server...")
    print("📡 MT5 should connect to: http://127.0.0.1:9091/get_signal")
    print()
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False, use_reloader=False)