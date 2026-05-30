# Bilibili 热点词云爬虫

基于 Scrapy 的 B 站视频弹幕/评论爬虫，支持扫码登录，自动生成热点词云图。

## 功能特性

- **扫码登录** — 自动生成二维码，B站 App 扫码即可登录，Cookie 本地持久化，自动校验有效期
- **智能搜索** — 按关键词搜索，自动选取播放量最高的 Top 10 视频
- **弹幕抓取** — XML 主接口 + Protobuf 分片补充（长视频按每 6 分钟分段），支持多分P视频
- **评论抓取** — 新 API 游标分页优先，失败自动回退旧 API，单视频最多 10000 条评论
- **词云生成** — 评论为主体（点赞加权 + TF-IDF），弹幕热点辅助筛选，jieba 中文分词，1200×800 PNG 输出
- **进度条** — tqdm 实时显示抓取进度和当前阶段
- **反反爬** — 合理的请求延迟、完整的 Referer/Origin 头、避免 brotli 编码

## 快速开始

### 环境要求

- Python 3.10+
- Windows / Linux / macOS

### 安装

```bash
cd my_spider_project
pip install -r requirements.txt
```

### 运行

**方式一：交互式启动（推荐）**

```bash
python run_bilibili.py
```

脚本会自动处理登录、提示输入关键词，然后启动爬虫。

首次运行会弹出二维码图片，用 B站 App 扫码登录，之后 Cookie 会自动保存，无需重复登录。

**方式二：命令行直接启动**

```bash
# 先用 run_bilibili.py 登录一次（会在项目目录生成 .bilibili_cookies.json）
python run_bilibili.py --relogin

# 之后可以直接用 Scrapy 命令
scrapy crawl bilibili -a keyword=Python
```

### 输出文件

```
热点词云图/
├── Python零基础入门教程/
│   ├── 弹幕.txt          # 爬取到的所有弹幕
│   ├── 评论.txt          # 爬取到的所有评论（含点赞数）
│   └── Python零基础入门教程.png  # 热点词云图
├── ChatGPT使用技巧/
│   ├── 弹幕.txt
│   ├── 评论.txt
│   └── ChatGPT使用技巧.png
└── ...
```

## 项目架构

```
my_spider_project/
├── run_bilibili.py                  # 交互式启动脚本
├── scrapy.cfg                       # Scrapy 部署配置
├── requirements.txt                 # 依赖列表
├── my_spider_project/
│   ├── settings.py                  # Scrapy 全局配置
│   ├── items.py                     # 数据模型 BilibiliVideoItem
│   ├── pipelines.py                 # 数据处理管道（保存 txt + 生成词云）
│   ├── middlewares.py               # Cookie 自动注入中间件
│   ├── extensions.py                # 登录扩展 + 进度条扩展
│   ├── bilibili_auth.py             # B站扫码登录与 Cookie 持久化
│   ├── progress_tracker.py          # tqdm 进度条（线程安全单例）
│   ├── danmaku_parser.py            # 弹幕 XML/Protobuf 解析器
│   ├── wordcloud_builder.py         # 词频构建 + 中文分词 + 加权策略
│   ├── utils.py                     # 文件名清洗、字体查找、目录管理
│   └── spiders/
│       ├── bilibili.py              # 核心爬虫（搜索 → 弹幕 → 评论）
│       └── example.py               # 示例爬虫
├── 热点词云图/                       # 词云输出目录
└── 清洗数据/                         # 历史抓取数据（JSON）
```

## 数据流

```
用户输入关键词
    │
    ▼
扫码登录 (bilibili_auth.py) ──► Cookie 持久化 (.bilibili_cookies.json)
    │
    ▼
LoginExtension ──► 注入 Cookie 到 Spider
    │
    ▼
Spider 搜索 API ──► 按播放量排序 ──► 取 Top 10 视频
    │
    ▼
逐个视频抓取:
  ├── 弹幕: comment.bilibili.com/{cid}.xml (XML 主接口)
  │         └── 长视频补充: seg.so (Protobuf 分片, 每 6 分钟一段)
  └── 评论: /x/v2/reply/main (新 API, 游标分页)
            └── 失败回退: /x/v2/reply (旧 API, 页码分页)
    │
    ▼
CookieMiddleware ──► 所有请求自动携带 Cookie
    │
    ▼
Pipeline 处理:
  ├── 去重
  ├── 保存 弹幕.txt / 评论.txt
  └── 词云生成:
        ├── jieba 分词 + 停用词过滤
        ├── 评论: 点赞加权 + TF-IDF
        ├── 弹幕: 提取热点词 → 对评论同主题词乘 2.2x
        ├── 关键词/标题: 额外固定加权
        └── wordcloud 生成 1200×800 PNG
```

## 词云加权策略

词云以**评论**为主体语料，**弹幕**仅作为热点方向辅助加权，弹幕文字本身不直接进入词云。

| 权重来源 | 权重值 | 说明 |
|---|---|---|
| 评论点赞加权 | `ln(likes+1) × 15 + 1` | 高赞评论的词获得更高权重 |
| 弹幕热点匹配 | `×2.2` | 评论中与弹幕高频词一致的词再乘 2.2 |
| TF-IDF | `weight × 300` | 对评论语料整体做关键词提取 |
| TF-IDF + 弹幕匹配 | `×1.8` | TF-IDF 词命中弹幕热点的额外加权 |
| 搜索关键词 | `+400` | 确保搜索主题词出现在词云中 |
| 标题词 | `+80` | 标题分词后命中的词加权 |

## 配置说明

`settings.py` 主要配置项：

| 配置 | 默认值 | 说明 |
|---|---|---|
| `BILIBILI_COOKIE` | `""` | 手动设置 Cookie 字符串 |
| `BILIBILI_FORCE_LOGIN` | `False` | 设为 True 强制重新扫码登录 |
| `DOWNLOAD_DELAY` | `1` | 全局下载延迟（爬虫内覆写为 0.6s） |
| `CONCURRENT_REQUESTS_PER_DOMAIN` | `1` | 全局并发（爬虫内覆写为 2） |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `ROBOTSTXT_OBEY` | `False` | 不遵守 robots.txt |

## 依赖

| 包 | 用途 |
|---|---|
| `scrapy>=2.11` | 爬虫框架 |
| `jieba>=0.42` | 中文分词 |
| `wordcloud>=1.9` | 词云生成 |
| `matplotlib>=3.8` | 可视化（wordcloud 依赖） |
| `tqdm>=4.66` | 进度条 |
| `qrcode[pil]>=7.4` | 登录二维码生成 |
| `requests>=2.31` | HTTP 客户端（登录模块） |
| `itemadapter>=0.8` | Item 抽象层 |

## 注意事项

- 首次使用需要扫码登录，Cookie 保存在项目目录的 `.bilibili_cookies.json`，请勿泄露
- 如遇 412 风控错误，请确保已完成登录
- 词云需要中文字体，Windows 下自动使用微软雅黑/黑体/宋体，Linux 需安装文泉驿或 Noto 字体
- 弹幕 XML 单次最多约 1200 条，长视频通过 Protobuf 分片补充
- 建议保持合理的 DOWNLOAD_DELAY，避免对 B 站服务器造成压力
