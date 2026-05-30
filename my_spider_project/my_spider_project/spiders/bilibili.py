import re
from urllib.parse import quote, urlencode

import scrapy

from my_spider_project.danmaku_parser import (
  parse_seg_protobuf,
  parse_xml_danmaku,
  segment_count,
)
from my_spider_project.items import BilibiliVideoItem
from my_spider_project.progress_tracker import CrawlProgress

SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
DM_XML_URL = "https://comment.bilibili.com/{cid}.xml"
DM_SEG_URL = "https://api.bilibili.com/x/v2/dm/web/seg.so"
REPLY_MAIN_URL = "https://api.bilibili.com/x/v2/reply/main"
REPLY_LEGACY_URL = "https://api.bilibili.com/x/v2/reply"
MAX_COMMENT_PAGES = 100
MAX_COMMENTS = 10000
MAX_VIDEO_PARTS = 30


class BilibiliSpider(scrapy.Spider):
  name = "bilibili"
  allowed_domains = ["bilibili.com", "api.bilibili.com", "comment.bilibili.com"]
  custom_settings = {
    "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    "DOWNLOAD_DELAY": 0.6,
    "COOKIES_ENABLED": True,
    "HTTPERROR_ALLOWED_CODES": [412],
  }

  def __init__(self, keyword=None, max_videos=10, *args, **kwargs):
    super().__init__(*args, **kwargs)
    if not keyword or not str(keyword).strip():
      raise ValueError(
        "请通过 -a keyword=关键字 传入搜索词，例如: scrapy crawl bilibili -a keyword=Python"
      )
    self.keyword = str(keyword).strip()
    self.max_videos = max(1, min(10, int(max_videos or 10)))

  async def start(self):
    yield scrapy.Request(
      "https://www.bilibili.com",
      callback=self.start_search,
      headers=self._api_headers("https://www.bilibili.com"),
      dont_filter=True,
      errback=self.errback_log,
    )

  def start_search(self, response):
    yield scrapy.Request(
      f"{SEARCH_URL}?{urlencode(self._search_params(1))}",
      callback=self.parse_search,
      cb_kwargs={"page": 1, "collected": []},
      headers=self._api_headers(),
      errback=self.errback_log,
    )

  def _search_params(self, page):
    return {
      "search_type": "video",
      "keyword": self.keyword,
      "page": page,
      "order": "click",
      "page_size": 20,
    }

  def _video_referer(self, bvid):
    return f"https://www.bilibili.com/video/{bvid}"

  def _api_headers(self, referer=None):
    if referer is None:
      referer = f"https://search.bilibili.com/all?keyword={quote(self.keyword)}"
    headers = {
      "Referer": referer,
      "Origin": "https://www.bilibili.com",
    }
    cookie = (self.settings.get("BILIBILI_COOKIE") or "").strip()
    if not cookie:
      cookie = (getattr(self, "bilibili_cookie", None) or "").strip()
    if cookie:
      headers["Cookie"] = cookie
    return headers

  def parse_search(self, response, page, collected):
    if response.status == 412:
      self.logger.error(
        "触发 B 站风控(412)。请在 settings.py 配置 BILIBILI_COOKIE 或 -s BILIBILI_COOKIE='...'"
      )
      return
    try:
      data = response.json()
    except ValueError:
      self.logger.error("搜索接口返回非 JSON")
      return
    if data.get("code") != 0:
      self.logger.error("搜索失败: %s", data.get("message"))
      return

    for item in data.get("data", {}).get("result") or []:
      if item.get("type") != "video":
        continue
      bvid = item.get("bvid")
      if not bvid:
        continue
      collected.append({
        "bvid": bvid,
        "aid": item.get("aid"),
        "title": self._clean_title(item.get("title") or ""),
        "play": self._parse_play_count(item.get("play") or item.get("view") or 0),
      })

    collected.sort(key=lambda x: x["play"], reverse=True)
    unique, seen = [], set()
    for v in collected:
      if v["bvid"] not in seen:
        seen.add(v["bvid"])
        unique.append(v)
    collected = unique

    if len(collected) < self.max_videos and page < 5:
      yield scrapy.Request(
        f"{SEARCH_URL}?{urlencode(self._search_params(page + 1))}",
        callback=self.parse_search,
        cb_kwargs={"page": page + 1, "collected": collected},
        headers=self._api_headers(),
        errback=self.errback_log,
      )
      return

    top_videos = collected[: self.max_videos]
    if not top_videos:
      self.logger.warning("未搜索到与「%s」相关的视频", self.keyword)
      return

    self.logger.info("已选取播放量最高的 %d 个视频", len(top_videos))
    CrawlProgress.get().set_total_videos(len(top_videos))
    CrawlProgress.get().set_phase("开始抓取视频")
    for video in top_videos:
      yield scrapy.Request(
        f"{VIEW_URL}?bvid={video['bvid']}",
        callback=self.parse_video,
        cb_kwargs={"video_meta": video},
        headers=self._api_headers(self._video_referer(video["bvid"])),
        errback=self.errback_log,
      )

  def parse_video(self, response, video_meta):
    data = response.json()
    if data.get("code") != 0:
      self.logger.error("视频信息失败 %s: %s", video_meta["bvid"], data.get("message"))
      return

    view = data.get("data", {})
    pages = view.get("pages") or [{"cid": view.get("cid"), "duration": view.get("duration", 0)}]
    part_infos = []
    for p in pages:
      cid = p.get("cid")
      if cid:
        part_infos.append({
          "cid": cid,
          "duration": p.get("duration") or view.get("duration") or 0,
        })
    part_infos = part_infos[:MAX_VIDEO_PARTS]
    if not part_infos:
      self.logger.warning("未获取到 cid: %s", video_meta["bvid"])
      return

    item = BilibiliVideoItem(
      bvid=video_meta["bvid"],
      aid=view.get("aid") or video_meta.get("aid"),
      title=view.get("title") or video_meta["title"],
      play=video_meta["play"],
      keyword=self.keyword,
      danmaku_list=[],
      comment_list=[],
    )

    yield scrapy.Request(
      DM_XML_URL.format(cid=part_infos[0]["cid"]),
      callback=self.parse_danmaku_xml,
      cb_kwargs={
        "item": item,
        "part_infos": part_infos,
        "part_index": 0,
        "seg_index": 0,
      },
      headers=self._api_headers(self._video_referer(item["bvid"])),
      errback=self.errback_log,
    )

  def parse_danmaku_xml(self, response, item, part_infos, part_index, seg_index):
    texts = parse_xml_danmaku(response.body)
    existing = list(item.get("danmaku_list") or [])
    existing.extend(texts)
    item["danmaku_list"] = existing

    part = part_infos[part_index]
    duration = part.get("duration") or 0
    total_segs = segment_count(duration)

    # XML 单次最多约 1200 条；长视频用 protobuf 分片补充
    if seg_index == 0 and total_segs > 1:
      yield scrapy.Request(
        f"{DM_SEG_URL}?{urlencode({'type': 1, 'oid': part['cid'], 'segment_index': 1})}",
        callback=self.parse_danmaku_seg,
        cb_kwargs={
          "item": item,
          "part_infos": part_infos,
          "part_index": part_index,
          "seg_index": 1,
          "total_segs": total_segs,
        },
        headers=self._api_headers(self._video_referer(item["bvid"])),
        errback=self.errback_log,
      )
      return

    yield from self._next_danmaku_part(item, part_infos, part_index)

  def parse_danmaku_seg(self, response, item, part_infos, part_index, seg_index, total_segs):
    texts = parse_seg_protobuf(response.body)
    existing = list(item.get("danmaku_list") or [])
    existing.extend(texts)
    item["danmaku_list"] = existing

    next_seg = seg_index + 1
    if next_seg <= total_segs:
      cid = part_infos[part_index]["cid"]
      yield scrapy.Request(
        f"{DM_SEG_URL}?{urlencode({'type': 1, 'oid': cid, 'segment_index': next_seg})}",
        callback=self.parse_danmaku_seg,
        cb_kwargs={
          "item": item,
          "part_infos": part_infos,
          "part_index": part_index,
          "seg_index": next_seg,
          "total_segs": total_segs,
        },
        headers=self._api_headers(self._video_referer(item["bvid"])),
        errback=self.errback_log,
      )
      return

    yield from self._next_danmaku_part(item, part_infos, part_index)

  def _next_danmaku_part(self, item, part_infos, part_index):
    next_part = part_index + 1
    if next_part < len(part_infos):
      cid = part_infos[next_part]["cid"]
      yield scrapy.Request(
        DM_XML_URL.format(cid=cid),
        callback=self.parse_danmaku_xml,
        cb_kwargs={
          "item": item,
          "part_infos": part_infos,
          "part_index": next_part,
          "seg_index": 0,
        },
        headers=self._api_headers(self._video_referer(item["bvid"])),
        errback=self.errback_log,
      )
      return

    self.logger.info("「%s」弹幕共 %d 条", item["title"], len(item.get("danmaku_list") or []))
    yield from self._start_comments(item)

  def _start_comments(self, item):
    aid = item.get("aid")
    if not aid:
      yield item
      return
    params = urlencode({"type": 1, "oid": aid, "mode": 3, "plat": 1, "next": 0})
    yield scrapy.Request(
      f"{REPLY_MAIN_URL}?{params}",
      callback=self.parse_reply_main,
      cb_kwargs={"item": item},
      headers=self._api_headers(self._video_referer(item["bvid"])),
      errback=self.errback_reply_fallback,
    )

  def parse_reply_main(self, response, item):
    try:
      data = response.json()
    except ValueError:
      yield self._reply_legacy_chain(item, pn=1)
      return
    if data.get("code") != 0:
      yield self._reply_legacy_chain(item, pn=1)
      return

    self._append_replies(item, data.get("data", {}).get("replies") or [])
    cur = data.get("data", {}).get("cursor") or {}
    next_cursor = cur.get("next", 0)
    is_end = cur.get("is_end", True)
    comment_count = len(item.get("comment_list") or [])

    if not is_end and next_cursor and comment_count < MAX_COMMENTS:
      params = urlencode({
        "type": 1,
        "oid": item["aid"],
        "mode": 3,
        "plat": 1,
        "next": next_cursor,
      })
      yield scrapy.Request(
        f"{REPLY_MAIN_URL}?{params}",
        callback=self.parse_reply_main,
        cb_kwargs={"item": item},
        headers=self._api_headers(self._video_referer(item["bvid"])),
        errback=self.errback_log,
      )
    else:
      yield from self._finalize_item(item)

  def _reply_legacy_chain(self, item, pn):
    params = urlencode({"type": 1, "oid": item["aid"], "pn": pn})
    return scrapy.Request(
      f"{REPLY_LEGACY_URL}?{params}",
      callback=self.parse_reply_legacy,
      cb_kwargs={"item": item, "pn": pn},
      headers=self._api_headers(self._video_referer(item["bvid"])),
      errback=self.errback_log,
    )

  def parse_reply_legacy(self, response, item, pn):
    try:
      data = response.json()
    except ValueError:
      yield from self._finalize_item(item)
      return
    if data.get("code") != 0:
      yield from self._finalize_item(item)
      return

    self._append_replies(item, data.get("data", {}).get("replies") or [])
    page_info = data.get("data", {}).get("page") or {}
    total = min(page_info.get("count", 1), MAX_COMMENT_PAGES)
    comment_count = len(item.get("comment_list") or [])

    if pn < total and comment_count < MAX_COMMENTS:
      yield self._reply_legacy_chain(item, pn + 1)
    else:
      yield from self._finalize_item(item)

  def errback_reply_fallback(self, failure):
    item = failure.request.cb_kwargs.get("item")
    if item:
      yield self._reply_legacy_chain(item, pn=1)

  def _append_replies(self, item, replies):
    comments = list(item.get("comment_list") or [])
    for r in replies:
      likes = int(r.get("like") or 0)
      msg = (r.get("content") or {}).get("message")
      if msg:
        comments.append({"text": msg.strip(), "likes": likes})
      for sub in r.get("replies") or []:
        sub_likes = int(sub.get("like") or 0)
        sub_msg = (sub.get("content") or {}).get("message")
        if sub_msg:
          comments.append({"text": sub_msg.strip(), "likes": sub_likes})
    comments.sort(key=lambda x: x.get("likes", 0), reverse=True)
    item["comment_list"] = comments

  @staticmethod
  def _dedupe_strings(lines):
    seen, out = set(), []
    for line in lines:
      if line and line not in seen:
        seen.add(line)
        out.append(line)
    return out

  @staticmethod
  def _dedupe_comments(comments):
    seen, out = set(), []
    for entry in comments:
      if isinstance(entry, dict):
        text = (entry.get("text") or "").strip()
        likes = int(entry.get("likes") or 0)
        key = (text, likes)
        if text and key not in seen:
          seen.add(key)
          out.append({"text": text, "likes": likes})
      elif entry:
        text = str(entry).strip()
        if text and text not in seen:
          seen.add(text)
          out.append({"text": text, "likes": 0})
    out.sort(key=lambda x: x.get("likes", 0), reverse=True)
    return out

  def _finalize_item(self, item):
    item["danmaku_list"] = self._dedupe_strings(item.get("danmaku_list") or [])
    item["comment_list"] = self._dedupe_comments(item.get("comment_list") or [])
    self.logger.info(
      "「%s」完成：弹幕 %d 条，评论 %d 条",
      item["title"],
      len(item["danmaku_list"]),
      len(item["comment_list"]),
    )
    yield item

  def errback_log(self, failure):
    self.logger.error("请求失败: %s — %s", failure.request.url, failure.value)

  @staticmethod
  def _parse_play_count(value):
    if isinstance(value, (int, float)):
      return int(value)
    s = str(value).strip().replace(",", "")
    if s.endswith("万"):
      return int(float(s[:-1]) * 10000)
    if s.endswith("亿"):
      return int(float(s[:-1]) * 100000000)
    try:
      return int(float(s))
    except ValueError:
      return 0

  @staticmethod
  def _clean_title(title):
    return re.sub(r"<[^>]+>", "", title)
