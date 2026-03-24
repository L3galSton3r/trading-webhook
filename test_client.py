import socket

print("🔍 Testing socket connection...")

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('127.0.0.1', 9090))

print("✅ Connected")

sock.sendall(b'GET_SIGNAL')
print("✅ Sent request")

response = sock.recv(1024)
print(f"✅ Received: {response.decode('utf-8')}")

sock.close()
print("✅ Done - Socket works perfectly!")