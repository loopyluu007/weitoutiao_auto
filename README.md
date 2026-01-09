# 微头条自动发布工具

自动从配置的新闻 API 获取内容并发布到今日头条微头条。

## 功能特性

- ✅ 自动获取新闻内容（支持自定义 API）
- ✅ 自动登录并保存 Cookie，减少重复登录
- ✅ 智能去重，避免重复发布相同内容
- ✅ 定时轮询，自动检测新内容
- ✅ 环境变量配置，灵活适配不同数据源

## 环境要求

- Python 3.7+
- Chrome 浏览器
- ChromeDriver（需与 Chrome 版本匹配）

## 安装步骤

1. 克隆或下载本项目

2. 安装依赖：
```bash
pip install selenium requests python-dotenv
```

3. 安装 ChromeDriver：
   - 访问 [ChromeDriver 下载页面](https://chromedriver.chromium.org/)
   - 下载与你的 Chrome 版本匹配的驱动
   - 将 `chromedriver` 添加到系统 PATH，或放在项目目录下

## 配置说明

1. **配置新闻 API**

   复制 `.env.example` 为 `.env`，并填入你的配置：
   ```bash
   cp .env.example .env
   ```

   编辑 `.env` 文件：
   ```env
   NEWS_API_URL=https://your-news-api.com/api/endpoint
   NEWS_API_PARAMS={"range": "24h", "limit": 1}
   ```

   **注意**：API 返回的 JSON 格式需要包含以下字段：
   - `items`: 数组，包含新闻列表
   - 每个 item 需要包含：`id`、`smart_title`、`summary`

2. **（可选）配置其他参数**

   编辑 `toutiao_auto.py` 中的配置：
   ```python
   HEADLESS = False          # 是否无头模式运行
   FETCH_INTERVAL_SEC = 60   # 轮询间隔（秒）
   WAIT_SEC = 25             # 页面等待超时（秒）
   ```

## 使用方法

1. **首次运行**

   运行脚本，会自动打开浏览器：
   ```bash
   python toutiao_auto.py
   ```

2. **完成登录**

   在打开的浏览器中完成今日头条登录，脚本会自动保存 Cookie 到 `toutiao_cookies.json`。

3. **自动运行**

   登录成功后，脚本会：
   - 每 60 秒检查一次新内容
   - 检测到新内容时自动发布
   - 显示发布状态和日志

4. **停止程序**

   按 `Ctrl+C` 优雅退出

## 文件说明

- `toutiao_auto.py` - 主程序文件
- `.env` - 环境变量配置（需自行创建，包含 API 配置）
- `.env.example` - 配置模板
- `toutiao_cookies.json` - Cookie 文件（首次登录后自动生成）
- `toutiao_cookies.json.example` - Cookie 格式示例
- `last_published_id.txt` - 记录最后发布的内容 ID（用于去重）

## 注意事项

⚠️ **重要提示**：

1. **Cookie 安全**：`toutiao_cookies.json` 包含登录凭证，请勿泄露或提交到 Git
2. **API 配置**：确保你的 API 返回格式符合要求（包含 `items` 数组和相关字段）
3. **发布频率**：请遵守平台规则，避免发布过于频繁
4. **内容审核**：发布的内容需符合平台规范

## 常见问题

**Q: 如何更换数据源？**  
A: 修改 `.env` 文件中的 `NEWS_API_URL` 和 `NEWS_API_PARAMS` 即可。

**Q: Cookie 失效怎么办？**  
A: 删除 `toutiao_cookies.json` 文件，重新运行脚本并登录。

**Q: 如何修改发布内容格式？**  
A: 编辑 `toutiao_auto.py` 中的 `publish_micro()` 函数（约第 126 行），修改 `final_text` 的格式和标签。

## License

MIT
