"""爬虫进度条（单条 tqdm，兼容 Windows 终端）。"""
from __future__ import annotations

import sys
import threading

try:
  from tqdm import tqdm
except ImportError:
  tqdm = None


class CrawlProgress:
  _instance: CrawlProgress | None = None
  _lock = threading.Lock()

  def __init__(self):
    self.enabled = tqdm is not None and sys.stdout.isatty()
    self.total_videos = 10
    self.done_videos = 0
    self._bar = None
    self._phase = ""
    self._inner_lock = threading.Lock()

  @classmethod
  def get(cls) -> CrawlProgress:
    with cls._lock:
      if cls._instance is None:
        cls._instance = CrawlProgress()
      return cls._instance

  @classmethod
  def reset(cls) -> None:
    with cls._lock:
      if cls._instance:
        cls._instance.close()
      cls._instance = None

  def start(self, total_videos: int = 10) -> None:
    self.total_videos = max(1, total_videos)
    self.done_videos = 0
    self.close()
    if not self.enabled:
      print(f"[进度] 开始抓取，共 {self.total_videos} 个视频", flush=True)
      return
    self._bar = tqdm(
      total=self.total_videos,
      desc="抓取进度",
      unit="视频",
      file=sys.stdout,
      dynamic_ncols=True,
      leave=True,
      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] {postfix}",
    )

  def set_total_videos(self, total: int) -> None:
    self.total_videos = max(1, total)
    if self.enabled and self._bar:
      self._bar.total = self.total_videos
      self._bar.refresh()
    elif not self.enabled:
      print(f"[进度] 将抓取 {self.total_videos} 个视频", flush=True)

  def set_phase(self, message: str) -> None:
    self._phase = str(message)[:40]
    if not self.enabled:
      return
    with self._inner_lock:
      if self._bar:
        self._bar.set_postfix_str(self._phase, refresh=False)
        self._bar.refresh()

  def complete_video(self, title: str) -> None:
    with self._inner_lock:
      self.done_videos += 1
      short = str(title)[:28]
      if self.enabled and self._bar:
        self._bar.update(1)
        self._bar.set_postfix_str(f"已完成 {short}")
      else:
        print(
          f"[进度] {self.done_videos}/{self.total_videos} 已完成: {short}",
          flush=True,
        )

  def close(self) -> None:
    with self._inner_lock:
      if self._bar:
        self._bar.close()
        self._bar = None
