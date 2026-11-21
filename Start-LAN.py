#!/usr/bin/env python3
"""Shared Wi-Fi host for the Mouse After Dark game."""
import argparse
from collections import deque
from contextlib import ExitStack
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
import threading
import time
import webbrowser

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
ROOM_PATH = re.compile(r"/mouse-lan/rooms/([23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{6})/(join|sync|leave)")
MAX_BODY = 128_000
MAX_PACKET = 3600
ROOM_WAIT_SECONDS = 600
ACTIVE_IDLE_SECONDS = 180


class RelayError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


@dataclass
class Player:
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    seen: float = field(default_factory=time.monotonic)
    sent: int = 0
    pending: deque = field(default_factory=deque)


@dataclass
class Room:
    created: float = field(default_factory=time.monotonic)
    host: Player = field(default_factory=Player)
    guest: Player | None = None

    def expired(self, now):
        if self.guest is None:
            return now - self.created > ROOM_WAIT_SECONDS
        return now - min(self.host.seen, self.guest.seen) > ACTIVE_IDLE_SECONDS


class Relay:
    def __init__(self):
        self.rooms = {}
        self.guard = threading.Lock()

    def exchange(self, code, action, body):
        with self.guard:
            now = time.monotonic()
            self.rooms = {key: room for key, room in self.rooms.items() if not room.expired(now)}
            if action == "create":
                if len(self.rooms) >= 32:
                    raise RelayError(503, "房间已满，请稍后再试。")
                while True:
                    code = "".join(secrets.choice(ALPHABET) for _ in range(6))
                    if code not in self.rooms:
                        break
                room = self.rooms[code] = Room()
                return {"code": code, "key": room.host.token}

            room = self.rooms.get(code)
            if room is None:
                raise RelayError(410, "房间已关闭或过期，请让队友创建新房间。")
            if action == "join":
                if room.guest is not None:
                    raise RelayError(409, "这个房间已经有两位玩家。")
                room.guest = Player()
                return {"code": code, "key": room.guest.token}

            key = body.get("key")
            if not isinstance(key, str) or not key.isascii() or len(key) > 128:
                raise RelayError(403, "无法确认房间身份。")
            if secrets.compare_digest(key, room.host.token):
                sender, partner = room.host, room.guest
            elif room.guest and secrets.compare_digest(key, room.guest.token):
                sender, partner = room.guest, room.host
            else:
                raise RelayError(403, "无法确认房间身份。")
            if action == "leave":
                del self.rooms[code]
                return {"left": True}

            ack, packets = body.get("ack"), body.get("packets")
            if (type(ack) is not int or not 0 <= ack <= (partner.sent if partner else 0)
                    or not isinstance(packets, list) or len(packets) > 32):
                raise RelayError(400, "房间消息无效，请重新加入。")
            sent = sender.sent
            additions = []
            for packet in packets:
                if (not isinstance(packet, list) or len(packet) != 2 or type(packet[0]) is not int
                        or packet[0] < 1 or not isinstance(packet[1], str) or len(packet[1]) > MAX_PACKET):
                    raise RelayError(400, "房间消息无效，请重新加入。")
                sequence, raw = packet
                if sequence <= sent:
                    continue
                if not partner or sequence != sent + 1:
                    raise RelayError(400, "房间消息顺序不一致，请重新加入。")
                additions.append((sequence, raw))
                sent = sequence
            if partner and len(partner.pending) + len(additions) > 768:
                raise RelayError(409, "队友网络长时间无响应，请重新加入。")
            sender.seen = now
            while sender.pending and sender.pending[0][0] <= ack:
                sender.pending.popleft()
            if partner:
                partner.pending.extend(additions)
                sender.sent = sent
            return {"paired": partner is not None, "accepted": sender.sent, "packets": list(sender.pending)[:48]}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MouseAfterDarkLAN"

    def log_message(self, _format, *_args):
        return

    def output(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def respond(self, status, payload):
        self.output(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/mouse-lan/status":
            self.respond(200, {"relay": 1, "origin": self.server.advertised_origin})
        elif path in ("/", "/index.html", "/MouseAfterDark.html"):
            self.output(200, self.server.game, "text/html; charset=utf-8")
        else:
            self.respond(404, {"error": "找不到这个页面。"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/mouse-lan/rooms":
            room, action = None, "create"
        else:
            match = ROOM_PATH.fullmatch(path)
            if not match:
                self.respond(404, {"error": "找不到这个房间入口。"})
                return
            room, action = match.groups()
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 2 <= size <= MAX_BODY or self.headers.get_content_type() != "application/json":
                raise ValueError("invalid input")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("not an object")
        except (ValueError, UnicodeError):
            self.close_connection = True
            self.respond(400, {"error": "房间请求格式不对。"})
            return
        try:
            self.respond(200, self.server.relay.exchange(room, action, body))
        except RelayError as error:
            self.respond(error.status, {"error": str(error)})


def lan_address():
    def usable(address):
        ip = ipaddress.ip_address(address)
        return not (ip.is_loopback or ip.is_link_local or ip.is_unspecified)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        try:
            connection.connect(("192.0.2.1", 9))
            found = connection.getsockname()[0]
            if usable(found):
                return found
        except OSError:
            pass
    # macOS may deny route probes; the primary Wi-Fi interface still exposes its address.
    for interface in ("en0", "en1"):
        try:
            info = subprocess.run(["/sbin/ifconfig", interface], capture_output=True, text=True,
                                  check=False, timeout=2).stdout
            for found in re.findall(r"\binet (\d+\.\d+\.\d+\.\d+)\b", info):
                if usable(found):
                    return found
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        return next(ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if usable(ip))
    except (OSError, StopIteration):
        return "127.0.0.1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", help="Use a single network interface instead of Wi-Fi and loopback")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--host-ip", help="IPv4 address to share with the other player")
    parser.add_argument("--lang", choices=("zh", "en"), default="zh", help="Launcher and initial browser language")
    parser.add_argument("--no-browser", action="store_true")
    options = parser.parse_args()
    english = options.lang == "en"
    query = "?lang=en" if english else ""
    game = Path(__file__).with_name("index.html").read_bytes()
    address = options.host_ip or (lan_address() if options.listen in (None, "0.0.0.0") else options.listen)
    primary = options.listen or "127.0.0.1"
    with ExitStack() as stack:
        server = stack.enter_context(ThreadingHTTPServer((primary, options.port), Handler))
        servers = [server]
        if options.listen is None and address != primary:
            servers.append(stack.enter_context(ThreadingHTTPServer((address, server.server_port), Handler)))
        relay = Relay()
        for listener in servers:
            listener.relay = relay
            listener.game = game
            listener.advertised_origin = f"http://{address}:{server.server_port}"
        origin = f"http://{address}:{server.server_port}"
        open_origin = f"http://{primary if primary != '0.0.0.0' else '127.0.0.1'}:{server.server_port}"
        if english:
            print(f"Mouse After Dark · Same-Wi-Fi Co-op\nOpen {origin}/{query}", flush=True)
            if open_origin != origin:
                print(f"The host can also open {open_origin}/{query}", flush=True)
            if address.startswith("127."):
                print("This address only works on the host. Use --host-ip to enter the host’s Wi-Fi IPv4 address.", flush=True)
            print("Keep this window open. Copy the invite link from the game lobby to share with your partner.", flush=True)
            print("Press Ctrl+C to stop.", flush=True)
        else:
            print(f"墙缝夜行 · 同 Wi‑Fi 联机\n打开 {origin}/", flush=True)
            if open_origin != origin:
                print(f"开房电脑也可打开 {open_origin}/", flush=True)
            if address.startswith("127."):
                print("当前显示的是本机地址。两台设备联机时，可用 --host-ip 指定此电脑的 Wi‑Fi IPv4 地址。", flush=True)
            print("保持此窗口打开。开始游戏后，在大厅里复制邀请链接发给队友。按 Ctrl+C 停止。", flush=True)
        if not options.no_browser:
            threading.Timer(.25, webbrowser.open, args=(open_origin+"/"+query,)).start()
        for listener in servers[1:]:
            threading.Thread(target=listener.serve_forever, daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nCo-op session ended." if english else "\n联机已结束。")
        finally:
            for listener in servers[1:]:
                listener.shutdown()


if __name__ == "__main__":
    main()
