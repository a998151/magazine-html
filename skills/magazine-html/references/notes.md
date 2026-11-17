# 踩坑与扩展笔记

## 一、按钮"全部失效"的真正原因

第一版阅读器里逐个写：

```js
document.getElementById('theme').onchange = ...
document.getElementById('fsup').onclick  = ...
document.getElementById('close').onclick = ...   // ← HTML 里根本没有 #close
```

`#close` 是我以为有、实际没渲染出来的元素。那一行抛 `TypeError: Cannot read properties of null`，
**后面所有 `getElementById(...).onclick = ...` 都不会执行**。

结果：目录按钮能用（在出错行之前绑的），字号、行距、主题、章节下拉、进度条、灯箱全是死的。
用户看到的是"顶部的按钮很多功能都是无效的"。

修法有两条，缺一不可：

1. **事件委托**：一个 `document` 级监听器按 `data-act` 分发，从此不存在漏绑：
   ```js
   document.addEventListener('click', function(e){
     var b = e.target.closest('[data-act]');
     if(!b) return;
     var act = b.getAttribute('data-act');
     ...
   });
   ```
2. **静态校验**：生成后比对「页面上的 `data-act` 集合」与「JS 里处理的分支集合」，
   差集非空就报错。脚本 `epub_to_html.py` 之后的验收脚本就是干这个的。

## 二、localStorage 在 file:// 下可能不可用

原代码把 `localStorage` 当唯一状态源：

```js
set('fs', v+'px');          // 写入失败会被 catch 吞掉
apply();                     // 再读，还是旧值 → 看起来"按了没反应"
```

`file://` 页面在部分浏览器/配置下访问 `localStorage` 会抛 `SecurityError`。
而且**写入失败是静默的**，不报错，只是设置不生效。

正确做法：**内存里的 `state` 对象是唯一真相**，localStorage 只在变更时顺手写一份：

```js
var state = { fs: parseFloat(get('fs','18px')) || 18, lh: get('lh','1.85'), theme: get('theme','paper') };
// 改的时候：state.fs = ...; set('fs', state.fs+'px'); apply();
```

## 三、图片内嵌的坑

- **不能二次替换**：先替换 `<img src>` 再替换 `<image xlink:href>` 时，
  后者的正则 `href="([^"]+)"` 会命中前一步生成的 `xlink:href="data:image/jpeg;base64,..."`，
  然后去 zip 里找一个叫 `data:image/jpeg;base64,...` 的文件 → KeyError。
  办法：合并成一个正则 `((?:xlink:)?href=")([^"]+)(")`，并在取值函数里跳过 `data:` / `#` 开头。
- **包外路径要容错**：源 EPUB 里可能引用了不在包里的图（比如被删掉的广告图），
  直接 `z.read()` 会崩。取不到就原样保留并打印一行告警。

## 四、一个 HTML 里有多篇，body 选择器会失效

EPUB 每篇是独立文档，各自有 `<body>`。合并成一个 HTML 后只有**一个** body，
所以书里的 `body { ... }` 只对第一篇生效（或者被第一条规则全局覆盖）。

本 skill 的做法：生成时把样式表里的 `body` 统一替换成 `.rbody`，
每篇内容包在 `<div class="rbody">` 里：

```python
css = re.sub(r"\bbody\b", ".rbody", css)
```

注意 `body, body * { ... }` 会变成 `.rbody, .rbody * { ... }` ✓，
`body.front-matter > p` 会变成 `.rbody.front-matter > p` ✓。

## 五、工具栏撑出横向滚动条

`display:flex` 默认 `flex-wrap:nowrap`，工具栏控件多、窗口窄时，
内容宽度超过视口 → `document.documentElement.scrollWidth > clientWidth` → 出现横向滚动条。

修法：`flex-wrap:wrap` + 子项 `min-width:0` + `overflow:hidden`/`text-overflow:ellipsis`。

## 六、章节标题提取

只取 `<h1>` 会让封面页（没有 h1）显示成"第 1 节"。兜底顺序：

```
ncx 里的 navLabel → 文档里的 <h1> → titlepage 判为「封面」→ div.book-title → 第 N 节
```

## 七、自动化验收的做法

用 headless Chrome，**让页面自己汇报结果**：

```bash
chrome --headless=new --disable-gpu --no-sandbox --virtual-time-budget=9000 \
       --dump-dom file:///tmp/probe.html
```

探针脚本把结论写进 `document.title`，再从 dump 出来的 DOM 里用正则抓 `<title>PROBE||...</title>`。

要点：
- 探针要注入到 HTML 的**副本**里，别污染交付物
- 用 `setTimeout(..., 700)` 等字体/图片就绪再测
- `--virtual-time-budget` 让定时器在无头模式下正常推进
- Chrome 路径要跨平台探测：
  macOS `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`、
  Linux `google-chrome`、Windows `C:\Program Files\...`，也支持环境变量 `CHROME_PATH`

## 八、别做的事

- 不要在成品 HTML 里写 `&nbsp;`（XHTML 未定义实体，XML 解析会失败）
- 不要用 `background` 硬编码浅色（夜间模式下会刺眼）——用 CSS 变量 + `color-scheme`
- 不要把章节正文塞进 `<iframe>`（除非要做真·翻页模式），否则目录高亮、进度、搜索都要跨文档通信
- 不要给正文加抽言块/改段落顺序——那是改书，不是做阅读器
