#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_html.py — 单文件 HTML 阅读器的自动化验收

用法:
    python3 verify_html.py out.html [--widths 700,1024,1440] [--chrome /path/to/chrome]

检查项:
    1. 无 JS 运行时错误
    2. 每个工具栏按钮都真实生效（字号/行距/主题/抽屉/当前章节/回到顶部）
    3. 抽屉能开能关，目录条目数与文档 section 数一致
    4. 图片全部内嵌为 data URI（无外链依赖）
    5. 多个宽度下无横向溢出（scrollWidth == clientWidth）

原理：把一段探针脚本注入 HTML 副本，让它把结果写进 <title>，
再用 headless Chrome 的 --dump-dom 把 title 读回来。
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

PROBE = r"""
<script>
(function(){
  var errs = [];
  var out = [];          // 必须和 ck() 同在��层作用域，否则 ck 引用不到
  window.addEventListener('error', function(e){ errs.push(e.message); });
  function ck(name, fn){
    try { out.push(name + '=' + fn()); }
    catch(e){ out.push(name + '=THREW:' + (e && e.message ? e.message : e)); }
  }
  window.addEventListener('load', function(){
    setTimeout(function(){
      function q(s){ return document.querySelector(s); }
      function fs(){ return getComputedStyle(document.body).fontSize; }
      function lh(){ return getComputedStyle(document.body).lineHeight; }

      ck('errors', function(){ return errs.length ? errs.join(';') : '0'; });

      // 字号
      ck('fs', function(){
        var f0 = fs(); q('[data-act="fs+"]').click();
        var ok = fs() !== f0; q('[data-act="fs-"]').click();
        return ok ? 'ok' : 'FAIL';
      });

      // 行距
      ck('lh', function(){
        var l0 = lh(); q('[data-act="lh+"]').click();
        var ok = lh() !== l0; q('[data-act="lh-"]').click();
        return ok ? 'ok' : 'FAIL';
      });

      // 主题：四个色板都要能切
      ck('theme', function(){
        var ok = true, t;
        ['paper','white','sepia','night'].forEach(function(name){
          q('[data-act="theme:' + name + '"]').click();
          t = document.documentElement.getAttribute('data-theme');
          if (t !== name) ok = false;
        });
        q('[data-act="theme:paper"]').click();
        return ok ? 'ok' : 'FAIL';
      });
      ck('swatch', function(){
        q('[data-act="theme:night"]').click();
        var ok = q('[data-act="theme:night"]').classList.contains('on');
        q('[data-act="theme:paper"]').click();
        return ok ? 'ok' : 'FAIL';
      });

      // 抽屉
      ck('drawerOpen', function(){
        q('[data-act="menu"]').click();
        return q('#drawer').classList.contains('on') ? 'ok' : 'FAIL';
      });
      ck('drawerClose', function(){
        q('[data-act="close"]').click();
        return !q('#drawer').classList.contains('on') ? 'ok' : 'FAIL';
      });
      ck('curBtn', function(){
        q('[data-act="cur"]').click();
        return q('#drawer').classList.contains('on') ? 'ok' : 'FAIL';
      });
      q('[data-act="close"]').click();

      // 目录条目 vs section 数
      ck('toc', function(){
        var links = document.querySelectorAll('#drawer a').length;
        var secs = document.querySelectorAll('section.doc').length;
        return (links === secs && links > 0) ? 'ok' : 'FAIL(' + links + '!=' + secs + ')';
      });

      // 图片是否全部内嵌（只看正文里的图，灯箱那张没有 src）
      ck('imgs', function(){
        var imgs = document.querySelectorAll('section.doc img');
        var ext = 0;
        for (var i = 0; i < imgs.length; i++) {
          var s = imgs[i].getAttribute('src') || '';
          if (s.indexOf('data:') !== 0) ext++;
        }
        return imgs.length + '/ext=' + ext + (ext === 0 ? ':ok' : ':FAIL');
      });

      // 灯箱：点正文里的图应弹出
      ck('lamp', function(){
        var img = document.querySelector('section.doc figure img');
        if (!img) return 'FAIL(no img)';
        img.click();
        var ok = q('#lamp').classList.contains('on');
        q('#lamp').click();
        return ok ? 'ok' : 'FAIL';
      });

      // 回到顶部按钮（页面开了 scroll-behavior:smooth，测量时临时关掉）
      ck('topBtn', function(){
        var root = document.documentElement;
        var prev = root.style.scrollBehavior;
        root.style.scrollBehavior = 'auto';
        window.scrollTo(0, 1500);
        window.dispatchEvent(new Event('scroll'));
        var btn = q('#topbtn');
        var shown = btn ? btn.classList.contains('on') : false;
        root.style.scrollBehavior = prev;
        window.scrollTo(0, 0);
        window.dispatchEvent(new Event('scroll'));
        return !btn ? 'FAIL(no btn)' : (shown ? 'ok' : 'FAIL');
      });

      // 快捷键 M 开关抽屉
      ck('keyM', function(){
        document.dispatchEvent(new KeyboardEvent('keydown', {key:'M', bubbles:true}));
        var ok = q('#drawer').classList.contains('on');
        document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
        return ok ? 'ok' : 'FAIL';
      });

      // 横向溢出
      ck('overflow', function(){
        var vw = document.documentElement.clientWidth;
        var sw = document.documentElement.scrollWidth;
        return (sw <= vw + 1) ? 'ok' : 'FAIL(' + sw + '>' + vw + ')';
      });

      document.title = 'PROBE||' + out.join('||');
    }, 700);
  });
})();
</script>
"""


def find_chrome(explicit=None):
    if explicit:
        return explicit
    env = os.environ.get("CHROME_PATH")
    if env and Path(env).exists():
        return env
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


def run_probe(chrome, html_path: Path, width: int):
    """注入探针 → headless 跑 → 从 title 取结果"""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tf:
        tf.write(html_path.read_text(encoding="utf-8").replace("</body>", PROBE + "</body>"))
        probe_file = Path(tf.name)
    try:
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
               "--virtual-time-budget=9000", f"--window-size={width},1000",
               "--dump-dom", probe_file.as_uri()]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        m = re.search(r"<title>PROBE\|\|(.*?)</title>", res.stdout, re.S)
        if not m:
            return None
        return dict(part.split("=", 1) for part in m.group(1).split("||") if "=" in part)
    except subprocess.TimeoutExpired:
        return None
    finally:
        probe_file.unlink(missing_ok=True)


def static_checks(html_path: Path):
    """不需要浏览器的静态检查：data-act 覆盖率 + CSS 外部依赖"""
    html = html_path.read_text(encoding="utf-8")
    problems = []

    # 1) 每个 data-act 都必须有对应的 JS 分支
    acts = sorted(set(re.findall(r'data-act="([^"]+)"', html)))
    scripts = "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S))
    uncovered = []
    for act in acts:
        if act.startswith("theme:"):
            ok = "theme:" in scripts
        else:
            ok = f"'{act}'" in scripts or f'"{act}"' in scripts
        if not ok:
            uncovered.append(act)
    if uncovered:
        problems.append(f"这些 data-act 在 JS 里没有处理分支：{', '.join(uncovered)}")

    # 2) 样式表里的 url(...) 是否都内嵌了
    ext_urls = []
    for m in re.finditer(r"url\(\s*['\"]?([^'\")]+)", html):
        u = m.group(1).strip()
        if not u.startswith("data:") and not u.startswith("#"):
            ext_urls.append(u)
    if ext_urls:
        problems.append(f"样式/内容里有外部依赖 url()：{', '.join(sorted(set(ext_urls))[:5])}")

    return acts, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("--widths", default="700,1024,1440")
    ap.add_argument("--chrome", default=None)
    args = ap.parse_args()

    html_path = Path(args.html).expanduser().resolve()
    if not html_path.exists():
        print(f"✗ 文件不存在：{html_path}")
        sys.exit(2)

    chrome = find_chrome(args.chrome)
    if not chrome:
        print("✗ 找不到 Chrome/Chromium，请用 --chrome 指定路径")
        sys.exit(2)
    print(f"浏览器：{chrome}")
    print(f"文件：{html_path}（{html_path.stat().st_size / 1024 / 1024:.2f} MB）\n")

    failures = []

    # 静态检查
    acts, problems = static_checks(html_path)
    print(f"静态检查：{len(acts)} 个 data-act 全部有处理分支 ✓" if not problems else "静态检查：")
    for p in problems:
        print(f"  ✗ {p}")
        failures.append(p)
    if not problems:
        print("静态检查：data-act 覆盖率 / 外部 url() 依赖 ✓")
    print()

    # 运行时检查
    widths = [int(w) for w in args.widths.split(",") if w.strip()]
    for w in widths:
        r = run_probe(chrome, html_path, w)
        if r is None:
            print(f"  宽 {w}px → 探针未返回结果（页面可能有致命 JS 错误）")
            failures.append(f"宽度 {w} 探针无响应")
            continue
        bad = [k for k, v in r.items()
               if v.startswith("FAIL") or v.startswith("THREW") or (k == "errors" and v != "0")]
        flag = "✓" if not bad else "✗"
        print(f"  宽 {w}px {flag} " + "  ".join(f"{k}={v}" for k, v in r.items()))
        for k in bad:
            failures.append(f"宽度 {w}: {k}={r[k]}")

    print()
    if failures:
        print("验收未通过：")
        for f in failures:
            print("  ✗", f)
        sys.exit(1)
    print("✓ 全部通过：按钮功能 / 抽屉 / 目录 / 图片内嵌 / 无横向溢出 / 无 JS 错误 / data-act 全覆盖 / 无外部依赖")


if __name__ == "__main__":
    main()
