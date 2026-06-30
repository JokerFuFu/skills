/* @meta
{
  "name": "chiphell/reply",
  "description": "在【当前已打开的帖子页】底部快速回复框(#fastpostmessage/#fastpostsubmit)发一条回帖,仅当显式 --submit yes 才真提交。内置“绝不下注”护栏:疑似 下注/梭哈 格式一律拒绝。",
  "domain": "www.chiphell.com",
  "args": {
    "text":   {"required": true,  "description": "回帖正文(求捞/讨论用,友好切题、非灌水)"},
    "submit": {"required": false, "description": "yes 才真正点提交;默认 no(只填不提交)"}
  },
  "capabilities": ["dom"],
  "readOnly": false,
  "example": "bb-browser site chiphell/reply \"<回帖正文>\" yes   (位置参数:text submit;省略submit=只填不提交)"
}
*/
async function(args) {
  const text = (args.text || '').trim();
  if (!text) return {error: 'Missing argument: text'};

  // 护栏:绝不下注。疑似 “球队 金额(10倍数)” 或 “梭哈” 一律拒绝提交。
  if (/^\s*梭哈\s*$/.test(text) || /^[一-龥A-Za-z()（）]{1,10}\s+\d{2,}\s*$/.test(text)) {
    return {submitted: false, error: '拒绝:文本疑似下注/梭哈格式。本适配器只用于求捞/讨论回帖,绝不代为下注。'};
  }
  if (text.length < 4) {
    return {submitted: false, error: '拒绝:文本过短,疑似灌水。求捞回帖请写真诚、切题的一两句。'};
  }

  const box = document.querySelector('#fastpostmessage');
  if (!box) {
    return {error: '当前页面无快速回复框 #fastpostmessage',
      hint: '请先 open 到目标帖子页(thread-<id>-1-1.html)再运行;或该帖已锁/无权回复'};
  }
  if (!document.querySelector('input[name=formhash]')?.value) {
    return {error: '无 formhash / 未登录', hint: '请先登录 chiphell(<CHIPHELL_USERNAME>)'};
  }

  // 填入正文
  box.value = text;
  ['input', 'change', 'keyup'].forEach(t => box.dispatchEvent(new Event(t, {bubbles: true})));

  const doSubmit = String(args.submit || 'no').toLowerCase() === 'yes';
  if (!doSubmit) {
    return {filled: true, submitted: false, text_len: text.length,
      note: '已填入快速回复框但未提交。确认无误后加 --submit yes 由命令点提交。',
      reminder: 'Discuz 两次发帖间隔限制:连发多帖之间务必等 20–30 秒。'};
  }

  const btn = document.querySelector('#fastpostsubmit');
  if (!btn) return {filled: true, submitted: false, error: '未找到提交按钮 #fastpostsubmit'};
  btn.click();
  return {filled: true, submitted: true, text_len: text.length,
    note: '已点击提交。请在 ~2-3 秒后用 chiphell/thread 复核楼层是否+1/回复是否出现,再隔 20–30 秒发下一帖。'};
}
