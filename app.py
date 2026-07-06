from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from datetime import datetime
import json
import os

MESSAGES_FILE = "messages.json"
PASSWORD = "ninjaamk"

def load_messages():
    if not os.path.exists(MESSAGES_FILE):
        return []
    with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_messages(messages):
    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

def page(username="", search=""):
    messages = load_messages()
    if search:
        messages = [m for m in messages if search.lower() in m["text"].lower() or search.lower() in m["user"].lower()]

    msgs_html = ""
    for i, m in enumerate(messages, start=1):
        msgs_html += f"""
        <div class="msg">
            <b>#{i} [{m['user']}]</b>
            <small>{m['time']}</small>
            <p>{m['text']}</p>
        </div>
        """

    return f"""
    <html>
    <head>
        <title>YChat</title>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial; background:#111; color:white; padding:30px; }}
            .box {{ max-width:800px; margin:auto; }}
            input, textarea, button {{ width:100%; padding:12px; margin:7px 0; border-radius:8px; border:0; }}
            button {{ background:#00a884; color:white; font-weight:bold; cursor:pointer; }}
            .danger {{ background:#c0392b; }}
            .msg {{ background:#222; padding:15px; margin:10px 0; border-radius:10px; }}
            small {{ color:#aaa; float:right; }}
            a {{ color:#00ffcc; }}
        </style>
    </head>
    <body>
        <div class="box">
            <h1>💬 YChat</h1>
            <p>Welcome, <b>{username}</b></p>

            <form method="POST" action="/send">
                <textarea name="text" placeholder="Write your message..." required></textarea>
                <button>Send Message</button>
            </form>

            <form method="GET" action="/">
                <input name="search" placeholder="Search messages..." value="{search}">
                <button>Search</button>
            </form>

            <form method="POST" action="/delete_last">
                <button class="danger">Delete Last Message</button>
            </form>

            <form method="POST" action="/delete_all">
                <button class="danger">Delete All Messages</button>
            </form>

            <hr>
            <h2>Messages</h2>
            {msgs_html if msgs_html else "<p>No messages yet.</p>"}
        </div>
    </body>
    </html>
    """

def login_page():
    return """
    <html>
    <head>
        <title>YChat Login</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial; background:#111; color:white; padding:30px; }
            .box { max-width:400px; margin:auto; margin-top:100px; }
            input, button { width:100%; padding:12px; margin:7px 0; border-radius:8px; border:0; }
            button { background:#00a884; color:white; font-weight:bold; }
        </style>
    </head>
    <body>
        <div class="box">
            <h1>🔐 YChat Login</h1>
            <form method="POST" action="/login">
                <input name="username" placeholder="Your name" required>
                <input name="password" placeholder="Password" type="password" required>
                <button>Login</button>
            </form>
        </div>
    </body>
    </html>
    """

class YChatHandler(BaseHTTPRequestHandler):
    def get_username(self):
        cookie = self.headers.get("Cookie", "")
        if "username=" in cookie:
            return cookie.split("username=")[1].split(";")[0]
        return ""

    def send_html(self, html, cookie=None):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def redirect(self, path="/"):
        self.send_response(303)
        self.send_header("Location", path)
        self.end_headers()

    def do_GET(self):
        username = self.get_username()
        if not username:
            self.send_html(login_page())
            return

        query = parse_qs(urlparse(self.path).query)
        search = query.get("search", [""])[0]
        self.send_html(page(username, search))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length).decode("utf-8")
        form = parse_qs(data)

        if self.path == "/login":
            username = form.get("username", [""])[0]
            password = form.get("password", [""])[0]

            if password == PASSWORD:
                self.send_response(303)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"username={username}")
                self.end_headers()
            else:
                self.send_html(login_page() + "<h3 style='color:red'>Wrong password</h3>")
            return

        username = self.get_username()
        if not username:
            self.redirect("/")
            return

        if self.path == "/send":
            text = form.get("text", [""])[0]
            messages = load_messages()
            messages.append({
                "user": username,
                "time": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "text": text
            })
            save_messages(messages)
            self.redirect("/")

        elif self.path == "/delete_last":
            messages = load_messages()
            if messages:
                messages.pop()
                save_messages(messages)
            self.redirect("/")

        elif self.path == "/delete_all":
            save_messages([])
            self.redirect("/")

server = ThreadingHTTPServer(("127.0.0.1", 8000), YChatHandler)
print("YChat is running...")
print("Open this link: http://127.0.0.1:8000")
server.serve_forever()