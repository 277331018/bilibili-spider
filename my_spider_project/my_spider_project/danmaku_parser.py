"""B 站弹幕解析：XML（主）+ protobuf 分片（补充）。"""
import gzip
import math
import re
from xml.etree import ElementTree

# protobuf 分片中较可靠的 UTF-8 弹幕文本
_UTF8_TEXT = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_+#.\-]{2,80}")


def decompress_body(body: bytes) -> bytes:
  if body and body[:2] == b"\x1f\x8b":
    try:
      return gzip.decompress(body)
    except OSError:
      pass
  return body or b""


def parse_xml_danmaku(body: bytes) -> list[str]:
  raw = decompress_body(body)
  if not raw.strip().startswith(b"<"):
    return []
  texts = []
  try:
    root = ElementTree.fromstring(raw)
    for node in root.iter("d"):
      if node.text:
        t = node.text.strip()
        if t:
          texts.append(t)
  except ElementTree.ParseError:
    pass
  return texts


def parse_seg_protobuf(body: bytes) -> list[str]:
  """从 seg.so 二进制响应中提取弹幕文本（启发式，用于 XML 不可用或需分片时）。"""
  raw = decompress_body(body)
  if not raw:
    return []
  texts = []
  seen = set()
  for m in _UTF8_TEXT.finditer(raw.decode("utf-8", errors="ignore")):
    t = m.group().strip()
    if len(t) < 2 or t.isdigit():
      continue
    if t in seen:
      continue
    seen.add(t)
    texts.append(t)
  return texts


def segment_count(duration_sec: int) -> int:
  """B 站每 6 分钟一个弹幕分片。"""
  if duration_sec <= 0:
    return 1
  return max(1, math.ceil(duration_sec / 360))
