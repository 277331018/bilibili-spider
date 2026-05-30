import scrapy


class ExampleSpider(scrapy.Spider):
    name = "example"
    allowed_domains = ["bilibili.com"]
    start_urls = ["https://www.bilibili.com"]

    def parse(self, response):
        list_list= response.xpath("//div[@class='channel-items__left']//a")
        ll = []
        for item in list_list:
            ll.append(item.xpath("./text()").extract()[0])
        yield ll

    # def parse(self, response):
    #     # 使用更通用的选择器，比如找所有的导航链接
    #     links = response.xpath("//div[@class='channel-items__left']//a")
    #     for item in links:
    #         ll = {}
    #         ll['title'] = item.xpath("./text()").get()  # 推荐使用 .get() 替代 extract_first()
    #         yield ll  # <--- 修正：在循环内部，每提取一个就输出一个