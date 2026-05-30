"""Downloader 中间件：注入 B 站登录 Cookie。"""
import os

from scrapy import signals

from my_spider_project.bilibili_auth import get_cookie_header


class BilibiliCookieMiddleware:
  """为所有 B 站请求注入 Cookie。"""

  def __init__(self, base_dir: str):
    self.base_dir = base_dir
    self.cookie_header = ""

  @classmethod
  def from_crawler(cls, crawler):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mw = cls(base_dir)
    crawler.signals.connect(mw.spider_opened, signal=signals.spider_opened)
    return mw

  def spider_opened(self, spider):
    if spider.name != "bilibili":
      return
    header = (os.environ.get("BILIBILI_COOKIE") or "").strip()
    if not header:
      header = (spider.settings.get("BILIBILI_COOKIE") or "").strip()
    if not header:
      header = get_cookie_header(self.base_dir)
    self.cookie_header = header
    spider.bilibili_cookie = header
    if header:
      spider.logger.info("Cookie 已注入（%d 字符）", len(header))
    else:
      spider.logger.warning("未找到 Cookie，部分接口可能受限")

  def process_request(self, request, spider):
    if spider.name != "bilibili":
      return None
    cookie = getattr(spider, "bilibili_cookie", None) or self.cookie_header
    if cookie:
      request.headers[b"Cookie"] = cookie.encode("utf-8")
    return None
