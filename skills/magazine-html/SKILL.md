---
name: magazine-html
description: |
  把 EPUB 电子书转成单文件、可离线打开的杂志风格 HTML 阅读器：按 spine 抽取全部正文、
  图片转 data URI 内嵌、跨文件链接改页内锚点、套上工具栏/目录抽屉/主题切换/字号行距/
  图片灯箱/打印样式的阅读器外壳，并附一套 headless Chrome 自动化验收脚本。
  Use this skill when the user says "做成 html 看"、"转成网页版"、"给 epub 做个阅读器"、
  "html 观感更好"、"在电脑上读这本电子书"、"把电子书做成单文件网页"，
  或需要在浏览器里输出带插画、目录、主题切换的电子书页面。不适用于 EPUB→PDF/MOBI 转换、
  站点前端开发，或不需要阅读器外壳的纯正文抽取。
---

# Magazine HTML

把一本 EPUB 变成一个 HTML 文件：双击就能在浏览器里读，离线可用，不依赖任何外链。

## Inputs to collect

- **源 EPUB**：`.epub` 文件。是否已做过杂志版重排决定正文样式来源（书里自带 `stylesheet.css` 就用它，否则套本 skill 的默认杂志样式）
- **要不要阅读器外壳**：默认要（工具栏/目录/主题）；只要纯正文 HTML 用 `--no-shell`
- **额外样式**（可选）：`--css` 追加在书籍样式之后，用于微调

源文件如果是解压后的目录，先打包成 epub 再喂进来（`zip` 的 mimetype 要首条且不压缩）。

## Procedure

记 `SKILL_DIR` = 本 skill 所在目录（装了 skills 的地方，例如 `~/.agents/skills/magazine-html`）。
下面的命令里 `scripts/` 和 `references/` 都是相对 **SKILL_DIR** 的，**不在 skill 目录里执行会找不到文件**。

### 1. 转

```bash
python3 <SKILL_DIR>/scripts/epub_to_html.py book.epub -o out.html
# 只出正文、不要外壳： --no-shell
```

脚本做四件事：按 spine 顺序取每篇 body → 跨文件链接改页内锚点 → 图片转 data URI 内嵌 →
注入样式并套阅读器外壳。

样式来源有优先级：书里的 `stylesheet.css`（杂志版 EPUB 自带）> 本 skill 的 `references/magazine.css`。
所以「先跑 magazine-epub 做杂志版 EPUB，再跑本 skill 转 HTML」能拿到最好看的效果；
直接转普通 EPUB 也能跑，只是正文样式会是默认杂志版。

### 2. 验收（不能跳）

```bash
python3 <SKILL_DIR>/scripts/verify_html.py out.html
```

它分两层：

**静态检查**（不用浏览器）：页面上每个 `data-act` 是否都有 JS 处理分支；样式/正文里有没有
没内嵌的 `url(...)` 外部依赖。

**运行时检查**（headless Chrome 注入探针，**真的去点每个按钮**再读回状态）：
无 JS 错误 / 字号生效 / 行距生效 / 四个主题色板都生效且选中态正确 / 抽屉能开能关 /
当前章节键能开抽屉 / 目录条目数与 section 数一致 / 正文图片全部内嵌 / 灯箱能弹 /
回到顶部按钮会浮现 / 快捷键 M 能开抽屉 / 700·1024·1440 三种宽度下无横向溢出。

不跑这一步就交付，等于把"按钮按了没反应"这种问题留给用户。

### 3. 交付

给出 `.html` 文件，说明：体积（图片 base64 后会涨约 33%）、有哪些功能、键盘快捷键。

## 硬规矩（都是踩过的坑）

1. **工具栏按钮一律用事件委托**，不要逐个 `getElementById(...).onclick=`。
   漏绑一个 id 会在那一行抛 TypeError，**后面所有绑定都不会执行**，
   表现为"只有第一个按钮能用，其他全是死的"。统一用 `data-act` + 一个 document 级监听器。

2. **状态以内存为准，localStorage 只做持久化**。
   浏览器在 `file://` 下可能禁用存储，写入会静默失败；若把存储当唯一状态源，
   改完再读还是旧值 → 按钮"按了没反应"。读也用 try/catch 兜底。

3. **XHTML 里 `&nbsp;` 是未定义实体**，会让整个文档 XML 解析失败。用真实字符 `\u00a0`。

4. **内嵌图片时跳过 `data:` 和 `#` 开头的值**，否则二次替换会破坏已生成的 data URI。

5. **一个 HTML 里有多篇，CSS 里的 `body` 选择器要改写成容器类**（本 skill 用 `.rbody`）：
   `body{`→`.rbody{`、`body,`→`.rbody,`、`body `→`.rbody `。

6. **工具栏用 flex 时必须 `flex-wrap:wrap` + 子项 `min-width:0`**，
   否则窄窗口下内容撑出横向滚动条（`scrollWidth > clientWidth`）。

7. **章节标题提取要有兜底顺序**：`NCX 里的 navLabel` → `文档里的 <h1>` →
   `titlepage` 判为"封面" → `div.book-title` → `第 N 节`。
   只取 `<h1>` 会让封面页显示成"第 1 节"。

8. **验收器本身也会写崩**。探针里 `getAttribute('src')` 可能返回 null
   （比如灯箱里那张还没有 src 的 `<img>`），后面 `null.indexOf(...)` 会抛异常，
   **整个探针静默失效**——你会看到"验收通过"其实是没跑。
   写探针时：取值一律兜底（`|| ''`），每项检查独立 try/catch，
   并且让验收脚本能区分"探针没响应"和"检查项失败"。

## Output contract

- 一个 `.html` 文件（默认自带阅读器外壳）
- 验收脚本输出「✓ 全部通过」才算完成；有 FAIL 就先修再交付
- 附一份说明：文件体积、功能清单、快捷键（`←`/`→` 翻章、`M` 目录、`Esc` 关闭）

## Failure handling

- **验收脚本报"探针未返回结果"**：页面有致命 JS 错误导致探针没跑完。用
  `chrome --headless=new --dump-dom out.html` 手动看，或先在文件里搜 `<script>` 附近的语法错误
- **验收报 `ext>0`（图片没内嵌）**：有图片引用了包外路径，检查 EPUB 里该文件是否在 manifest 里
- **验收报横向溢出**：多半是工具栏或某个超宽元素没加 `flex-wrap` / `min-width:0`；用探针里那句
  `document.querySelectorAll('*')` 找 `right > clientWidth` 的元素定位
- **体积过大**：base64 编码本身会让图片膨胀约 33%，整份 HTML 相对原始 EPUB 通常涨 35–40%。
  想压体积就在转换前把图压到 1200px / JPEG q75

## Examples

Input: 「把 `某书.epub` 转成 html，我在电脑上读」
Output: `python3 scripts/epub_to_html.py 某书.epub -o 某书.html` → `python3 scripts/verify_html.py 某书.html`
→ 交付单文件 HTML + 验收结果

## Windows (win32) platform notes

脚本是 Python 3 跨平台，路径用正斜杠或 `Path` 对象即可，不要拼 `\`。
验收脚本会自动探测 Chrome/Chromium/Edge；Windows 上装在默认路径即可，
装在别处就用 `--chrome "C:\path\to\chrome.exe"` 或设环境变量 `CHROME_PATH`。
若系统没有 Chrome，可改用 Edge（已在探测列表里）。

## 扩展

改 `references/reader.css` 加主题、给 `references/reader.js` 加搜索/分页，都不用改脚本。
新增按钮时：在 HTML 模板里加 `data-act="xxx"`，在 reader.js 的委托分支里加一条 `act==='xxx'`，
两处都改完再跑验收脚本——它会检查每个 `data-act` 都有对应分支。
