"""One-shot localhost UI for storing Council provider credentials on Windows."""

from __future__ import annotations

import ctypes
import hmac
import html
import secrets
import threading
import urllib.parse
import winreg
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


TOKEN = secrets.token_urlsafe(24)
MAX_BODY_BYTES = 64 * 1024


def save_user_environment_variable(name: str, value: str) -> None:
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_SET_VALUE,
    ) as environment_key:
        winreg.SetValueEx(environment_key, name, 0, winreg.REG_SZ, value)


def notify_environment_changed() -> None:
    hwnd_broadcast = 0xFFFF
    wm_settingchange = 0x001A
    smto_abortifhung = 0x0002
    result = ctypes.c_ulong()
    ctypes.windll.user32.SendMessageTimeoutW(
        hwnd_broadcast,
        wm_settingchange,
        0,
        "Environment",
        smto_abortifhung,
        2000,
        ctypes.byref(result),
    )


def page(content: str, *, title: str = "Council credentials") -> bytes:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light dark; font-family: Inter, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #101318; color: #edf1f7; }}
    main {{ max-width: 620px; margin: 56px auto; padding: 30px; background: #191e26;
            border: 1px solid #303846; border-radius: 16px; box-shadow: 0 16px 48px #0006; }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    p {{ color: #b8c1ce; line-height: 1.55; }}
    label {{ display: block; margin: 22px 0 8px; font-weight: 650; }}
    code {{ color: #9bd0ff; }}
    input {{ width: 100%; box-sizing: border-box; padding: 12px 14px; border-radius: 9px;
             border: 1px solid #475264; background: #0d1117; color: #fff; font: inherit; }}
    input:focus {{ outline: 2px solid #4da3ff; border-color: transparent; }}
    button {{ margin-top: 26px; width: 100%; padding: 13px; border: 0; border-radius: 9px;
              background: #2388ff; color: white; font-weight: 700; font-size: 15px; cursor: pointer; }}
    .note {{ margin-top: 18px; padding: 12px; border-radius: 9px; background: #222a35; font-size: 13px; }}
    .ok {{ color: #86efac; }}
    .error {{ color: #fca5a5; }}
  </style>
</head>
<body><main>{content}</main></body>
</html>""".encode("utf-8")


class CredentialHandler(BaseHTTPRequestHandler):
    server_version = "CouncilCredentialUI/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def send_page(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def token_from_query(self) -> str:
        return urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get(
            "token", [""]
        )[0]

    def do_GET(self) -> None:  # noqa: N802
        if not hmac.compare_digest(self.token_from_query(), TOKEN):
            self.send_page(403, page('<h1 class="error">链接无效或已过期</h1>'))
            return
        form = f"""
        <h1>配置 Kimi + DeepSeek</h1>
        <p>输入内容仅提交到本机 <code>127.0.0.1</code>，并保存为 Windows 用户环境变量。</p>
        <form method="post" action="/?token={urllib.parse.quote(TOKEN)}" autocomplete="off">
          <label for="deepseek">DeepSeek API Key</label>
          <input id="deepseek" name="deepseek" type="password" required autofocus
                 autocomplete="new-password" spellcheck="false"
                 placeholder="保存到 DEEPSEEK_API_KEY">
          <label for="kimi">Kimi / Moonshot API Key</label>
          <input id="kimi" name="kimi" type="password" required
                 autocomplete="new-password" spellcheck="false"
                 placeholder="保存到 MOONSHOT_API_KEY">
          <button type="submit">保存凭据</button>
        </form>
        <p class="note">不会写入仓库或 Council JSON。保存后请重启 Codex/Provider 进程。</p>
        """
        self.send_page(200, page(form))

    def do_POST(self) -> None:  # noqa: N802
        if not hmac.compare_digest(self.token_from_query(), TOKEN):
            self.send_page(403, page('<h1 class="error">链接无效或已过期</h1>'))
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self.send_page(400, page('<h1 class="error">提交内容无效</h1>'))
            return
        values = urllib.parse.parse_qs(
            self.rfile.read(content_length).decode("utf-8"), keep_blank_values=True
        )
        deepseek_key = values.get("deepseek", [""])[0].strip()
        kimi_key = values.get("kimi", [""])[0].strip()
        if not deepseek_key or not kimi_key:
            self.send_page(400, page('<h1 class="error">两个 Key 都不能为空</h1>'))
            return
        try:
            save_user_environment_variable("DEEPSEEK_API_KEY", deepseek_key)
            save_user_environment_variable("MOONSHOT_API_KEY", kimi_key)
            notify_environment_changed()
        except OSError as exc:
            self.send_page(
                500,
                page(
                    f'<h1 class="error">保存失败</h1><p>{html.escape(str(exc))}</p>'
                ),
            )
            return
        finally:
            deepseek_key = ""
            kimi_key = ""
        self.send_page(
            200,
            page(
                '<h1 class="ok">凭据已保存</h1>'
                '<p>已写入 <code>DEEPSEEK_API_KEY</code> 和 '
                '<code>MOONSHOT_API_KEY</code>。现在可以关闭此页并重启 Codex。</p>'
            ),
        )
        threading.Timer(1.0, self.server.shutdown).start()


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), CredentialHandler)
    port = server.server_address[1]
    print(f"http://127.0.0.1:{port}/?token={TOKEN}", flush=True)
    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    main()
