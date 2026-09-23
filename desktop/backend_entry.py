"""Private loopback server for Electron; supports the embeddable Windows Python."""
from __future__ import annotations

import asyncio
import ctypes
import json
import os
import socket
import sys
import threading
import time


def enforce_offline():
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def allowed(address):
        return isinstance(address, tuple) and str(address[0]) in {"127.0.0.1", "::1", "localhost"}

    def connect(sock, address):
        if not allowed(address):
            raise OSError("JEV desktop is offline: external connections are disabled")
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if not allowed(address):
            return 10013
        return original_connect_ex(sock, address)

    def getaddrinfo(host, *args, **kwargs):
        if host not in {None, "127.0.0.1", "::1", "localhost"}:
            raise OSError("JEV desktop is offline: external DNS is disabled")
        return original_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = getaddrinfo


def monitor_parent(parent_pid):
    if os.name != "nt" or not parent_pid:
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, parent_pid)
    if not handle:
        os._exit(0)
    try:
        if kernel.WaitForSingleObject(handle, 0xFFFFFFFF) == 0:
            os._exit(0)
    finally:
        kernel.CloseHandle(handle)


def main():
    sys.dont_write_bytecode = True
    if not os.getenv("JEV_DESKTOP_TOKEN"):
        raise RuntimeError("Launch the desktop backend through JevDocumentSearchDesktop.exe")
    enforce_offline()
    threading.Thread(target=monitor_parent, args=(int(os.getenv("JEV_PARENT_PID", "0")),), daemon=True).start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Binding port zero removes the probe-then-bind port allocation race.
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    os.environ["JEV_DESKTOP_ORIGIN"] = f"http://127.0.0.1:{port}"
    import uvicorn
    from app import app
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False, loop="asyncio", http="h11", ws="none", timeout_graceful_shutdown=3)
    server = uvicorn.Server(config)

    @app.post("/api/desktop/shutdown")
    async def shutdown():
        # Authentication is enforced by app.py before every route, including this one.
        asyncio.get_running_loop().call_later(0.1, setattr, server, "should_exit", True)
        return {"stopping": True}

    print("JEV_READY " + json.dumps({"port": port, "pid": os.getpid()}), flush=True)
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
