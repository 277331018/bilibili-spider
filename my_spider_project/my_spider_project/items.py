import scrapy


class BilibiliVideoItem(scrapy.Item):
  bvid = scrapy.Field()
  aid = scrapy.Field()
  title = scrapy.Field()
  play = scrapy.Field()
  keyword = scrapy.Field()
  danmaku_list = scrapy.Field()
  comment_list = scrapy.Field()
