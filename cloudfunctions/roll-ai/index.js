'use strict';

const http = require('http');

const DEEPSEEK_URL = 'https://api.deepseek.com/anthropic/v1/messages';
const MODEL = process.env.DEEPSEEK_MODEL || 'deepseek-flash';
const MAX_BODY = 64 * 1024;
const MAX_MESSAGES = 24;
const RATE_LIMIT = 10;
const RATE_WINDOW_MS = 60 * 1000;
const hits = new Map();

// CORS 由 CloudBase HTTP 网关统一注入；函数不要再返回 *，否则会重复。
const CORS_HEADERS = {
  'Content-Type': 'application/json; charset=utf-8'
};

const DISPLAY_MATCH_TOOL = {
  name: 'display_match',
  description:
    '展示一套 5v5 对黑阵容卡片。只有在已经确定或建议一套具体阵容时调用；' +
    '调用前先用文字说明调整思路。',
  input_schema: {
    type: 'object',
    properties: {
      team_a: {
        type: 'array', items: { type: 'string' },
        minItems: 5, maxItems: 5,
        description: '队伍 A 的 5 个玩家名，必须来自给定的 10 人名单'
      },
      team_b: {
        type: 'array', items: { type: 'string' },
        minItems: 5, maxItems: 5,
        description: '队伍 B 的 5 个玩家名，必须来自给定的 10 人名单'
      },
      reason: { type: 'string', description: '这套阵容的调整理由，中文' }
    },
    required: ['team_a', 'team_b', 'reason']
  }
};

function send(res, status, body) {
  res.writeHead(status, CORS_HEADERS);
  res.end(JSON.stringify(body));
}

function clientIp(req) {
  const xff = req.headers['x-forwarded-for'];
  if (xff) return String(xff).split(',')[0].trim();
  return req.headers['x-real-ip'] || (req.socket && req.socket.remoteAddress) || 'unknown';
}

function rateLimited(ip) {
  const now = Date.now();
  const list = (hits.get(ip) || []).filter(t => now - t < RATE_WINDOW_MS);
  if (list.length >= RATE_LIMIT) {
    hits.set(ip, list);
    return true;
  }
  list.push(now);
  hits.set(ip, list);
  if (hits.size > 5000) hits.clear();
  return false;
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', chunk => {
      size += chunk.length;
      if (size > MAX_BODY) {
        reject(new Error('body too large'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

function buildSystem(context) {
  const players = (context.players || []).map(p =>
    `- ${p.name} | 评分 ${p.rating} | ${p.role} | KDA ${p.kda} | GPM ${p.gpm} | XPM ${p.xpm} | MMR ${p.mmr}`
  ).join('\n');

  const lineups = (context.lineups || []).map((l, i) =>
    `方案${i + 1}: A[${l.team_a.join('、')}] vs B[${l.team_b.join('、')}]` +
    ` | 预测胜率 ${(l.pa * 100).toFixed(1)}% | 平衡分 ${Number(l.score).toFixed(1)}`
  ).join('\n');

  const adopted = context.adopted
    ? `\n当前已采用方案：A[${context.adopted.team_a.join('、')}] vs B[${context.adopted.team_b.join('、')}]`
    : '';

  return [
    '你是 Dota 2 对黑匹配助手，用中文和用户交流。',
    '目标：在用户已经 roll 出的阵容基础上，通过对话微调出更合理的 5v5 分队。',
    '',
    '【玩家池（只能使用这些人，禁止编造或替换成其他人）】',
    players,
    '',
    '【当前 3 套方案】',
    lineups || '（无）',
    adopted,
    '',
    '【分队规则】',
    '1. 每队正好 5 人，两队共 10 人，且必须正好覆盖给定的 10 人。',
    '2. 两队核心数差尽量 ≤ 1。',
    '3. 预测胜率尽量落在 45%–55%，平衡分越高越好。',
    '4. 综合分前 2 名尽量不要在同一队。',
    '5. 只能调整已选的 10 人，不要建议换人。',
    '',
    '【工具】',
    '当用户要求给出、调整或重新生成阵容时，必须调用 display_match 展示，不要只在文字里列名单。',
    '如果用户只是提问或讨论，不要调用工具，直接用文字回答。',
    '不要重复展示完全相同的阵容。'
  ].join('\n');
}

function deepSeekBody(system, messages, stream) {
  return {
    model: MODEL,
    max_tokens: 3000,
    temperature: 0.5,
    system,
    messages,
    tools: [DISPLAY_MATCH_TOOL],
    stream: !!stream
  };
}

async function callDeepSeek(key, system, messages) {
  const resp = await fetch(DEEPSEEK_URL, {
    method: 'POST',
    headers: {
      'x-api-key': key,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json'
    },
    body: JSON.stringify(deepSeekBody(system, messages, false))
  });
  const data = await resp.json().catch(() => null);
  if (!resp.ok) {
    const msg = (data && data.error && (data.error.message || data.error.type)) ||
      `AI 服务错误 ${resp.status}`;
    const err = new Error(String(msg).slice(0, 300));
    err.status = 502;
    throw err;
  }
  return data || {};
}

async function streamDeepSeek(res, key, system, messages) {
  const upstream = await fetch(DEEPSEEK_URL, {
    method: 'POST',
    headers: {
      'x-api-key': key,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json'
    },
    body: JSON.stringify(deepSeekBody(system, messages, true))
  });

  if (!upstream.ok) {
    const data = await upstream.json().catch(() => null);
    const msg = (data && data.error && (data.error.message || data.error.type)) ||
      `AI 服务错误 ${upstream.status}`;
    send(res, 502, { error: String(msg).slice(0, 300) });
    return;
  }

  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no'
  });
  if (typeof res.flushHeaders === 'function') res.flushHeaders();

  const reader = upstream.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      res.write(Buffer.from(value));
    }
  } catch (e) {
    try {
      res.write(`event: error\ndata: ${JSON.stringify({ error: '流式响应中断' })}\n\n`);
    } catch (_) {}
  } finally {
    res.end();
  }
}

async function handle(req, res) {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, CORS_HEADERS);
    res.end();
    return;
  }
  if (req.method !== 'POST') {
    send(res, 405, { error: '只支持 POST' });
    return;
  }

  const key = process.env.DEEPSEEK_API_KEY;
  if (!key) {
    send(res, 500, { error: 'AI 服务未配置 DEEPSEEK_API_KEY' });
    return;
  }
  if (rateLimited(clientIp(req))) {
    send(res, 429, { error: '请求过于频繁，请稍后再试' });
    return;
  }

  let payload;
  try {
    const raw = await readBody(req);
    payload = JSON.parse(raw);
  } catch (e) {
    send(res, e.message === 'body too large' ? 413 : 400,
      { error: e.message === 'body too large' ? '请求内容过大' : '请求 JSON 无效' });
    return;
  }

  const messages = payload && payload.messages;
  const context = (payload && payload.context) || {};
  if (!Array.isArray(messages) || messages.length === 0) {
    send(res, 400, { error: '缺少 messages' });
    return;
  }
  if (messages.length > MAX_MESSAGES) {
    send(res, 413, { error: '对话过长，请重新开始' });
    return;
  }

  try {
    if (payload.stream) {
      await streamDeepSeek(res, key, buildSystem(context), messages);
      return;
    }
    const data = await callDeepSeek(key, buildSystem(context), messages);
    send(res, 200, {
      content: data.content || [],
      stop_reason: data.stop_reason || null
    });
  } catch (e) {
    send(res, e.status || 502, { error: e.message || 'AI 服务错误' });
  }
}

const server = http.createServer((req, res) => {
  handle(req, res).catch(() => {
    try { send(res, 500, { error: '内部错误' }); } catch (_) {}
  });
});

const port = Number(process.env.PORT) || 9000;
server.listen(port, () => {
  console.log(`roll-ai listening on ${port}`);
});

module.exports = { handle };
