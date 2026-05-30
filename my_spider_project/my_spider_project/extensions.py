"""Scrapy 扩展：登录检查、进度条。"""
from __future__ import annotations

import os

from scrapy import signals

from my_spider_project.bilibili_auth import (
  cookies_to_header,
  ensure_login,
  load_cookies,
)
from my_spider_project.progress_tracker import CrawlProgress


class BilibiliLoginExtension:
  """爬虫启动时加载 Cookie（run_bilibili 已登录则跳过重复校验）。"""

  def __init__(self, base_dir: str, force_login: bool):
    self.base_dir = base_dir
    self.force_login = force_login

  @classmethod
  def from_crawler(cls, crawler):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ext = cls(base_dir, crawler.settings.getbool("BILIBILI_FORCE_LOGIN", False))
    crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
    return ext

  def spider_opened(self, spider):
    if spider.name != "bilibili":
      return

    skip_check = spider.settings.getbool("BILIBILI_SKIP_AUTH_CHECK", False)
    header = (os.environ.get("BILIBILI_COOKIE") or "").strip()
    if not header:
      header = (spider.settings.get("BILIBILI_COOKIE") or "").strip()

    if skip_check and header:
      spider.bilibili_cookie = header
      spider.logger.info("使用已验证 Cookie 启动爬虫")
      return

    if skip_check and not header:
      cookies = load_cookies(self.base_dir)
      if cookies.get("SESSDATA"):
        spider.bilibili_cookie = cookies_to_header(cookies)
        spider.logger.info("已从本地文件加载 Cookie")
        return

    cookies = ensure_login(self.base_dir, force=self.force_login, quiet=True)
    spider.bilibili_cookie = cookies_to_header(cookies)
    spider.logger.info("B 站登录就绪（Cookie 条目: %d）", len(cookies))


class BilibiliProgressExtension:
  """抓取过程进度条（单条，避免 Windows 终端卡死）。"""

  @classmethod
  def from_crawler(cls, crawler):
    ext = cls()
    crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
    crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
    crawler.signals.connect(ext.response_received, signal=signals.response_received)
    return ext

  def spider_opened(self, spider):
    if spider.name != "bilibili":
      return
    CrawlProgress.reset()
    total = int(getattr(spider, "max_videos", 10) or 10)
    CrawlProgress.get().start(total_videos=total)
    CrawlProgress.get().set_phase("初始化")

  def response_received(self, response, request, spider):
    if spider.name != "bilibili":
      return
    progress = CrawlProgress.get()
    url = response.url
    if "search/type" in url:
      progress.set_phase("搜索视频")
    elif "web-interface/view" in url:
      progress.set_phase("获取视频信息")
    elif "comment.bilibili.com" in url or "dm/web/seg.so" in url:
      progress.set_phase("抓取弹幕")
    elif "reply" in url:
      progress.set_phase("抓取评论")

  def spider_closed(self, spider, reason):
    if spider.name != "bilibili":
      return
    progress = CrawlProgress.get()
    progress.set_phase(f"完成 ({reason})")
    progress.close()
