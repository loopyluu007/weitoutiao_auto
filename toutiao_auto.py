import sys
import io
# 设置标准输出和错误输出的编码为 UTF-8，解决 Windows 环境下的中文编码问题
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import os
import time
import requests
import traceback
from pathlib import Path
from datetime import datetime

# 尝试加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 如果没有安装 python-dotenv，忽略

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ================== 配置区域 ==================

PUBLISH_URL = "https://mp.toutiao.com/profile_v4/weitoutiao/publish"
LIST_URL = "https://mp.toutiao.com/profile_v4/weitoutiao"

COOKIE_FILE = "toutiao_cookies.json"
LAST_PUBLISHED_FILE = "last_published_id.txt"

# 新闻 API 配置（从环境变量读取）
NEWS_API_URL = os.getenv("NEWS_API_URL", "")
NEWS_API_PARAMS_JSON = os.getenv("NEWS_API_PARAMS", "{}")
try:
    NEWS_PARAMS = json.loads(NEWS_API_PARAMS_JSON) if NEWS_API_PARAMS_JSON else {}
except json.JSONDecodeError:
    NEWS_PARAMS = {}

HEADLESS = False  # 保持非 headless 模式，避免被封禁风险
FETCH_INTERVAL_SEC = 60          
WAIT_SEC = 25     

# ================== 工具函数 ==================

def log(step: str, msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{step}] {msg}", flush=True)

def err(step: str, msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR:{step}] {msg}", flush=True)

# ================== Cookie 管理 ==================

def load_cookies(driver) -> bool:
    """注入本地 Cookie 并验证有效性"""
    if not Path(COOKIE_FILE).exists():
        return False

    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        
        # 必须先访问域名才能注入 Cookie
        driver.get("https://mp.toutiao.com")
        time.sleep(2)
        
        for c in cookies:
            try:
                driver.add_cookie(c)
            except:
                pass
        
        log("cookie", "已注入本地 Cookie，尝试刷新验证...")
        driver.refresh()
        time.sleep(3)

        # 验证是否进入了登录后的页面（通过判断是否存在发布按钮或特定 ID）
        # 如果依然停留在登录页，说明 Cookie 失效
        if "login" in driver.current_url.lower():
            log("cookie", "Cookie 已失效，需要重新登录")
            return False
            
        log("cookie", "Cookie 验证成功，继续复用")
        return True
    except Exception as e:
        err("cookie", f"加载 Cookie 出错: {repr(e)}")
        return False

def save_cookies(driver):
    cookies = driver.get_cookies()
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    log("cookie", "Cookie 已保存到本地")

# ================== API 获取逻辑 ==================

def get_latest_news_list(limit: int = 10) -> list[dict]:
    """从配置的 API 获取最新新闻列表（支持批量获取，避免丢失新闻）
    
    Args:
        limit: 获取新闻数量上限（默认10条，根据实际情况：10分钟内最多十几条）
    
    Returns:
        有中文内容的新闻列表，按时间倒序排列
    """
    if not NEWS_API_URL:
        err("api", "未配置 NEWS_API_URL 环境变量")
        return []
    
    # 临时修改 limit 参数，获取多条新闻
    params = NEWS_PARAMS.copy()
    params["limit"] = limit
    
    # 调试日志：输出配置信息
    log("api", f"API URL: {NEWS_API_URL}")
    log("api", f"API 参数: {params}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        resp = requests.get(NEWS_API_URL, params=params, headers=headers, timeout=20, verify=True)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        
        if items:
            log("api", f"获取到 {len(items)} 条新闻")
            # 检查每条新闻是否有中文内容，过滤出有效的新闻
            valid_items = []
            for news in items:
                has_zh = news.get("content_multilingual", {}).get("zh") if isinstance(news.get("content_multilingual"), dict) else None
                if has_zh and has_zh.get("title") and has_zh.get("summary"):
                    log("api", f"找到中文内容: {has_zh.get('title', '')[:50]}...")
                    valid_items.append(news)
                else:
                    log("api", f"跳过无中文内容的新闻: {news.get('id', 'unknown')}")
            
            if valid_items:
                log("api", f"有效新闻数量: {len(valid_items)}")
            else:
                log("api", "警告：所有新闻都没有中文内容")
            
            return valid_items
        else:
            log("api", "API 返回的 items 为空")
            return []
    except Exception as e:
        err("api", f"获取新闻失败: {repr(e)}")
        import traceback
        err("api", traceback.format_exc())
        return []

def get_latest_news() -> dict | None:
    """从配置的 API 获取最新新闻（兼容旧接口，返回单条）"""
    items = get_latest_news_list(limit=1)
    return items[0] if items else None

# ================== 发布逻辑 ==================

def extract_content_from_summary(summary) -> str:
    if isinstance(summary, list):
        return "\n\n".join(str(x).strip() for x in summary if x).strip()
    return str(summary or "").strip()

def publish_micro(driver, news: dict):
    content_id = news.get("id")
    
    # 优先使用中文内容（content_multilingual.zh）
    content_multilingual = news.get("content_multilingual", {})
    zh_content = content_multilingual.get("zh") if isinstance(content_multilingual, dict) else None
    
    if zh_content and zh_content.get("title") and zh_content.get("summary"):
        # 使用中文内容
        title = zh_content.get("title", "")
        content = extract_content_from_summary(zh_content.get("summary"))
        log("publish", "使用中文内容")
    else:
        # 回退到英文内容
        title = news.get("smart_title", "")
        content = extract_content_from_summary(news.get("summary"))
        log("publish", "使用英文内容（未找到中文内容）")
    
    final_text = f"【{title}】\n\n{content}\n\n#美股# #财经#"
    
    log("publish", f"正在发布 ID: {content_id}")
    driver.get(PUBLISH_URL)
    wait = WebDriverWait(driver, WAIT_SEC)
    
    try:
        # 等待页面完全加载
        time.sleep(2)
        
        # 等待编辑器出现
        editor = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="root"]//p')))
        # 确保编辑器可见且可交互
        wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="root"]//p')))
        
        # 清空编辑器并输入内容
        editor.clear()
        editor.send_keys(final_text)
        
        # 等待内容输入完成，可能有验证逻辑
        time.sleep(2)
        
        # 尝试关闭可能的弹窗或提示（如果有）
        try:
            close_elements = driver.find_elements(By.XPATH, "//*[contains(@class, 'close') or contains(@aria-label, '关闭') or contains(@class, 'modal-close')]")
            for elem in close_elements[:3]:  # 只尝试前3个，避免过多尝试
                try:
                    if elem.is_displayed():
                        elem.click()
                        time.sleep(0.5)
                except:
                    pass
        except:
            pass
        
        # 等待发布按钮可点击，并滚动到可见位置
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="root"]//button[contains(., "发布")]')))
        
        # 滚动到按钮位置，确保在视口中
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'auto'});", btn)
        time.sleep(1)  # 等待滚动完成
        
        # 再次检查按钮是否可点击
        btn = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="root"]//button[contains(., "发布")]')))
        
        # 尝试多种点击方式
        try:
            # 方法1: 普通点击
            btn.click()
            log("publish", "使用普通点击方式")
        except Exception as click_error:
            log("publish", f"普通点击失败: {type(click_error).__name__}，尝试 JavaScript 点击")
            try:
                # 方法2: JavaScript 点击（绕过遮挡）
                driver.execute_script("arguments[0].click();", btn)
                log("publish", "使用 JavaScript 点击方式")
            except Exception as js_error:
                err("publish", f"JavaScript 点击也失败: {repr(js_error)}")
                raise
        
        log("publish", "已点击发布按钮，等待发布成功跳转...")
        
        # 等待 URL 跳转到列表页，表示发布成功
        wait.until(EC.url_to_be(LIST_URL))
        log("publish", "发布成功，已跳转到列表页")
        time.sleep(3) # 跳转后短暂等待页面加载
        return True
    except Exception as e:
        err("publish", f"发布过程出错: {repr(e)}")
        # 在 CI 环境中，尝试保存截图以便调试（如果配置了截图功能）
        if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
            try:
                screenshot_path = f"error_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                driver.save_screenshot(screenshot_path)
                log("publish", f"错误截图已保存: {screenshot_path}")
            except:
                pass
        return False

# ================== 主逻辑 ==================

def main():
    log("boot", "程序启动...")
    last_file = Path(LAST_PUBLISHED_FILE)
    last_id = last_file.read_text().strip() if last_file.exists() else ""

    chrome_options = Options()
    # 保持非 headless 模式，避免被封禁风险
    
    # 设置窗口大小，确保元素可见（解决窗口尺寸问题）
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--start-maximized")
    
    # CI 环境的额外优化（保持非 headless 模式）
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        # 注意：在 Windows CI 环境中，非 headless 模式也能正常运行
    
    driver = webdriver.Chrome(options=chrome_options)
    # 显式设置窗口大小，确保元素可见
    try:
        driver.set_window_size(1920, 1080)
    except:
        # 如果设置失败，尝试最大化窗口
        try:
            driver.maximize_window()
        except:
            pass

    try:
        # 1. Cookie 优先复用逻辑
        if not load_cookies(driver):
            log("login", "未检测到有效 Cookie，请在弹出的浏览器中完成登录...")
            driver.get("https://mp.toutiao.com")
            # 循环检查直到用户登录成功（URL 不再包含 login）
            while "login" in driver.current_url.lower():
                time.sleep(2)
            save_cookies(driver)
            log("login", "登录成功，Cookie 已记录")

        # 2. 轮询主循环（支持批量处理，避免丢失新闻）
        # 根据实际情况：10分钟内最多十几条，所以每次获取10条足够覆盖
        while True:
            # 获取多条新闻（最多10条），避免在发布过程中丢失新新闻
            news_list = get_latest_news_list(limit=10)
            
            if news_list:
                published_count = 0
                for news in news_list:
                    c_id = news.get("id")
                    if c_id != last_id:
                        log("main", f"检测到新内容: {c_id}")
                        if publish_micro(driver, news):
                            last_id = c_id
                            last_file.write_text(c_id)
                            published_count += 1
                            log("main", f"发布成功，已更新本地 ID（本次已发布 {published_count} 条）")
                        else:
                            log("main", f"发布失败，停止处理后续新闻，等待下次轮询")
                            break  # 如果发布失败，停止处理后续新闻，等待下次轮询
                    else:
                        # 已发布过，跳过
                        log("main", f"新闻 {c_id} 已发布过，跳过")
                
                if published_count == 0:
                    # 视觉反馈：显示当前时间，证明程序没死
                    print(f"\r[{datetime.now().strftime('%H:%M:%S')}] 暂无新内容，等待中...", end="", flush=True)
            else:
                # 视觉反馈：显示当前时间，证明程序没死
                print(f"\r[{datetime.now().strftime('%H:%M:%S')}] 暂无新内容，等待中...", end="", flush=True)
            
            # 倒计时等待，允许 Ctrl+C 退出
            for i in range(FETCH_INTERVAL_SEC, 0, -1):
                time.sleep(1)
                
    except KeyboardInterrupt:
        log("exit", "用户手动停止程序")
    except Exception as e:
        err("fatal", traceback.format_exc())
    finally:
        driver.quit()

if __name__ == "__main__":
    main()