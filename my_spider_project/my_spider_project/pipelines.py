import os

from itemadapter import ItemAdapter
from wordcloud import WordCloud

from my_spider_project.progress_tracker import CrawlProgress
from my_spider_project.utils import find_chinese_font, get_video_output_dir, sanitize_filename
from my_spider_project.wordcloud_builder import build_hot_comment_word_frequencies


class BilibiliPipeline:
  @classmethod
  def from_crawler(cls, crawler):
    pipe = cls()
    pipe.crawler = crawler
    return pipe

  def open_spider(self):
    spider = self.crawler.spider
    if spider.name != "bilibili":
      return
    self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    self.font_path = find_chinese_font()
    if not self.font_path:
      spider.logger.warning("未找到中文字体，词云可能无法正常显示中文")

  def process_item(self, item):
    spider = self.crawler.spider
    if spider.name != "bilibili":
      return item

    adapter = ItemAdapter(item)
    title = adapter.get("title") or "未命名"
    keyword = adapter.get("keyword") or ""
    danmaku = adapter.get("danmaku_list") or []
    comments = adapter.get("comment_list") or []
    progress = CrawlProgress.get()

    progress.set_phase(f"保存数据: {title[:25]}")
    video_dir = get_video_output_dir(self.base_dir, title)
    self._save_txt(video_dir, "弹幕.txt", danmaku)
    self._save_txt(video_dir, "评论.txt", self._comment_lines(comments))

    progress.set_phase(f"生成词云: {title[:25]}")
    self._generate_wordcloud(comments, danmaku, title, keyword, video_dir, spider)
    progress.complete_video(title)
    return item

  @staticmethod
  def _comment_lines(comments: list) -> list[str]:
    lines = []
    for entry in comments:
      if isinstance(entry, dict):
        text = (entry.get("text") or "").strip()
        likes = int(entry.get("likes") or 0)
        if text:
          lines.append(f"[{likes}赞] {text}" if likes else text)
      elif entry:
        lines.append(str(entry).strip())
    return lines

  @staticmethod
  def _save_txt(directory: str, filename: str, lines: list[str]) -> None:
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
      f.write("\n".join(lines) if lines else "")

  def _generate_wordcloud(
    self,
    comments: list,
    danmaku: list[str],
    title: str,
    keyword: str,
    video_dir: str,
    spider,
  ) -> None:
    safe_title = sanitize_filename(title)
    out_path = os.path.join(video_dir, f"{safe_title}.png")

    if not comments and not danmaku:
      spider.logger.warning("「%s」弹幕与评论均为空，跳过词云", title)
      return

    word_freq = build_hot_comment_word_frequencies(
      comments, danmaku, keyword, title=title
    )
    if len(word_freq) < 5:
      spider.logger.warning(
        "「%s」有效词条过少(%d)，请确认已登录且评论抓取成功",
        title,
        len(word_freq),
      )
      if not word_freq:
        return

    wc_kwargs = {
      "width": 1200,
      "height": 800,
      "background_color": "white",
      "max_words": 150,
      "collocations": False,
      "prefer_horizontal": 0.85,
    }
    if self.font_path:
      wc_kwargs["font_path"] = self.font_path

    wc = WordCloud(**wc_kwargs)
    wc.generate_from_frequencies(word_freq)
    wc.to_file(out_path)
    spider.logger.info(
      "词云已保存: %s（%d 词，评论 %d 条，弹幕 %d 条）",
      out_path,
      len(word_freq),
      len(comments),
      len(danmaku),
    )


class MySpiderProjectPipeline:
  def process_item(self, item, spider):
    return item
