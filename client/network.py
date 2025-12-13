import json
import socket
from typing import Any, Dict, Optional

#每個socket一個buffer，避免recv_json把多餘bytes丟掉
_sock_buf: Dict[int, bytearray] = {}

class ServerDisconnected(Exception):
    pass

def connect_to_server(host: str, port: int):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    return s

def _get_buf(sock: socket.socket) -> bytearray:
    key = sock.fileno()
    if key not in _sock_buf:
        _sock_buf[key] = bytearray()
    return _sock_buf[key]

def send_json(sock: socket.socket, obj: Dict[str, Any]):
    data = json.dumps(obj).encode("utf-8") + b"\n"
    sock.sendall(data)

def recv_json(sock: socket.socket) -> Optional[Dict[str, Any]]:
    buf = _get_buf(sock)

    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        buf.extend(chunk)

    line, rest = buf.split(b"\n", 1)
    # 把剩下的 bytes 留回 buffer（這就是修 bug 的關鍵）
    _sock_buf[sock.fileno()] = bytearray(rest)

    try:
        return json.loads(line.decode("utf-8"))
    except json.JSONDecodeError:
        return None

def recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = _get_buf(sock)

    while len(buf) < n:
        chunk = sock.recv(4096)
        if not chunk:
            return None
        buf.extend(chunk)

    data = bytes(buf[:n])
    # 把多出來的 bytes 留回 buffer
    _sock_buf[sock.fileno()] = buf[n:]
    return data
