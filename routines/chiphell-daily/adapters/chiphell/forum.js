/* @meta
{
  "name": "chiphell/forum",
  "description": "扫 chiphell 任意板块主题列表(按 fid),逐帖归类 betting(盘口/竞猜,绝不求捞)/welfare(福利/亡灵捞人)/discussion(休闲讨论)/forbidden(禁区)/self_rescue(自己的求捞帖),并标 sticky(全站置顶公告)。供求捞回血挑可回帖的休闲/福利帖。只读。",
  "domain": "www.chiphell.com",
  "args": {
    "fid":   {"required": true,  "description": "板块 fid:312=自由水世界(求捞主力) / 326=2026 WC(盘口板)"},
    "pages": {"required": false, "description": "扫几页,默认 1"}
  },
  "capabilities": ["dom"],
  "readOnly": true,
  "example": "bb-browser site chiphell/forum 312 2   (位置参数:fid pages)"
}
*/
async function(args) {
  const fid = String(args.fid || '').replace(/\D/g, '');
  if (!fid) return {error: 'Missing/invalid argument: fid（如 312=自由水世界 / 326=2026 WC）'};
  const pages = Math.max(1, Math.min(5, parseInt(args.pages || '1', 10) || 1));

  // 禁区帖(绝不回);自己的求捞帖(单独节流自顶)
  const FORBIDDEN = new Set((process.env.CHIPHELL_FORBIDDEN || '').split(',').map(x => x.trim()).filter(Boolean));
  const SELF_RESCUE = process.env.CHIPHELL_SELF_RESCUE || '';  // 你的求捞帖 tid(可选,env 配置)
  // 全站置顶公告(每个板块都出现的版务帖,非话题帖)——靠 sticky + 关键词双重识别
  const ANNOUNCE_KW = /受理|投诉|申诉|说明|结算|招募|招聘|规则|公告|实名|攻略|违规|置顶|版规|领导人/;

  const classify = (title, sticky) => {
    const t = title || '';
    // 盘口/竞猜帖:只收下注格式,绝不在此求捞。竞猜/福利盘/【数字】场次/VS/让球/盘口。
    if (/【\s*\d{1,4}\s*】/.test(t)
      || /\bVS\b/i.test(t) || /ＶＳ/.test(t)
      || /竞猜|福利盘|散盘|盘口/.test(t)
      || /[+\-－＋]\s*\d+(?:\.\d+)?\s*[一-龥(（]/.test(t)
      || /让\s*[\d一二三四五六七八九十]/.test(t)) return 'betting';
    // 福利/捞人/亡灵翻身帖(开放的话是好目标,是否开放由 skill 读帖判断)
    if (/福利|散\s*分|散\s*邪恶|捞|亡灵|幸运儿|清零|求捞|送\s*邪恶|回帖(奖励|得|给)/.test(t)) return 'welfare';
    return 'discussion';
  };

  try {
    const all = [];
    let logged_in = null;
    for (let p = 1; p <= pages; p++) {
      const r = await fetch(`/forum-${fid}-${p}.html`, {credentials: 'same-origin'});
      const html = await r.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      if (logged_in === null) {
        const head = doc.title + ' ' + ((doc.body && doc.body.innerText) || '').slice(0, 200);
        logged_in = !/请\s*登录|您需要先登录|用户登录|无权|提示信息/.test(head)
          && !!doc.querySelector('tbody[id^="normalthread_"], tbody[id^="stickthread_"]');
      }
      const rows = [...doc.querySelectorAll('tbody[id^="normalthread_"], tbody[id^="stickthread_"]')];
      for (const tb of rows) {
        const a = tb.querySelector('a.s.xst') || tb.querySelector('th a.xst') || tb.querySelector('a.xst');
        if (!a) continue;
        const href = a.getAttribute('href') || '';
        const idm = (tb.id.match(/_(\d+)/) || href.match(/thread-(\d+)/) || href.match(/tid=(\d+)/) || []);
        const id = idm[1] || null;
        if (!id) continue;
        const title = a.textContent.replace(/\s+/g, ' ').trim();
        const authorEl = tb.querySelector('td.by cite a, .by cite a');
        const replyEl = tb.querySelector('td.num a.xi2, .num a.xi2');
        // 建帖日期(作者列 em/span,或整列文本里的 YYYY-M-D[ HH:MM]);供热榜按帖龄过滤常青帖。附加字段,不影响既有消费方。
        const byTd = tb.querySelector('td.by');
        let created = null;
        if (byTd) {
          const sp = byTd.querySelector('em span, em');
          const rawDate = (sp && (sp.getAttribute('title') || sp.textContent)) || byTd.textContent || '';
          const dm = rawDate.match(/(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?/);
          if (dm) created = dm[0];
        }
        const sticky = /^stickthread_/.test(tb.id);
        let kind = FORBIDDEN.has(id) ? 'forbidden'
          : (id === SELF_RESCUE ? 'self_rescue' : classify(title, sticky));
        // 全站置顶公告:即使分类成 discussion 也单独标记,skill 应跳过
        const announce = sticky && ANNOUNCE_KW.test(title);
        all.push({
          id, title,
          url: `https://www.chiphell.com/thread-${id}-1-1.html`,
          author: authorEl ? authorEl.textContent.trim() : null,
          replies: replyEl ? parseInt(replyEl.textContent.trim(), 10) : null,
          created,
          sticky, announce, kind
        });
      }
    }

    if (logged_in === false) {
      return {logged_in: false, fid, threads: [],
        error: `forum-${fid} 需登录`, hint: '请在该 Chrome 里登录 chiphell(<CHIPHELL_USERNAME>)后重试'};
    }
    const seen = new Set(), threads = [];
    for (const t of all) { if (!seen.has(t.id)) { seen.add(t.id); threads.push(t); } }

    const counts = {total: threads.length};
    for (const k of ['discussion', 'welfare', 'betting', 'forbidden', 'self_rescue']) {
      counts[k] = threads.filter(t => t.kind === k).length;
    }
    return {
      logged_in: true, fid, counts, threads,
      note: 'discussion(休闲讨论,求捞好目标)/welfare(福利亡灵帖,开放才回)可求捞;betting(盘口/竞猜)绝不求捞=灌水违规;announce=true 的全站置顶公告跳过;forbidden/self_rescue 单独处理。最终是否回帖由 skill 逐帖判断,且求捞要先就帖子话题真诚搭话再自然带一句。'
    };
  } catch (e) {
    return {logged_in: null, fid, threads: [], error: 'fetch 失败: ' + (e && e.message)};
  }
}
