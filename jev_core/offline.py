"""Block outbound model traffic while allowing local service connections."""
import socket


def enforce_offline():
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_resolve = socket.getaddrinfo

    def allowed(address):
        return isinstance(address, tuple) and str(address[0]) in {"127.0.0.1", "::1", "localhost"}

    def connect(sock, address):
        if not allowed(address):
            raise OSError("JEV uses local models; outbound connections are disabled")
        return original_connect(sock, address)

    def connect_ex(sock, address):
        return original_connect_ex(sock, address) if allowed(address) else 10013

    def resolve(host, *args, **kwargs):
        if host not in {None, "127.0.0.1", "::1", "localhost", "0.0.0.0"}:
            raise OSError("JEV uses local models; external DNS is disabled")
        return original_resolve(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = resolve
