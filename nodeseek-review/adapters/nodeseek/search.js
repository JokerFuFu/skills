/* @meta
{
  "name": "nodeseek/search",
  "description": "在 NodeSeek 站内搜索（经 Google site: 搜索真实浏览器），返回相关帖子",
  "domain": "www.google.com",
  "args": {
    "query": {"required": true, "description": "搜索关键词"},
    "count": {"required": false, "description": "返回条数（默认 10，最大 20）"}
  },
  "capabilities": ["network"],
  "readOnly": true,
  "example": "bb-browser site nodeseek/search \"AetherCloud 评价\""
}
*/

async function(args) {
  const query = (args.query || args._ || '').toString().trim();
  if (!query) return { error: '缺少参数 query', hint: '提供搜索关键词' };
  const num = Math.min(parseInt(args.count) || 10, 20);

  const q = 'site:www.nodeseek.com ' + query;
  const url = '/search?q=' + encodeURIComponent(q) + '&num=' + (num + 10) + '&hl=zh-CN';

  let html;
  try {
    const ctl = new AbortController();
    const tid = setTimeout(() => ctl.abort(), 12000);
    let r;
    try { r = await fetch(url, { credentials: 'include', signal: ctl.signal }); }
    finally { clearTimeout(tid); }
    if (!r.ok) return { error: 'HTTP ' + r.status, hint: '确认有 google.com 标签页，且未被人机验证拦截' };
    html = await r.text();
  } catch (e) {
    return { error: String(e), hint: 'Google 搜索超时或失败，可能需要在浏览器先完成人机验证' };
  }

  // 同意页 / 人机验证 / JS 壳页识别
  const blocked = /\/sorry\/|unusual traffic|consent\.google|Before you continue|id="captcha|enablejs.*noscript/i.test(html);

  const doc = new DOMParser().parseFromString(html, 'text/html');
  const out = [];
  const seen = new Set();

  const pushResult = (href, title, snippet) => {
    const m = (href || '').match(/nodeseek\.com\/post-(\d+)/);
    if (!m) return;
    const id = m[1];
    if (seen.has(id)) return;
    if (!title) return;
    seen.add(id);
    out.push({
      post_id: +id,
      title: title.trim(),
      url: 'https://www.nodeseek.com/post-' + id + '-1',
      snippet: snippet ? snippet.trim().slice(0, 300) : null
    });
  };

  // 主策略：以 h3 标题为锚，向上找承载链接与摘要
  doc.querySelectorAll('h3').forEach((h3) => {
    let anchor = h3.closest('a');
    if (!anchor || !/nodeseek\.com\/post-/.test(anchor.getAttribute('href') || '')) {
      anchor = h3.parentElement ? h3.parentElement.querySelector('a[href*="nodeseek.com/post-"]') : null;
    }
    let href = anchor ? anchor.getAttribute('href') : '';
    if (href && href.startsWith('/url')) {
      const w = href.match(/[?&](?:q|url)=([^&]+)/);
      if (w) href = decodeURIComponent(w[1]);
    }
    if (!href) return;

    // 摘要：向上找结果容器，去掉标题与 cite 后的剩余文本
    let snippet = '';
    let container = h3;
    for (let i = 0; i < 5 && container; i++) {
      container = container.parentElement;
      if (!container) break;
      const txt = container.textContent || '';
      if (txt.length > h3.textContent.length + 60) {
        const clone = container.cloneNode(true);
        const ch = clone.querySelector('h3'); if (ch) ch.remove();
        clone.querySelectorAll('cite').forEach((c) => c.remove());
        const rem = clone.textContent.trim();
        if (rem.length > 30) { snippet = rem; break; }
      }
    }
    pushResult(href, h3.textContent, snippet);
  });

  // 兜底：直接扫所有指向 post 的链接
  if (out.length === 0) {
    doc.querySelectorAll('a[href*="nodeseek.com/post-"]').forEach((a) => {
      pushResult(a.getAttribute('href'), a.textContent || ('帖子 ' + (a.getAttribute('href') || '')), null);
    });
  }

  if (out.length === 0) {
    if (blocked) return { error: 'Google 人机验证/同意页拦截', hint: '在浏览器打开 https://www.google.com 完成一次人机验证或同意 cookie 后重试' };
    return { error: '无搜索结果', hint: '换个关键词，或在浏览器打开 google.com 确认能正常搜索' };
  }

  return { query, source: 'google site:www.nodeseek.com', count: Math.min(out.length, num), results: out.slice(0, num) };
}
