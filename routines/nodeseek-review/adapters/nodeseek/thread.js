/* @meta
{
  "name": "nodeseek/thread",
  "description": "NodeSeek 单帖正文与评论（自动翻评论页，按楼层去重排序）",
  "domain": "www.nodeseek.com",
  "args": {
    "id": {"required": true, "description": "帖子 ID（如 387328）或完整 URL"},
    "comments": {"required": false, "description": "返回评论条数（默认 20，0=不要评论，最大 200）"}
  },
  "capabilities": ["network"],
  "readOnly": true,
  "example": "bb-browser site nodeseek/thread 387328 30"
}
*/

async function(args) {
  if (!args.id && args.id !== 0) return { error: '缺少参数 id', hint: '提供帖子 ID 或 URL，如 387328' };
  const raw = String(args.id);
  const idm = raw.match(/(\d{3,})/);
  if (!idm) return { error: '无法识别帖子 ID', hint: '示例: 387328 或 https://www.nodeseek.com/post-387328-1' };
  const id = idm[1];
  const climit = (args.comments === undefined || args.comments === null)
    ? 20
    : Math.min(Math.max(parseInt(args.comments) || 0, 0), 200);

  const TIMEOUT = 9000;
  const fetchT = async (url) => {
    const ctl = new AbortController();
    const tid = setTimeout(() => ctl.abort(), TIMEOUT);
    try { return await fetch(url, { credentials: 'include', signal: ctl.signal }); }
    finally { clearTimeout(tid); }
  };
  // innerText 在多数运行环境可用且能保留换行；textContent 作为兜底，保证游离文档下仍取到文本
  const txt = (el) => el ? (el.innerText || el.textContent || '') : '';

  const parseItem = (it) => {
    const meta = txt(it.querySelector('.nsk-content-meta-info')).replace(/\s+/g, ' ').trim();
    const nameA = [...it.querySelectorAll('a[href^="/space/"]')].find((a) => a.textContent.trim());
    const anyA = it.querySelector('a[href^="/space/"]');
    const author = (nameA && nameA.textContent.trim()) || (meta.split(' ')[0] || null);
    const hrefForUid = (nameA && nameA.getAttribute('href')) || (anyA && anyA.getAttribute('href')) || '';
    const uidM = hrefForUid.match(/\/space\/(\d+)/);
    const timeEl = it.querySelector('time');
    const time = (timeEl && (timeEl.getAttribute('title') || timeEl.textContent.trim())) || null;
    const floorM = meta.match(/#(\d+)/);
    const body = txt(it.querySelector('.post-content')).trim();
    return { floor: floorM ? +floorM[1] : null, author, uid: uidM ? uidM[1] : null, time, body };
  };

  const fetchPage = async (pg) => {
    const url = '/post-' + id + '-' + pg;
    let r;
    try { r = await fetchT(url); } catch (e) { return { status: 0, err: String(e), doc: null }; }
    if (!r.ok) return { status: r.status, doc: null };
    return { status: 200, doc: new DOMParser().parseFromString(await r.text(), 'text/html') };
  };

  // 第一页：含楼主 + 首页评论（可能含置顶热门评论）
  let first;
  try { first = await fetchPage(1); } catch (e) { return { error: String(e), hint: '确认浏览器有 nodeseek.com 标签页' }; }
  if (first.status !== 200) {
    if (first.status === 0) return { error: first.err || 'fetch failed', hint: '网络超时或浏览器未在 nodeseek.com' };
    return { error: 'HTTP ' + first.status, hint: first.status === 404 ? '帖子不存在或已删除' : '可能需要登录或遇到验证页' };
  }
  const doc1 = first.doc;
  const items1 = [...doc1.querySelectorAll('.content-item')].map((el) => ({ el, p: parseItem(el) }));
  if (items1.length === 0) return { error: '解析不到内容', hint: '页面结构可能已变更，或返回了验证页' };

  // 楼主按楼层定位（NodeSeek 楼主为 #0），避免置顶/热门评论排在最前时取错；兜底取第一个
  const opEntry = items1.find((x) => x.p.floor === 0) || items1[0];
  const op = opEntry.p;
  const title = (txt(doc1.querySelector('h1')) || (doc1.querySelector('title') || {}).textContent || '').trim();
  // 分类优先用 DOM 锚点，回退英文 meta 正则
  const catA = doc1.querySelector('a[href*="/categories/"]');
  const opMeta = txt(doc1.querySelector('.nsk-content-meta-info'));
  const catRegex = opMeta.match(/\bin\s+([^\s#]+)/);
  const category = (catA && catA.textContent.trim()) || (catRegex ? catRegex[1] : null);

  // 收集评论：第一页除楼主外 + 后续页，按楼层去重
  const byFloor = new Map();
  const noFloor = [];
  const seenNoFloor = new Set();
  const addComment = (c, isOp) => {
    if (isOp) return;
    if (c.floor === null) {
      if (!c.body) return;
      const k = (c.author || '') + '|' + c.body.slice(0, 40);
      if (seenNoFloor.has(k)) return;
      seenNoFloor.add(k); noFloor.push(c);
      return;
    }
    if (!byFloor.has(c.floor)) byFloor.set(c.floor, c);
  };

  if (climit > 0) {
    items1.forEach((x) => addComment(x.p, x === opEntry));

    const MAX_PAGES = 12;
    let pg = 2;
    let emptyStreak = 0;
    while (byFloor.size + noFloor.length < climit && pg <= MAX_PAGES) {
      const res = await fetchPage(pg);
      if (res.status !== 200 || !res.doc) break;
      const items = [...res.doc.querySelectorAll('.content-item')];
      if (items.length === 0) break;
      const before = byFloor.size + noFloor.length;
      items.forEach((it) => addComment(parseItem(it), false));
      // 整页无新增可能是重复的置顶评论页；容忍 1 页，连续 2 页无新增才停
      if (byFloor.size + noFloor.length === before) { if (++emptyStreak >= 2) break; }
      else emptyStreak = 0;
      pg++;
    }
  }

  const comments = [...byFloor.values()]
    .sort((a, b) => a.floor - b.floor)
    .concat(noFloor)
    .slice(0, climit);

  return {
    post_id: +id,
    url: 'https://www.nodeseek.com/post-' + id + '-1',
    title,
    category,
    author: op.author,
    uid: op.uid,
    post_time: op.time,
    body: op.body,
    comments_collected: comments.length,
    comments
  };
}
