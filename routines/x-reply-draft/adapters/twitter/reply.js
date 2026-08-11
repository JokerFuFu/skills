/* @meta
{
  "name": "twitter/reply",
  "description": "回复一条推文（CreateTweet 写操作）。默认 dry-run，只有末位参数为 yes 才真正发布。经真实登录浏览器会话提交。",
  "domain": "x.com",
  "args": {
    "tweet_id": {"required": true, "description": "被回复推文的 id（数字，in_reply_to）"},
    "text": {"required": true, "description": "回帖正文（≤270 字符）"},
    "confirm": {"required": false, "description": "传 yes 才真正发布；否则仅 dry-run 返回将要发送的内容"}
  },
  "capabilities": ["network"],
  "readOnly": false,
  "example": "bb-browser site twitter/reply 1234567890 \"nice point — ...\" yes"
}
*/

async function(args) {
  const id = String(args.tweet_id || args._ || '').replace(/\D/g, '');
  const text = (args.text || '').toString();
  const confirm = (args.confirm || args._2 || '').toString().toLowerCase() === 'yes';

  if (!id) return { error: '缺少 tweet_id', hint: '提供被回复推文的数字 id' };
  if (!text.trim()) return { error: '回帖正文为空' };
  if (text.length > 270) return { error: '回帖过长', hint: '≤270 字符，当前 ' + text.length };

  const ct0 = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith('ct0='))?.split('=')[1];
  if (!ct0) return { error: 'No ct0 cookie', hint: 'Please log in to https://x.com first.' };

  if (!confirm) {
    return { dry_run: true, would_post: true, in_reply_to: id, text, length: text.length,
             hint: '末位参数传 yes 才会真正发布' };
  }

  // —— 自包含 helper（私有目录适配器不会被注入社区 _helper.js）——
  // 下面提取 GraphQL queryId 与 x-client-transaction-id 生成器的做法，派生自
  // epiral/bb-sites 的 twitter/_helper.js：https://github.com/epiral/bb-sites
  const _getReq = () => {
    let req;
    window.webpackChunk_twitter_responsive_web.push(
      [['__bb_r_' + Date.now()], {}, (r) => { req = r; }]);
    return req;
  };
  const findGraphQLQueryId = (operationName, fallbackQueryId) => {
    try {
      const req = _getReq();
      const op = operationName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const patterns = [
        new RegExp('queryId:\\s*"([^"]+)"\\s*,\\s*operationName:\\s*"' + op + '"'),
        new RegExp('operationName:\\s*"' + op + '"\\s*,\\s*queryId:\\s*"([^"]+)"')
      ];
      for (const id of Object.keys(req.m)) {
        try {
          const src = req.m[id].toString();
          if (!src.includes(operationName)) continue;
          for (const p of patterns) { const m = src.match(p); if (m) return m[1]; }
        } catch {}
      }
    } catch {}
    return fallbackQueryId;
  };
  const findTransactionIdGenerator = async () => {
    try {
      const req = _getReq();
      for (const id of Object.keys(req.m)) {
        try {
          const src = req.m[id].toString();
          if (!src.includes('x-client-transaction-id') || !src.includes('rweb_client_transaction_id_enabled')) continue;
          const mod = req(id);
          for (const fn of Object.values(mod)) {
            if (typeof fn !== 'function') continue;
            try {
              const sample = await fn('x.com', '/i/api/graphql/test/Op', 'GET');
              if (typeof sample !== 'string' || sample.length < 40) continue;
              try { if (atob(sample).startsWith('e:')) continue; } catch {}
              return fn;
            } catch {}
          }
        } catch {}
      }
    } catch {}
    return null;
  };

  const genTxId = await findTransactionIdGenerator();
  const queryId = findGraphQLQueryId('CreateTweet', 'xT36w0XM3A8jDynpkdN6Aw');
  if (!genTxId) return { error: 'Cannot find transaction-id generator', hint: 'x.com webpack 结构可能已变' };
  if (!queryId) return { error: 'Cannot find CreateTweet queryId', hint: 'x.com API 结构可能已变' };

  const bearer = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA';
  const path = '/i/api/graphql/' + queryId + '/CreateTweet';
  const txId = await genTxId('x.com', path, 'POST');

  const headers = {
    'Authorization': 'Bearer ' + bearer,
    'X-Csrf-Token': ct0,
    'X-Twitter-Auth-Type': 'OAuth2Session',
    'X-Twitter-Active-User': 'yes',
    'X-Twitter-Client-Language': 'zh-cn',
    'Content-Type': 'application/json',
    'X-Client-Transaction-Id': txId
  };

  const variables = {
    tweet_text: text,
    reply: { in_reply_to_tweet_id: id, exclude_reply_user_ids: [] },
    dark_request: false,
    media: { media_entities: [], possibly_sensitive: false },
    semantic_annotation_ids: [],
    disallowed_reply_options: null
  };

  const features = {
    premium_content_api_read_enabled: false,
    communities_web_enable_tweet_community_results_fetch: true,
    c9s_tweet_anatomy_moderator_badge_enabled: true,
    responsive_web_grok_analyze_button_fetch_trends_enabled: false,
    responsive_web_grok_analyze_post_followups_enabled: true,
    responsive_web_jetfuel_frame: true,
    responsive_web_grok_share_attachment_enabled: true,
    responsive_web_edit_tweet_api_enabled: true,
    graphql_is_translatable_rweb_tweet_is_translatable_enabled: true,
    view_counts_everywhere_api_enabled: true,
    longform_notetweets_consumption_enabled: true,
    responsive_web_twitter_article_tweet_consumption_enabled: true,
    tweet_awards_web_tipping_enabled: false,
    responsive_web_grok_show_grok_translated_post: false,
    responsive_web_grok_analysis_button_from_backend: true,
    creator_subscriptions_quote_tweet_preview_enabled: false,
    longform_notetweets_rich_text_read_enabled: true,
    longform_notetweets_inline_media_enabled: true,
    profile_label_improvements_pcf_label_in_post_enabled: true,
    rweb_cashtags_composer_attachment_enabled: true,
    verified_phone_label_enabled: false,
    articles_preview_enabled: true,
    rweb_video_screen_enabled: false,
    responsive_web_grok_community_note_auto_translation_is_enabled: false,
    responsive_web_graphql_skip_user_profile_image_extensions_enabled: false,
    freedom_of_speech_not_reach_fetch_enabled: true,
    standardized_nudges_misinfo: true,
    tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled: true,
    responsive_web_graphql_timeline_navigation_enabled: true,
    responsive_web_enhance_cards_enabled: false
  };

  let resp, data;
  try {
    resp = await fetch('https://x.com' + path, {
      method: 'POST', headers, credentials: 'include',
      body: JSON.stringify({ variables, features, queryId })
    });
    data = await resp.json();
  } catch (e) {
    return { error: '请求失败', detail: String(e) };
  }
  if (!resp.ok) return { error: 'HTTP ' + resp.status, detail: JSON.stringify(data).slice(0, 400) };
  if (data.errors && data.errors.length) {
    return { error: 'x.com 拒绝', detail: data.errors.map(e => e.message).join(' | ').slice(0, 400) };
  }

  const res = data?.data?.create_tweet?.tweet_results?.result;
  const newId = res?.rest_id;
  const screen = res?.core?.user_results?.result?.legacy?.screen_name
              || res?.core?.user_results?.result?.core?.screen_name;
  return {
    ok: true,
    posted_id: newId || null,
    url: newId && screen ? ('https://x.com/' + screen + '/status/' + newId) : null,
    in_reply_to: id
  };
}
