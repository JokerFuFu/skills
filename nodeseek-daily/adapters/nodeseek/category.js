/* @meta
{
  "name": "nodeseek/category",
  "description": "NodeSeek 按分类浏览最新帖子",
  "domain": "www.nodeseek.com",
  "args": {
    "name": {"required": true, "description": "分类 slug: daily/tech/info/review/trade/carpool/promotion/life/dev/photo-share/expose/sandbox"},
    "count": {"required": false, "description": "返回条数（默认 20，最大 100）"},
    "page": {"required": false, "description": "页码（默认 1）"}
  },
  "capabilities": ["network"],
  "readOnly": true,
  "example": "bb-browser site nodeseek/category tech 15   (参数按位置: name count page)"
}
*/

async function(args) {
  const name = (args.name || args._ || '').toString().replace(/^\/?categories\//, '').trim();
  if (!name) return { error: '缺少参数 name', hint: '提供分类 slug，如 tech / daily / info' };
  const count = Math.min(Math.max(parseInt(args.count) || 20, 1), 100);
  const page = Math.max(parseInt(args.page) || 1, 1);

  const num = (s) => { const x = (s || '').replace(/[^\d]/g, ''); return x ? parseInt(x, 10) : 0; };
  const fetchT = async (u) => {
    const ctl = new AbortController();
    const tid = setTimeout(() => ctl.abort(), 9000);
    try { return await fetch(u, { credentials: 'include', signal: ctl.signal }); }
    finally { clearTimeout(tid); }
  };

  const url = page === 1 ? '/categories/' + name : '/categories/' + name + '?page=' + page;
  let html;
  try {
    const r = await fetchT(url);
    if (!r.ok) return { error: 'HTTP ' + r.status, hint: r.status === 404 ? '分类不存在，检查 slug' : '可能遇到 Cloudflare 验证' };
    html = await r.text();
  } catch (e) {
    return { error: String(e), hint: '网络超时或浏览器未在 nodeseek.com' };
  }

  const doc = new DOMParser().parseFromString(html, 'text/html');
  let items = doc.querySelectorAll('ul.post-list:not(.topic-carousel-panel) > li.post-list-item');
  if (items.length === 0) items = doc.querySelectorAll('li.post-list-item');
  if (items.length === 0) return { error: '解析不到帖子', hint: '分类 slug 可能错误或页面结构已变更' };

  const parsed = [];
  const seen = new Set();
  items.forEach((it) => {
    if (it.classList.contains('topic-carousel-item')) return;
    const a = it.querySelector('.post-title a');
    if (!a) return;
    const href = a.getAttribute('href') || '';
    const m = href.match(/\/post-(\d+)/);
    if (!m) return;
    const id = +m[1];
    if (seen.has(id)) return;
    seen.add(id);

    const authorA = it.querySelector('.info-author a');
    const viewsEl = it.querySelector('.info-views span[title], .info-views span');
    const commEl = it.querySelector('.info-comments-count');
    const timeEl = it.querySelector('.info-last-comment-time time');

    parsed.push({
      post_id: id,
      title: a.textContent.trim(),
      url: 'https://www.nodeseek.com' + href,
      author: authorA ? authorA.textContent.trim() : null,
      uid: ((authorA && authorA.getAttribute('href')) || '').match(/\/space\/(\d+)/) ? (authorA.getAttribute('href').match(/\/space\/(\d+)/))[1] : null,
      views: num(viewsEl && (viewsEl.getAttribute('title') || viewsEl.textContent)),
      comments: num(commEl && (commEl.getAttribute('title') || commEl.textContent)),
      last_active: timeEl ? timeEl.getAttribute('title') : null
    });
  });

  if (parsed.length === 0) return { error: '解析不到帖子', hint: '分类 slug 可能错误或页面结构已变更' };

  // 第一页常含置顶帖（post_id 远小于本页最新）：打标记，方便消费者识别"非最新"
  const maxId = Math.max(...parsed.map((x) => x.post_id));
  const posts = parsed.slice(0, count).map((x, i) => ({
    rank: i + 1,
    pinned_or_old: x.post_id < maxId * 0.5,
    ...x
  }));

  return { category: name, page, count: posts.length, posts };
}
