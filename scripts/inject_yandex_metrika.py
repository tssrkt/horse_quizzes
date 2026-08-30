"""Inject the single Yandex Metrika counter into every built HTML page."""

from __future__ import annotations

import re
from pathlib import Path


COUNTER_ID = "112089914"
HEAD_FRAGMENT = """<!-- Yandex.Metrika counter -->
<script type="text/javascript">
    (function(m,e,t,r,i,k,a){
        m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
    })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=112089914', 'ym');

    ym(112089914, 'init', {ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true});
</script>"""
BODY_FRAGMENT = """<noscript><div><img src="https://mc.yandex.ru/watch/112089914" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->"""


def inject_page(path: Path) -> None:
    html = path.read_text(encoding="utf-8")
    if "Yandex.Metrika counter" in html or "ym(112089914, 'init'" in html:
        raise ValueError(f"{path}: Yandex Metrika is already present")
    if html.count("<head>") != 1:
        raise ValueError(f"{path}: expected exactly one <head>")
    html = html.replace("<head>", f"<head>\n{HEAD_FRAGMENT}", 1)
    html, replacements = re.subn(
        r"(<body(?:\s[^>]*)?>)",
        rf"\1\n{BODY_FRAGMENT}",
        html,
        count=1,
    )
    if replacements != 1:
        raise ValueError(f"{path}: expected exactly one <body>")
    path.write_text(html, encoding="utf-8", newline="\n")


def inject_all(output: Path) -> int:
    pages = sorted(output.rglob("*.html"))
    for path in pages:
        inject_page(path)
    return len(pages)
