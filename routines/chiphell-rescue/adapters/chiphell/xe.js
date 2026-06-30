/* @meta
{
  "name": "chiphell/xe",
  "description": "读取当前登录用户的邪恶值/邪恶指数(XE)——世界杯菠菜板的下注货币,≠顶栏积分。亡灵保护以此为准。",
  "domain": "www.chiphell.com",
  "args": {},
  "capabilities": ["dom"],
  "readOnly": true,
  "example": "bb-browser site chiphell/xe"
}
*/
async function(args) {
  // 同源 fetch 复用浏览器登录态(cookie),不依赖当前在哪个页面。
  const parse = (html) => {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    return doc;
  };
  const loggedInDoc = (doc) =>
    !!doc.querySelector('a[href*="logout"]') ||
    !!doc.querySelector('strong.vwmy a, .vwmy a[href*="space-uid"]') ||
    !/请\s*登录|您需要先登录|用户登录/.test((doc.body && doc.body.innerText) || '');

  // 在文本里抓 “邪恶值/邪恶指数 : 数字”(带正负号)。只认 “邪恶”,绝不抓 “积分”。
  const grabXE = (text) => {
    const m = text.match(/邪恶(?:值|指数)?\s*[:：]?\s*(-?\d+)/);
    return m ? parseInt(m[1], 10) : null;
  };

  try {
    // 1) credit 页:Discuz 在此列出所有 extcredits(含改名后的“邪恶值”)
    const r = await fetch('/home.php?mod=spacecp&ac=credit&op=base', {credentials: 'same-origin'});
    const html = await r.text();
    const doc = parse(html);

    if (!loggedInDoc(doc)) {
      return {logged_in: false, xe: null,
        error: '未登录', hint: '请在该 Chrome 里登录 chiphell(<CHIPHELL_USERNAME>)后重试'};
    }

    // 优先在结构化积分列表里找“邪恶”行,精确取值
    let xe = null, raw = null;
    const cand = [...doc.querySelectorAll('li, td, span, em, p')].find(el =>
      /邪恶(值|指数)?/.test(el.textContent || ''));
    if (cand) {
      // 取该元素(及其父)文本里的数字
      raw = (cand.parentElement || cand).textContent.replace(/\s+/g, ' ').trim().slice(0, 80);
      xe = grabXE((cand.parentElement || cand).textContent) ?? grabXE(cand.textContent);
    }
    // 兜底:全文正则
    if (xe === null) { xe = grabXE(doc.body ? doc.body.innerText : html); }

    if (xe === null) {
      return {logged_in: true, xe: null,
        error: '已登录但未能在 credit 页解析到邪恶值',
        hint: '页面结构可能变化,请人工核对 home.php?mod=spacecp&ac=credit&op=base',
        raw};
    }
    return {logged_in: true, xe, undead: xe < 0, raw,
      note: xe < 0 ? '邪恶值为负=亡灵态,禁止下注,只能回帖求捞回血' : '邪恶值已转正'};
  } catch (e) {
    return {logged_in: null, xe: null, error: 'fetch 失败: ' + (e && e.message),
      hint: '确认当前标签在 www.chiphell.com 且网络可达'};
  }
}
