"""交互式启动 B 站爬虫：登录 → 输入关键字 → 抓取并生成词云。"""
import os
import subprocess
import sys


def main():
  project_dir = os.path.dirname(os.path.abspath(__file__))
  package_dir = os.path.join(project_dir, "my_spider_project")

  sys.path.insert(0, project_dir)
  from my_spider_project.bilibili_auth import cookies_to_header, ensure_login

  force = "--relogin" in sys.argv
  print("=== B 站爬虫 · 登录 ===", flush=True)
  cookies = ensure_login(package_dir, force=force)
  cookie_header = cookies_to_header(cookies)

  print("\n>>> 请输入搜索关键字（输入后按回车）: ", end="", flush=True)
  keyword = input().strip()
  if not keyword:
    print("关键字不能为空", flush=True)
    sys.exit(1)

  cmd = [
    sys.executable, "-m", "scrapy", "crawl", "bilibili",
    "-a", f"keyword={keyword}",
    "-s", "BILIBILI_SKIP_AUTH_CHECK=true",
  ]
  if force:
    cmd.extend(["-s", "BILIBILI_FORCE_LOGIN=true"])

  # Cookie 通过环境变量传递，避免命令行特殊字符问题
  env = os.environ.copy()
  env["BILIBILI_COOKIE"] = cookie_header

  print(f"\n=== 开始抓取关键字「{keyword}」===\n", flush=True)
  result = subprocess.run(cmd, cwd=project_dir, env=env)
  sys.exit(result.returncode)


if __name__ == "__main__":
  main()
