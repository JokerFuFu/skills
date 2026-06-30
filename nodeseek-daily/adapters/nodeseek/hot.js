/* @meta
{
  "name": "nodeseek/hot",
  "description": "NodeSeek 热门/最新帖子列表（综合热度排序或首页最新）",
  "domain": "www.nodeseek.com",
  "args": {
    "mode": {"required": false, "description": "hot=综合热度排序(默认) | latest=按页面原顺序(最新)"},
    "category": {"required": false, "description": "限定分类 slug: daily/tech/info/review/trade/carpool/promotion/life/dev/photo-share/expose/sandbox（留空=全站）"},
    "count": {"required": false, "description": "返回条数（默认 20，最大 100）"},
    "pages": {"required": false, "description": "抓取页数用于计算热度（默认 2，最大 10）"}
  },
  "capabilities": ["network"],
  "readOnly": true,
  "example": "bb-browser site nodeseek/hot hot \"\" 15   (参数按位置: mode category count pages)"
}
*/

async function(args) {
  const mode = String(args.mode || 'hot').toLowerCase();
  const count = Math.min(parseInt(args.count) || 20, 100);
  const pages = Math.min(Math.max(parseInt(args.pages) || 2, 1), 10);
  const cat = args.category ? String(args.category).replace(/^\/?categories\//, '').trim() : '';
  const base = cat ? '/categories/' + cat : '';

  const num = (s) => { const x = (s || '').replace(/[^\d]/g, ''); return x ? parseInt(x, 10) : 0; };
  const fetchT = async (u) => {
    const ctl = new AbortController();
    const tid = setTimeout(() => ctl.abort(), 9000);
    try { return await fetch(u, { credentials: 'include', signal: ctl.signal }); }
    finally { clearTimeout(tid); }
  };
  const selectItems = (doc) => {
    let items = doc.querySelectorAll('ul.post-list:not(.topic-carousel-panel) > li.post-list-item');
    if (items.length === 0) items = doc.querySelectorAll('li.post-list-item');
    return items;
  };

  const all = [];
  const seen = new Set();

  for (let p = 1; p <= pages; p++) {
    // 首页分页用 /page-N；分类分页用 ?page=N
    const url = p === 1
      ? (base || '/')
      : (base ? base + '?page=' + p : '/page-' + p);

    let html;
    try {
      const r = await fetchT(url);
      if (!r.ok) {
        if (p === 1) return { error: 'HTTP ' + r.status, hint: 'NodeSeek 可能在 Cloudflare 验证，先在浏览器打开 ' + url + ' 通过验证后重试' };
        break;
      }
      html = await r.text();
    } catch (e) {
      if (p === 1) return { error: String(e), hint: '网络超时或 bb-browser 未在 nodeseek.com；确认 daemon 已启动' };
      break;
    }

    const doc = new DOMParser().parseFromString(html, 'text/html');
    const items = selectItems(doc);
    if (items.length === 0) {
      if (p === 1) return { error: '解析不到帖子', hint: '页面结构可能已变更，或返回了登录/验证页' };
      break;
    }

    items.forEach((it) => {
      // 跳过轮播推荐项
      if (it.classList.contains('topic-carousel-item')) return;
      const a = it.querySelector('.post-title a');
      if (!a) return;
      const href = a.getAttribute('href') || '';
      const m = href.match(/\/post-(\d+)/);
      if (!m) return;
      const id = m[1];
      if (seen.has(id)) return;
      seen.add(id);

      const authorA = it.querySelector('.info-author a');
      const catA = [...it.querySelectorAll('a')].find((x) => (x.getAttribute('href') || '').includes('/categories/'));
      const viewsEl = it.querySelector('.info-views span[title], .info-views span');
      const commEl = it.querySelector('.info-comments-count');
      const timeEl = it.querySelector('.info-last-comment-time time');
      const dt = timeEl ? timeEl.getAttribute('datetime') : null;
      const ts = dt ? Date.parse(dt) : NaN;

      all.push({
        post_id: +id,
        title: a.textContent.trim(),
        url: 'https://www.nodeseek.com' + href,
        author: authorA ? authorA.textContent.trim() : null,
        uid: ((authorA && authorA.getAttribute('href')) || '').match(/\/space\/(\d+)/) ? ((authorA.getAttribute('href')).match(/\/space\/(\d+)/))[1] : null,
        category: catA ? catA.textContent.trim() : null,
        category_slug: ((catA && catA.getAttribute('href')) || '').match(/\/categories\/([\w-]+)/) ? (catA.getAttribute('href').match(/\/categories\/([\w-]+)/))[1] : null,
        views: num(viewsEl && (viewsEl.getAttribute('title') || viewsEl.textContent)),
        comments: num(commEl && (commEl.getAttribute('title') || commEl.textContent)),
        last_active: timeEl ? timeEl.getAttribute('title') : null,
        _ts: isNaN(ts) ? 0 : ts
      });
    });
  }

  if (all.length === 0) return { error: '无帖子', hint: '解析结果为空' };

  let ranked;
  let dropped_evergreen = 0;
  if (mode === 'latest') {
    ranked = all.slice();
  } else {
    // 过滤被顶起的"常青/置顶"老帖:post_id 远小于本批最新帖的,
    // 其累计评论/浏览量会霸榜但不代表当日热点,从热度池剔除。
    const maxId = Math.max(...all.map((x) => x.post_id));
    const recentPool = all.filter((x) => x.post_id >= maxId * 0.5);
    const pool = recentPool.length >= Math.min(count, 5) ? recentPool : all;
    dropped_evergreen = all.length - pool.length;

    // 归一化只在热度池内做,避免被剔除的极端老帖拉偏基准。
    const maxC = Math.max(...pool.map((x) => x.comments), 1);
    const maxV = Math.max(...pool.map((x) => x.views), 1);
    const now = Date.now();
    ranked = pool.map((x) => {
      const c = x.comments / maxC;                 // 评论热度（讨论度）
      const v = x.views / maxV;                    // 浏览热度
      const ageH = x._ts ? (now - x._ts) / 3.6e6 : 999;
      const recency = Math.max(0, 1 - ageH / 168); // 7 天内线性衰减
      const score = 0.55 * c + 0.20 * v + 0.25 * recency;
      return Object.assign({}, x, { score: +score.toFixed(4) });
    }).sort((a, b) => b.score - a.score);
  }

  const posts = ranked.slice(0, count).map((x, i) => {
    const o = Object.assign({ rank: i + 1 }, x);
    delete o._ts;
    return o;
  });

  return { mode, category: cat || 'all', scanned: all.length, dropped_evergreen, pages_fetched: pages, count: posts.length, posts };
}
