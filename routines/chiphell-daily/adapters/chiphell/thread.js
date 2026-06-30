/* @meta
{
  "name": "chiphell/thread",
  "description": "读 chiphell 单帖:标题/楼主/锁帖/总楼层,并扫【全部页】判断指定用户是否已在帖内回过(求捞去重的权威依据,不依赖本地去重表时机)。只读。",
  "domain": "www.chiphell.com",
  "args": {
    "id": {"required": true,  "description": "帖子 tid(数字)"},
    "me": {"required": false, "description": "我的用户名(默认 <CHIPHELL_USERNAME>),用于检测是否已回过"}
  },
  "capabilities": ["dom"],
  "readOnly": true,
  "example": "bb-browser site chiphell/thread <thread_id> <CHIPHELL_USERNAME>   (位置参数:id me)"
}
*/
async function(args) {
  const id = String(args.id || '').replace(/\D/g, '');
  if (!id) return {error: 'Missing/invalid argument: id'};
  const me = (args.me || process.env.CHIPHELL_USERNAME || '').trim();
  const MAXP = 12; // 全页扫描上限,防超大帖

  const parse = (html) => new DOMParser().parseFromString(html, 'text/html');
  const authorsOf = (doc) => [...doc.querySelectorAll('#postlist .authi a, .pls .authi a')].map(a => a.textContent.trim());

  try {
    const r = await fetch(`/thread-${id}-1-1.html`, {credentials: 'same-origin'});
    const html = await r.text();
    const doc = parse(html);

    const logged_in = !(/请\s*登录|您需要先登录|用户登录/.test(((doc.body && doc.body.innerText) || '').slice(0, 200)));
    if (!logged_in) return {logged_in: false, error: '未登录', hint: '请先登录 chiphell'};

    const titleEl = doc.querySelector('#thread_subject, span#thread_subject, h1.ts a, h1.ts');
    const title = titleEl ? titleEl.textContent.replace(/\s+/g, ' ').trim() : (doc.title || '').trim();
    const firstAuthor = (doc.querySelector('#postlist .authi a.xw1, #postlist .authi a') || {}).textContent;
    const firstBody = doc.querySelector('#postlist td.t_f, #postlist .t_f, td[id^="postmessage_"]');
    const bodyExcerpt = firstBody ? firstBody.textContent.replace(/\s+/g, ' ').trim().slice(0, 400) : null;
    const hasFastpost = !!doc.querySelector('#fastpostmessage');
    const closed = /主题已关闭|本帖已被关闭|无权回复|已锁定/.test((doc.body && doc.body.innerText) || '');

    // 总页数
    const pgTxt = (doc.querySelector('.pg label, .pgs .pg label') || {}).textContent || '';
    const pm = pgTxt.match(/(\d+)\s*页/);
    const pages = Math.min(MAXP, pm ? parseInt(pm[1], 10) : 1);

    // 【关键】扫全部页判断是否已回过(权威去重,不依赖本地 farm_log 时机)
    let already_replied = authorsOf(doc).includes(me);
    let lastPageScanned = 1;
    for (let p = 2; p <= pages && !already_replied; p++) {
      try {
        const rp = await fetch(`/thread-${id}-${p}-1.html`, {credentials: 'same-origin'});
        const dp = parse(await rp.text());
        lastPageScanned = p;
        if (authorsOf(dp).includes(me)) already_replied = true;
      } catch (e) { /* 单页失败不致命 */ }
    }

    return {
      logged_in: true, id, title,
      author: firstAuthor ? firstAuthor.trim() : null,
      pages,
      already_replied,                       // 已扫全部页,可作为回帖前的权威去重
      scanned_pages: already_replied ? lastPageScanned : pages,
      can_reply: hasFastpost && !closed,
      closed,
      body_excerpt: bodyExcerpt,
      url: `https://www.chiphell.com/thread-${id}-1-1.html`
    };
  } catch (e) {
    return {error: 'fetch 失败: ' + (e && e.message)};
  }
}
