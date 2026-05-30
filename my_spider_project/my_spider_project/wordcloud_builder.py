"""
词云构建：以热点评论为主体，弹幕高频词作为辅助筛选/加权。
"""
import math
import re
from collections import Counter

import jieba
import jieba.analyse

STOPWORDS = {
  "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
  "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
  "自己", "这", "那", "吗", "吧", "啊", "呢", "哈", "嗯", "哦", "呀", "么", "什么",
  "怎么", "这个", "那个", "还是", "可以", "就是", "真的", "感觉", "知道", "觉得",
  "视频", "弹幕", "评论", "bilibili", "哔哩哔哩", "www", "http", "https",
  "前方", "高能", "预警", "打卡", "签到", "来了", "第一", "路过",
}

_EN_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9_+#.\-]{1,}")


def _tokenize(text: str) -> list[str]:
  tokens = []
  for word in jieba.cut(text):
    word = word.strip()
    if word:
      tokens.append(word)
  for m in _EN_TOKEN.finditer(text):
    tokens.append(m.group())
  return tokens


def _is_valid_token(word: str) -> bool:
  if len(word) < 2 and not _EN_TOKEN.fullmatch(word):
    return False
  if word in STOPWORDS:
    return False
  if re.fullmatch(r"[\W\d_]+", word):
    return False
  return True


def _normalize_comment(entry) -> tuple[str, int]:
  if isinstance(entry, dict):
    return entry.get("text") or "", int(entry.get("likes") or 0)
  return str(entry), 0


def _extract_danmaku_hot_terms(danmaku: list[str], top_k: int = 120) -> set[str]:
  """从弹幕中提取高频热点词，用于辅助筛选评论主题。"""
  counter: Counter[str] = Counter()
  for text in danmaku:
    for token in _tokenize(text):
      if _is_valid_token(token):
        counter[token] += 1
  return {w for w, _ in counter.most_common(top_k)}


def _danmaku_match(token: str, dm_hot: set[str]) -> bool:
  if token in dm_hot:
    return True
  t_lower = token.lower()
  for d in dm_hot:
    if len(d) < 2:
      continue
    if d in token or token in d:
      return True
    if t_lower == d.lower():
      return True
  return False


def build_hot_comment_word_frequencies(
  comments: list,
  danmaku: list[str],
  keyword: str,
  title: str = "",
  *,
  max_words: int = 150,
  min_words: int = 25,
) -> dict[str, float]:
  """
  词云词频策略：
  1. 主体 = 评论（按点赞加权 + TF-IDF）
  2. 弹幕 = 辅助：提取弹幕热点词，对评论中出现的同主题词加权
  3. 仅输出在评论语料中出现的词（弹幕不直接进入词云）
  """
  keyword = (keyword or "").strip()
  dm_hot = _extract_danmaku_hot_terms(danmaku)

  parsed = [_normalize_comment(c) for c in comments]
  parsed = [(t, lk) for t, lk in parsed if t.strip()]
  if not parsed and not danmaku:
    return {}

  jieba.add_word(keyword, freq=20000)
  for w in _tokenize(title):
    if len(w) >= 2:
      jieba.add_word(w, freq=10000)

  merged: Counter[str] = Counter()
  comment_texts = [t for t, _ in parsed]
  comment_token_set: set[str] = set()

  # --- 主体：热点评论（点赞加权）---
  for text, likes in parsed:
    like_weight = math.log1p(likes) * 15 + 1
    for token in _tokenize(text):
      if not _is_valid_token(token):
        continue
      comment_token_set.add(token)
      score = like_weight
      if _danmaku_match(token, dm_hot):
        score *= 2.2
      merged[token] += score

  # --- TF-IDF 仅对评论语料 ---
  if comment_texts:
    corpus = "\n".join(comment_texts)
    for word, weight in jieba.analyse.extract_tags(
      corpus, topK=max_words * 2, withWeight=True
    ):
      if _is_valid_token(word) and word in comment_token_set:
        score = weight * 300
        if _danmaku_match(word, dm_hot):
          score *= 1.8
        merged[word] += score

  # 只保留评论中出现的词（弹幕仅作筛选器）
  merged = Counter({w: c for w, c in merged.items() if w in comment_token_set})

  if not merged and comment_texts:
    for text, likes in parsed:
      like_weight = math.log1p(likes) * 10 + 1
      for token in _tokenize(text):
        if _is_valid_token(token):
          merged[token] += like_weight

  if not merged:
    return {}

  if keyword:
    merged[keyword] += 400
    kw_lower = keyword.lower()
    for word in list(merged):
      if word.lower() == kw_lower:
        merged[word] += 200

  for word in _tokenize(title):
    if _is_valid_token(word) and word in comment_token_set:
      merged[word] += 80

  ranked = merged.most_common(max_words * 2)
  result = {w: float(c) for w, c in ranked[:max_words]}

  if len(result) < min_words:
    for w, c in ranked[max_words : max_words * 2]:
      result[w] = float(c)
      if len(result) >= min_words:
        break

  if keyword and keyword not in result:
    result[keyword] = 400.0

  return dict(sorted(result.items(), key=lambda x: x[1], reverse=True)[:max_words])
