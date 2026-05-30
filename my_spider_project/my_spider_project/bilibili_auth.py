"""B 站扫码登录与 Cookie 持久化。"""
import json
import os
import subprocess
import sys
import time

import requests

QR_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

HEADERS = {
  "User-Agent": (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
  ),
  "Referer": "https://www.bilibili.com",
  "Origin": "https://www.bilibili.com",
}


def cookie_file_path(base_dir: str) -> str:
  return os.path.join(base_dir, ".bilibili_cookies.json")


def qr_image_path(base_dir: str) -> str:
  return os.path.join(base_dir, "bilibili_login_qr.png")


def _session() -> requests.Session:
  s = requests.Session()
  s.headers.update(HEADERS)
  return s


def cookies_to_header(cookies: dict[str, str]) -> str:
  return "; ".join(f"{k}={v}" for k, v in cookies.items())


def load_cookies(base_dir: str) -> dict[str, str]:
  path = cookie_file_path(base_dir)
  if not os.path.isfile(path):
    return {}
  try:
    with open(path, encoding="utf-8") as f:
      data = json.load(f)
    if isinstance(data, dict):
      return {str(k): str(v) for k, v in data.items()}
  except (json.JSONDecodeError, OSError):
    pass
  return {}


def save_cookies(base_dir: str, cookies: dict[str, str]) -> None:
  path = cookie_file_path(base_dir)
  with open(path, "w", encoding="utf-8") as f:
    json.dump(cookies, f, ensure_ascii=False, indent=2)


def _session_cookies_dict(session: requests.Session) -> dict[str, str]:
  return {c.name: c.value for c in session.cookies}


def is_login_valid(cookies: dict[str, str]) -> bool:
  if not cookies.get("SESSDATA"):
    return False
  s = _session()
  s.cookies.update(cookies)
  try:
    r = s.get(NAV_URL, timeout=10)
    data = r.json()
    return data.get("code") == 0 and data.get("data", {}).get("isLogin") is True
  except (requests.RequestException, ValueError):
    return False


def _open_image(path: str) -> None:
  """用系统默认程序打开二维码图片。"""
  try:
    if sys.platform == "win32":
      os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
      subprocess.run(["open", path], check=False)
    else:
      subprocess.run(["xdg-open", path], check=False)
  except OSError:
    pass


def _show_qrcode(base_dir: str, qr_url: str) -> str:
  """
  生成二维码图片供 B 站 App 扫描。
  注意：qr_url 只能在 App 内扫码确认，浏览器打开会跳转下载 APK。
  """
  img_path = qr_image_path(base_dir)

  try:
    import qrcode
    qr = qrcode.QRCode(
      version=None,
      error_correction=qrcode.constants.ERROR_CORRECT_M,
      box_size=8,
      border=2,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(img_path)
  except ImportError as exc:
    raise RuntimeError(
      "缺少 qrcode 库，请执行: pip install qrcode[pil]"
    ) from exc

  print("\n" + "=" * 52)
  print("  B 站登录 · 请用手机 App 扫码（不要打开链接）")
  print("=" * 52)
  print("  1. 打开手机「哔哩哔哩」App")
  print("  2. 点击右下角「我的」→ 左上角扫一扫")
  print("  3. 扫描已弹出的二维码图片")
  print("  4. 在手机上点击「确认登录」")
  print()
  print("  [注意] 请勿在浏览器中打开二维码链接，否则会下载安装包")
  print(f"  二维码图片: {img_path}")
  print("=" * 52 + "\n")

  _open_image(img_path)
  return img_path


def qr_login(base_dir: str) -> dict[str, str]:
  os.makedirs(base_dir, exist_ok=True)
  s = _session()
  s.get("https://www.bilibili.com", timeout=10)

  r = s.get(QR_GENERATE, timeout=10)
  data = r.json()
  if data.get("code") != 0:
    raise RuntimeError(f"获取登录二维码失败: {data.get('message')}")

  qr_url = data["data"]["url"]
  qrcode_key = data["data"]["qrcode_key"]
  _show_qrcode(base_dir, qr_url)
  print("等待扫码确认（120 秒内有效）…")

  for _ in range(60):
    time.sleep(2)
    pr = s.get(QR_POLL, params={"qrcode_key": qrcode_key}, timeout=10)
    pdata = pr.json()
    code = pdata.get("data", {}).get("code")

    if code == 0:
      cookies = _session_cookies_dict(s)
      if not cookies.get("SESSDATA"):
        raise RuntimeError("登录回调成功但未获取到 Cookie，请重试")
      save_cookies(base_dir, cookies)
      qr_path = qr_image_path(base_dir)
      if os.path.isfile(qr_path):
        try:
          os.remove(qr_path)
        except OSError:
          pass
      print(f"\n登录成功！Cookie 已保存到 {cookie_file_path(base_dir)}")
      return cookies

    if code in (86038, 86039):
      raise RuntimeError("二维码已过期，请重新运行")
    if code == 86090:
      print("已扫码，请在手机上点击「确认登录」…", end="\r", flush=True)
    elif code == 86101:
      print("等待扫码…", end="\r", flush=True)

  raise RuntimeError("登录超时（120 秒），请重新运行")


def ensure_login(base_dir: str, *, force: bool = False, quiet: bool = False) -> dict[str, str]:
  """确保已登录；Cookie 持久化到项目目录。"""
  os.makedirs(base_dir, exist_ok=True)
  cookies = load_cookies(base_dir)
  if not force and cookies and is_login_valid(cookies):
    if not quiet:
      print("已加载本地登录状态（Cookie 有效）", flush=True)
    return cookies
  if cookies and not force and not quiet:
    print("本地 Cookie 已失效，需要重新登录…", flush=True)
  return qr_login(base_dir)


def get_cookie_header(base_dir: str) -> str:
  cookies = load_cookies(base_dir)
  return cookies_to_header(cookies)
