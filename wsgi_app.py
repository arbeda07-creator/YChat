from urllib.parse import parse_qs
from datetime import datetime
from app import load_messages, save_messages, page, login_page, PASSWORD

def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")
    cookie = environ.get("HTTP_COOKIE", "")
    username = ""

    if "username=" in cookie:
        username = cookie.split("username=")[-1].split(";")[0]

    def send(html="", status="200 OK", headers=None):
        h = [("Content-Type", "text/html; charset=utf-8")]
        if headers:
            h += headers
        start_response(status, h)
        return [html.encode("utf-8")]

    if path == "/logout":
        return send("", "303 See Other", [("Location", "/"), ("Set-Cookie", "username=; Max-Age=0")])

    if method == "POST":
        length = int(environ.get("CONTENT_LENGTH", 0) or 0)
        data = environ["wsgi.input"].read(length).decode("utf-8")
        form = parse_qs(data)

        if path == "/login":
            username = form.get("username", [""])[0]
            password = form.get("password", [""])[0]
            if password == PASSWORD:
                return send("", "303 See Other", [("Location", "/"), ("Set-Cookie", f"username={username}")])
            return send(login_page() + "<h3 style='color:red'>Wrong password</h3>")

        if path == "/send" and username:
            text = form.get("text", [""])[0]
            messages = load_messages()
            messages.append({"user": username, "time": datetime.now().strftime("%d/%m/%Y %H:%M"), "text": text})
            save_messages(messages)
            return send("", "303 See Other", [("Location", "/")])

    if not username:
        return send(login_page())

    return send(page(username))
