#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_to_html.py — 把 EPUB 合成一个可离线打开的单文件 HTML 阅读器

用法:
    python3 epub_to_html.py <book.epub> [-o out.html] [--css extra.css] [--no-shell]

做四件事:
    1. 按 spine 顺序取出每篇 body，跨文件链接改成页内锚点
    2. 图片（img src / svg xlink:href）转 data URI 内嵌，成品可单文件分发
    3. 注入书籍自身样式表；没有则用本 skill 的 magazine.css
    4. 套上阅读器外壳：工具栏 / 目录抽屉 / 主题 / 字号行距 / 灯箱 / 进度 / 打印样式

--no-shell 只做 1~3，产出纯正文 HTML（适合再加工或塞进别的模板）。
"""

import argparse
import base64
import html as html_mod
import re
import zipfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FALLBACK_CSS = SKILL_DIR / "references" / "magazine.css"
READER_CSS = SKILL_DIR / "references" / "reader.css"

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}


def data_uri(name, blob):
    mime = MIME.get(Path(name).suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(blob).decode()}"


def spine_order(z):
    opf_name = next((n for n in z.namelist() if n.endswith(".opf")), None)
    if not opf_name:
        return [], {}
    text = z.read(opf_name).decode("utf-8", "ignore")
    manifest = {m.group(2): m.group(1)
                for m in re.finditer(r'href="([^"]+)"[^>]*id="([^"]+)"', text)}
    order = [m.group(1) for m in re.finditer(r'<itemref[^>]*idref="([^"]+)"', text)]
    titles = {}
    ncx = next((n for n in z.namelist() if n.endswith(".ncx")), None)
    if ncx:
        nt = z.read(ncx).decode("utf-8", "ignore")
        for blk in re.findall(r"<navPoint.*?</navPoint>", nt, re.S):
            src = re.search(r'<content[^>]*src="([^"]+)"', blk)
            lab = re.search(r"<text>(.*?)</text>", blk, re.S)
            if src and lab:
                titles[src.group(1)] = re.sub(r"<[^>]+>", "", lab.group(1)).strip()
    return [manifest[i] for i in order if i in manifest], titles


def body_of(raw):
    m = re.search(r"<body([^>]*)>(.*)</body>", raw, re.S)
    if not m:
        return "", ""
    return m.group(1), m.group(2)


def rewrite_links(inner):
    """跨文件链接 → 页内锚点；同文件锚点保持不变"""
    inner = re.sub(r'href="([^"#]+\.html)#([^"]+)"', r'href="#\2"', inner)
    inner = re.sub(r'href="([^"#]+\.html)"',
                   lambda m: f'href="#sec-{Path(m.group(1)).stem}"', inner)
    return inner


def build(epub_path: Path, out_path: Path, extra_css: Path = None, shell: bool = True):
    z = zipfile.ZipFile(epub_path)
    order, ncx_titles = spine_order(z)
    names = set(z.namelist())
    uri_cache = {}

    def img_uri(rel):
        # 已经是 data: 或页内锚点就别动，避免二次替换把内容弄坏
        if rel.startswith("data:") or rel.startswith("#"):
            return rel
        if rel not in uri_cache:
            if rel not in names:
                print(f"  ! 引用了不存在的图片，跳过：{rel}")
                uri_cache[rel] = rel
                return rel
            uri_cache[rel] = data_uri(Path(rel).name, z.read(rel))
        return uri_cache[rel]

    sections, drawer = [], []
    for idx, href in enumerate(order):
        if href not in names:
            continue
        raw = z.read(href).decode("utf-8")
        body_attrs, inner = body_of(raw)
        inner = rewrite_links(inner)

        # 内嵌图片：一次处理 img[src] 与 svg 的 xlink:href / href
        inner = re.sub(r'(<img[^>]*\ssrc=")([^"]+)(")',
                       lambda m: m.group(1) + img_uri(m.group(2)) + m.group(3), inner)
        inner = re.sub(r'((?:xlink:)?href=")([^"]+)(")',
                       lambda m: m.group(1) + img_uri(m.group(2)) + m.group(3), inner)

        # 该文档自带的 <style>（封面页常有）
        local_css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", raw, re.S))
        local_css = re.sub(r"\bbody\b", ".rbody", local_css)

        classes = "rbody" + (" front-matter" if "front-matter" in body_attrs else "")

        title = ncx_titles.get(href) or ""
        if not title:
            m = re.search(r'<h1[^>]*>(.*?)</h1>', inner, re.S)
            if m:
                title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            elif "titlepage" in href.lower():
                title = "封面"
            else:
                m = re.search(r'<div class="book-title">(.*?)</div>', inner, re.S)
                title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else f"第 {idx+1} 节"

        is_cover = "titlepage" in href.lower()
        sec_class = "doc" + (" cover" if is_cover else "")
        sections.append(
            f'<section class="{sec_class}" id="sec-{Path(href).stem}" '
            f'data-title="{html_mod.escape(title, quote=True)}" '
            f'data-css="{html_mod.escape(local_css, quote=True)}">'
            f'<div class="{classes}">{inner}</div></section>'
        )
        drawer.append(f'<a href="#sec-{Path(href).stem}"><span class="n">{idx+1:02d}</span>'
                      f'<span class="t">{html_mod.escape(title)}</span></a>')

    # 书籍样式表：优先用书里的（杂志版 EPUB 自带），否则退回默认杂志样式
    css = ""
    if "stylesheet.css" in names:
        css = z.read("stylesheet.css").decode("utf-8")
        css = re.sub(r"\bbody\b", ".rbody", css)
        css = re.sub(r"\bhtml\b", ".rbody", css)
    else:
        css = FALLBACK_CSS.read_text(encoding="utf-8")
    if extra_css:
        css += "\n" + extra_css.read_text(encoding="utf-8")

    page_css = ""
    if "page_styles.css" in names:
        page_css = z.read("page_styles.css").decode("utf-8")

    body = "\n".join(sections)
    if not shell:
        out_path.write_text(
            f"<!DOCTYPE html>\n<html lang=\"zh\"><head><meta charset=\"utf-8\">\n"
            f"<title>电子书</title>\n<style>{page_css}\n{css}</style></head>\n"
            f"<body class=\"rbody\">{body}</body></html>\n", encoding="utf-8")
        return len(order), len(uri_cache)

    reader_css = READER_CSS.read_text(encoding="utf-8")
    reader_js = (SKILL_DIR / "references" / "reader.js").read_text(encoding="utf-8")

    doc = f"""<!DOCTYPE html>
<html lang="zh" data-theme="paper">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html_mod.escape(ncx_titles.get(order[0], "电子书") if order else "电子书")}</title>
<style>
{page_css}
{css}
{reader_css}
</style>
</head>
<body>
<div id="prog"></div>

<div class="bar" id="bar">
  <button class="ibtn" data-act="menu" title="目录（M）"><span class="ico">☰</span>目录</button>
  <span class="ttl">{html_mod.escape(ncx_titles.get(order[1], "电子书") if len(order) > 1 else "电子书")}</span>
  <button class="cur" id="cur" data-act="cur" title="当前章节"><b id="now"></b></button>
  <span class="sp"></span>
  <span class="seg">
    <button data-act="fs-" title="缩小字号">A−</button>
    <span class="val" id="fsv">18</span>
    <button data-act="fs+" title="放大字号">A+</button>
  </span>
  <span class="seg">
    <button data-act="lh-" title="收紧行距">行−</button>
    <span class="val" id="lhv">1.85</span>
    <button data-act="lh+" title="放宽行距">行+</button>
  </span>
  <span class="swatches">
    <button class="s-paper" data-act="theme:paper" title="纸色"></button>
    <button class="s-white" data-act="theme:white" title="白底"></button>
    <button class="s-sepia" data-act="theme:sepia" title="米黄"></button>
    <button class="s-night" data-act="theme:night" title="夜间"></button>
  </span>
</div>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer">
  <div class="head">
    <h4>目 录</h4>
    <button data-act="close" title="关闭（Esc）">×</button>
  </div>
  <div class="list">
  {''.join(drawer)}
  </div>
  <div class="foot">
    <kbd>←</kbd><kbd>→</kbd> 翻章 &nbsp; <kbd>M</kbd> 目录 &nbsp; <kbd>Esc</kbd> 关闭<br>
    点击插图可放大；设置会记住。
  </div>
</aside>

<main>
{body}
</main>

<button class="top" id="topbtn" data-act="top" title="回到顶部">↑</button>

<div id="lamp"><img id="limg" alt=""><div class="cap" id="lcap"></div></div>

<script>
{reader_js}
</script>
</body>
</html>
"""
    out_path.write_text(doc, encoding="utf-8")
    return len(order), len(uri_cache)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("epub")
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--css", help="额外样式表（追加在书籍样式之后）")
    ap.add_argument("--no-shell", action="store_true", help="只输出正文，不套阅读器外壳")
    args = ap.parse_args()

    src = Path(args.epub).expanduser().resolve()
    out = Path(args.output) if args.output else src.with_suffix(".html")
    extra = Path(args.css).expanduser().resolve() if args.css else None
    n_docs, n_imgs = build(src, out, extra, shell=not args.no_shell)
    print(f"已生成：{out}（{out.stat().st_size / 1024 / 1024:.2f} MB）")
    print(f"  {n_docs} 节，内嵌图片 {n_imgs} 张")
