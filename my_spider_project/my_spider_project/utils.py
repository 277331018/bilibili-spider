import os
import re

INVALID_WIN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, max_len: int = 80) -> str:
  name = INVALID_WIN_CHARS.sub("_", name.strip())
  name = name.rstrip(". ")
  if not name:
    name = "untitled"
  if len(name) > max_len:
    name = name[:max_len].rstrip(". ")
  return name


def find_chinese_font() -> str | None:
  candidates = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
  ]
  for path in candidates:
    if os.path.isfile(path):
      return path
  return None


def get_wordcloud_root(base_dir: str) -> str:
  out_dir = os.path.join(base_dir, "热点词云图")
  os.makedirs(out_dir, exist_ok=True)
  return out_dir


def get_video_output_dir(base_dir: str, title: str) -> str:
  """热点词云图/{视频标题}/ — 存放词云、弹幕.txt、评论.txt"""
  root = get_wordcloud_root(base_dir)
  folder = os.path.join(root, sanitize_filename(title))
  os.makedirs(folder, exist_ok=True)
  return folder
