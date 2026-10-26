'use strict';

/**
 * Dota 2 对黑助手 —— 录像上传 + 解析 + 自动发布服务
 *
 * 运行环境：CloudBase 云托管容器（Node.js 20 + Python 3 + tcb CLI）
 *
 * 接口：
 *   GET  /health
 *   POST /upload   分片上传（header 携带 uploadId / index / total / name / 口令）
 *   POST /parse    开始解析（JSON: {uploadId}）
 *   GET  /status   查询任务（?jobId=）
 *
 * 流程：分片落盘 → 合并校验 → parse → 校验练习赛 → 统计/生成网页
 *       → 上传 state 与 docs 到静态托管 → 删除录像
 */

const http = require('http');
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const ROOT = __dirname;
const JSON_DIR = path.join(ROOT, 'json');
const STATE_DIR = path.join(ROOT, 'state');
const DOCS_DIR = path.join(ROOT, 'docs');
const TMP_DIR = '/tmp/replay-uploads';
const CLOUD_STATE_DIR = '/tmp/cloud-state';
const TCB_HOME = '/tmp/tcb-home';

const MAX_FILE_BYTES = 300 * 1024 * 1024;
const MAX_CHUNK_BYTES = 8 * 1024 * 1024;
const MAX_CHUNKS = 100;
const MIN_DEM_BYTES = 5 * 1024 * 1024;
const UPLOAD_TTL_MS = 3 * 60 * 60 * 1000;
const JOB_TTL_MS = 2 * 60 * 60 * 1000;

let SECRETS = {};
try {
  SECRETS = JSON.parse(fs.readFileSync(path.join(ROOT, 'secrets.json'), 'utf8'));
} catch (err) {
  console.error('secrets.json 读取失败:', err.message);
}

const ENV_ID = SECRETS.envId || '';
const DOMAIN = SECRETS.domain || '';
const UPLOAD_CODE = String(SECRETS.uploadCode || '');
const API_KEY = SECRETS.apiKey || '';
const SERVICE_NAME = SECRETS.serviceName || 'dota-upload';
const PARSE_BIN = process.env.PARSE_BIN || path.join(ROOT, 'mantatool', 'parse');
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const SKIP_PUBLISH = process.env.SKIP_PUBLISH === '1';

const uploads = new Map(); // uploadId -> { dir, name, total, received:Set, createdAt }
const jobs = new Map(); // jobId -> job
const jobQueue = [];
let jobRunning = false;
let tcbLoggedIn = false;
let stateSynced = false;
let stateRemote = false;
let stateIncomplete = false;

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers': 'content-type,x-upload-code,x-upload-id,x-chunk-index,x-chunk-total,x-file-name',
  'Access-Control-Max-Age': '86400',
};

/* ------------------------------------------------------------------ */
/* 工具                                                                */
/* ------------------------------------------------------------------ */

function json(res, code, obj) {
  const body = Buffer.from(JSON.stringify(obj), 'utf8');
  res.writeHead(code, {
    ...CORS,
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': body.length,
    'Cache-Control': 'no-store',
  });
  res.end(body);
}

function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (buf) => {
      size += buf.length;
      if (size > limit) {
        reject(new Error('请求体过大'));
        req.destroy();
        return;
      }
      chunks.push(buf);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd: opts.cwd || ROOT,
      env: { ...process.env, HOME: TCB_HOME, ...(opts.env || {}) },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let out = '';
    let err = '';
    child.stdout.on('data', (d) => (out += d.toString()));
    child.stderr.on('data', (d) => (err += d.toString()));
    const timer = setTimeout(() => {
      try { child.kill('SIGKILL'); } catch (_) { /* ignore */ }
    }, opts.timeout || 120000);
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({ code, out, err });
    });
    child.on('error', (e) => {
      clearTimeout(timer);
      resolve({ code: -1, out, err: err + e.message });
    });
  });
}

function safeEqual(a, b) {
  const ba = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (ba.length !== bb.length) return false;
  return crypto.timingSafeEqual(ba, bb);
}

function checkCode(req) {
  if (!UPLOAD_CODE) return false;
  return safeEqual(req.headers['x-upload-code'] || '', UPLOAD_CODE);
}

function listMatchIds() {
  try {
    return fs.readdirSync(JSON_DIR)
      .filter((f) => /^match_\d+\.json$/.test(f))
      .map((f) => f.slice(6, -5))
      .sort();
  } catch (_) {
    return [];
  }
}

function sanitize(obj) {
  const copy = JSON.parse(JSON.stringify(obj));
  for (const p of copy.players || []) {
    delete p.steamid;
  }
  delete copy.steamid;
  return copy;
}

function loadIndex() {
  const file = path.join(STATE_DIR, 'index.json');
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (_) {
    return null;
  }
}

function writeIndex(ids) {
  const payload = {
    ids: [...ids].sort(),
    updates: { at: new Date().toISOString(), count: ids.length },
  };
  fs.mkdirSync(STATE_DIR, { recursive: true });
  fs.writeFileSync(path.join(STATE_DIR, 'index.json'), JSON.stringify(payload, null, 2));
}

function cleanupUploads() {
  const now = Date.now();
  for (const [id, u] of uploads) {
    if (now - u.createdAt > UPLOAD_TTL_MS) {
      fs.rm(u.dir, { recursive: true, force: true }, () => {});
      uploads.delete(id);
    }
  }
  for (const [id, j] of jobs) {
    if (now - j.createdAt > JOB_TTL_MS && j.state !== 'running' && j.state !== 'queued') {
      jobs.delete(id);
    }
  }
}

/* ------------------------------------------------------------------ */
/* tcb CLI / 云端状态                                                  */
/* ------------------------------------------------------------------ */

async function ensureLogin() {
  if (!API_KEY) return false;
  if (tcbLoggedIn) return true;
  fs.mkdirSync(TCB_HOME, { recursive: true });
  const r = await run('tcb', ['login', '--cloudbase-api-key', API_KEY, '-e', ENV_ID], { timeout: 90000 });
  if (r.code === 0) {
    tcbLoggedIn = true;
    return true;
  }
  console.error('tcb login 失败', r.code, r.out.slice(-400), r.err.slice(-400));
  return false;
}

/**
 * 首次启动时把自己的公网域名写进 cloudbase.json，
 * 这样服务端重新生成网页时「上传录像」Tab 仍指向正确的服务地址。
 */
async function ensureUploadEndpoint() {
  const cfgPath = path.join(ROOT, 'cloudbase.json');
  let cfg = {};
  try {
    cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
  } catch (_) {
    return;
  }
  if (cfg.upload_endpoint) return;
  const r = await run('tcb', ['cloudrun', 'detail', '-s', SERVICE_NAME, '-e', ENV_ID, '--json'], {
    timeout: 60000,
  });
  if (r.code !== 0) {
    console.error('获取服务域名失败:', (r.err || r.out).slice(-300));
    return;
  }
  try {
    const domain = JSON.parse(r.out).data.BaseInfo.DefaultDomainName;
    if (domain) {
      cfg.upload_endpoint = domain.replace(/\/$/, '');
      fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2) + '\n');
      console.log('上传服务地址已写入 cloudbase.json:', cfg.upload_endpoint);
    }
  } catch (err) {
    console.error('解析服务域名失败:', err.message);
  }
}

async function syncStateFromCloud() {
  if (stateSynced) return;
  stateSynced = true;
  if (!(await ensureLogin())) {
    console.error('未登录，跳过云端状态同步，仅使用镜像内置数据');
    return;
  }
  try {
    // 先下载到独立目录：云端为空时命令仍返回 0，必须检查实际文件
    fs.rmSync(CLOUD_STATE_DIR, { recursive: true, force: true });
    fs.mkdirSync(CLOUD_STATE_DIR, { recursive: true });
    const r = await run(
      'tcb',
      ['hosting', 'download', 'state', CLOUD_STATE_DIR, '--dir', '-e', ENV_ID],
      { timeout: 120000 }
    );
    if (r.code !== 0) {
      console.log('云端 state 下载失败，使用镜像内置数据:', r.err.slice(-300));
      return;
    }
    const files = fs.readdirSync(CLOUD_STATE_DIR).filter((f) => /^match_\d+\.json$/.test(f));
    if (!files.length) {
      console.log('云端 state 为空，使用镜像内置数据');
      return;
    }

    stateRemote = true;
    fs.mkdirSync(STATE_DIR, { recursive: true });
    fs.mkdirSync(JSON_DIR, { recursive: true });
    for (const f of files) {
      fs.copyFileSync(path.join(CLOUD_STATE_DIR, f), path.join(STATE_DIR, f));
      fs.copyFileSync(path.join(CLOUD_STATE_DIR, f), path.join(JSON_DIR, f));
    }
    const remoteIndex = path.join(CLOUD_STATE_DIR, 'index.json');
    if (fs.existsSync(remoteIndex)) {
      fs.copyFileSync(remoteIndex, path.join(STATE_DIR, 'index.json'));
    }

    // 索引按合并后的本地集合重建（本地镜像可能比云端新）
    const ids = listMatchIds();
    writeIndex(ids);

    const index = loadIndex();
    if (index && Array.isArray(index.ids)) {
      const local = new Set(ids);
      const missing = index.ids.filter((id) => !local.has(String(id)));
      if (missing.length) {
        // 云端记录了本地没有的比赛：禁止用不完整数据覆盖线上
        stateIncomplete = true;
        console.error('云端 state 有本地缺失的比赛:', missing.join(','));
      }
    }
    console.log(`state 已合并：云端 ${files.length} 场，本地共 ${ids.length} 场`);
  } catch (err) {
    console.error('state 同步异常:', err.message);
  }
}

async function publishState() {
  const r = await run('tcb', ['hosting', 'deploy', 'state', 'state', '-e', ENV_ID], { timeout: 180000 });
  if (r.code !== 0) throw new Error('上传 state 失败: ' + (r.err || r.out).slice(-400));
}

async function remoteMatchCount() {
  if (!DOMAIN) return null;
  try {
    const url = DOMAIN.replace(/\/?$/, '/') + 'index.html?ts=' + Date.now();
    const res = await fetch(url, { headers: { 'Cache-Control': 'no-cache' } });
    if (!res.ok) return null;
    const text = await res.text();
    const m = text.match(/const MATCH_COUNT = (\d+)/);
    return m ? Number(m[1]) : null;
  } catch (err) {
    console.error('读取线上比赛数失败:', err.message);
    return null;
  }
}

async function publishDocs() {
  const r = await run(
    'tcb',
    ['hosting', 'deploy', 'docs', '-e', ENV_ID, '--entry', 'index.html', '--verify'],
    { timeout: 300000 }
  );
  if (r.code !== 0) throw new Error('发布网页失败: ' + (r.err || r.out).slice(-400));
}

/* ------------------------------------------------------------------ */
/* 解析流水线                                                          */
/* ------------------------------------------------------------------ */

function createJob(uploadId) {
  const job = {
    id: crypto.randomBytes(9).toString('hex'),
    uploadId,
    state: 'queued',
    stage: '排队中',
    message: '',
    createdAt: Date.now(),
    result: null,
  };
  jobs.set(job.id, job);
  jobQueue.push(job);
  setImmediate(runQueue);
  return job;
}

async function runQueue() {
  if (jobRunning) return;
  const job = jobQueue.shift();
  if (!job) return;
  jobRunning = true;
  job.state = 'running';
  try {
    await processJob(job);
  } catch (err) {
    job.state = 'error';
    job.message = err.message || String(err);
    console.error('任务失败', job.id, err);
  } finally {
    jobRunning = false;
    setImmediate(runQueue);
  }
}

function stage(job, text) {
  job.stage = text;
  console.log(`[${job.id}] ${text}`);
}

async function processJob(job) {
  const upload = uploads.get(job.uploadId);
  if (!upload) throw new Error('上传任务不存在或已过期');

  await syncStateFromCloud();
  if (stateIncomplete) {
    throw new Error('云端比赛数据与本地不一致，已拒绝发布会话；请升级服务镜像后重试');
  }

  const matchId = upload.name.replace(/\.dem$/i, '');
  const demPath = path.join(upload.dir, 'upload.dem');

  // 按比赛 ID 去重：已解析过的直接跳过（不重复解析、不重复发布）
  if (listMatchIds().includes(matchId)) {
    fs.rm(upload.dir, { recursive: true, force: true }, () => {});
    uploads.delete(job.uploadId);
    job.state = 'done';
    job.stage = '已存在，跳过';
    job.result = {
      matchId,
      skipped: true,
      matchCount: listMatchIds().length,
      url: DOMAIN,
      page: DOMAIN ? DOMAIN.replace(/\/?$/, '/') + '?v=' + Date.now() : '',
    };
    job.message = `比赛 ${matchId} 已存在（按 ID 去重），已跳过`;
    return;
  }

  stage(job, '合并分片');
  const out = fs.createWriteStream(demPath);
  for (let i = 0; i < upload.total; i++) {
    const chunk = await fsp.readFile(path.join(upload.dir, `chunk_${i}.bin`));
    if (!out.write(chunk)) {
      await new Promise((r) => out.once('drain', r));
    }
  }
  await new Promise((resolve, reject) => {
    out.end((err) => (err ? reject(err) : resolve()));
  });

  const stat = await fsp.stat(demPath);
  if (stat.size < MIN_DEM_BYTES) throw new Error('录像文件太小，可能上传不完整');
  if (stat.size > MAX_FILE_BYTES) throw new Error('录像文件超过大小限制');
  const head = Buffer.alloc(8);
  const fd = await fsp.open(demPath, 'r');
  await fd.read(head, 0, 8, 0);
  await fd.close();
  if (head.toString('latin1') !== 'PBDEMS2\0') {
    throw new Error('不是有效的 Dota 2 录像（PBDEMS2）');
  }

  stage(job, '解析录像（约 10–30 秒）');
  const jsonPath = path.join(JSON_DIR, `match_${matchId}.json`);
  try { fs.unlinkSync(jsonPath); } catch (_) { /* ignore */ }
  const parsed = await run(
    PARSE_BIN,
    ['--out', JSON_DIR, '--no-raw', demPath],
    { timeout: 300000 }
  );
  if (parsed.code !== 0 || !fs.existsSync(jsonPath)) {
    // 解析失败可能留下残缺文件，必须清掉，避免混进下一次发布
    try { fs.unlinkSync(jsonPath); } catch (_) { /* ignore */ }
    throw new Error('解析失败: ' + (parsed.out || parsed.err || '').slice(-400));
  }

  const data = JSON.parse(await fsp.readFile(jsonPath, 'utf8'));
  const lobby = data.lobby_type;
  const players = (data.players || []).length;
  const duration = data.duration || 0;
  if (lobby !== 1 || players !== 10 || duration <= 0) {
    // 非练习赛：删除解析结果，确保不会在后续发布中被带进统计
    try { fs.unlinkSync(jsonPath); } catch (_) { /* ignore */ }
    throw new Error(`不是有效的练习赛（lobby_type=${lobby}, players=${players}, duration=${duration}）`);
  }

  stage(job, '写入比赛数据');
  const clean = sanitize(data);
  fs.mkdirSync(STATE_DIR, { recursive: true });
  await fsp.writeFile(path.join(STATE_DIR, `match_${matchId}.json`), JSON.stringify(clean));
  const ids = listMatchIds();
  if (!ids.includes(String(matchId))) ids.push(String(matchId));
  writeIndex(ids);

  stage(job, '重新生成统计与网页');
  for (const script of ['stats.py', 'make_web.py']) {
    const r = await run(PYTHON_BIN, [path.join(ROOT, script)], { timeout: 180000 });
    if (r.code !== 0) {
      throw new Error(`${script} 失败: ` + (r.err || r.out).slice(-400));
    }
  }

  const dataFile = path.join(DOCS_DIR, 'data', 'matches.js');
  const dataText = await fsp.readFile(dataFile, 'utf8');
  if (/steamid/i.test(dataText) || /7656119\d{10}/.test(dataText)) {
    throw new Error('发布产物包含 SteamID，已终止');
  }

  if (!SKIP_PUBLISH) {
    const localCount = listMatchIds().length;
    const remoteCount = await remoteMatchCount();
    if (remoteCount !== null && remoteCount > localCount) {
      throw new Error(
        `线上已有 ${remoteCount} 场，本地只有 ${localCount} 场，已拒绝发布（避免数据回退）`
      );
    }

    stage(job, '上传比赛数据');
    if (!(await ensureLogin())) throw new Error('CloudBase 登录失败，无法自动发布');
    await publishState();

    stage(job, '发布网页');
    await publishDocs();
  } else {
    stage(job, '已跳过发布（本地测试）');
  }

  // 清理
  fs.rm(upload.dir, { recursive: true, force: true }, () => {});
  uploads.delete(job.uploadId);

  const matchCount = listMatchIds().length;
  job.state = 'done';
  job.stage = '完成';
  job.result = {
    matchId,
    duration,
    players,
    matchCount,
    winner: data.radiant_win ? 'radiant' : 'dire',
    url: DOMAIN,
    page: DOMAIN ? DOMAIN.replace(/\/?$/, '/') + '?v=' + Date.now() : '',
  };
  job.message = `已解析并发布：比赛 ${matchId}，当前共 ${matchCount} 场`;
}

/* ------------------------------------------------------------------ */
/* HTTP 路由                                                           */
/* ------------------------------------------------------------------ */

async function handleUpload(req, res) {
  if (!checkCode(req)) return json(res, 401, { error: '口令错误' });
  if (stateIncomplete) return json(res, 503, { error: '服务状态未就绪，请稍后重试' });

  const uploadId = String(req.headers['x-upload-id'] || '');
  const index = Number(req.headers['x-chunk-index']);
  const total = Number(req.headers['x-chunk-total']);
  const name = String(req.headers['x-file-name'] || '');

  if (!/^[a-f0-9]{16,40}$/i.test(uploadId)) return json(res, 400, { error: 'uploadId 无效' });
  if (!Number.isInteger(index) || !Number.isInteger(total) || total < 1 || total > MAX_CHUNKS) {
    return json(res, 400, { error: '分片参数无效' });
  }
  if (index < 0 || index >= total) return json(res, 400, { error: '分片序号无效' });
  if (!/^\d{7,12}\.dem$/i.test(name)) {
    return json(res, 400, { error: '文件名必须是比赛 ID，例如 9061520546.dem' });
  }

  // 第一片就检查 ID 是否已存在，避免白传 100MB
  if (index === 0 && !uploads.has(uploadId)) {
    const matchId = name.replace(/\.dem$/i, '');
    if (listMatchIds().includes(matchId)) {
      return json(res, 409, {
        error: `比赛 ${matchId} 已存在（按 ID 去重），无需重复上传`,
        code: 'EXISTS',
      });
    }
  }

  const body = await readBody(req, MAX_CHUNK_BYTES);
  if (!body.length) return json(res, 400, { error: '分片为空' });

  let upload = uploads.get(uploadId);
  if (!upload) {
    const dir = path.join(TMP_DIR, uploadId);
    await fsp.mkdir(dir, { recursive: true });
    upload = { dir, name, total, received: new Set(), createdAt: Date.now() };
    uploads.set(uploadId, upload);
  }
  if (upload.name !== name || upload.total !== total) {
    return json(res, 409, { error: '上传参数不一致' });
  }

  await fsp.writeFile(path.join(upload.dir, `chunk_${index}.bin`), body);
  upload.received.add(index);

  return json(res, 200, {
    received: upload.received.size,
    total,
    complete: upload.received.size === total,
  });
}

async function handleParse(req, res) {
  if (!checkCode(req)) return json(res, 401, { error: '口令错误' });
  const body = await readBody(req, 64 * 1024);
  let payload = {};
  try {
    payload = JSON.parse(body.toString('utf8') || '{}');
  } catch (_) {
    return json(res, 400, { error: '请求格式错误' });
  }
  const uploadId = String(payload.uploadId || '');
  const upload = uploads.get(uploadId);
  if (!upload) return json(res, 404, { error: '上传任务不存在或已过期' });
  if (upload.received.size !== upload.total) {
    return json(res, 400, { error: `分片未上传完整（${upload.received.size}/${upload.total}）` });
  }

  const job = createJob(uploadId);
  return json(res, 202, { jobId: job.id });
}

async function handleCheck(req, res) {
  if (!checkCode(req)) return json(res, 401, { error: '口令错误' });
  const body = await readBody(req, 64 * 1024);
  let payload = {};
  try {
    payload = JSON.parse(body.toString('utf8') || '{}');
  } catch (_) {
    return json(res, 400, { error: '请求格式错误' });
  }
  const matchId = String(payload.matchId || '');
  if (!/^\d{7,12}$/.test(matchId)) return json(res, 400, { error: '比赛 ID 无效' });
  const ids = listMatchIds();
  return json(res, 200, { exists: ids.includes(matchId), matchCount: ids.length });
}

async function handleCancel(req, res) {
  if (!checkCode(req)) return json(res, 401, { error: '口令错误' });
  const body = await readBody(req, 64 * 1024);
  let payload = {};
  try {
    payload = JSON.parse(body.toString('utf8') || '{}');
  } catch (_) {
    return json(res, 400, { error: '请求格式错误' });
  }
  const uploadId = String(payload.uploadId || '');
  const running = [...jobs.values()].find(
    (j) => j.uploadId === uploadId && (j.state === 'running' || j.state === 'queued')
  );
  if (running) return json(res, 409, { error: '已开始解析，无法取消' });
  const upload = uploads.get(uploadId);
  if (!upload) return json(res, 200, { ok: true });
  fs.rm(upload.dir, { recursive: true, force: true }, () => {});
  uploads.delete(uploadId);
  return json(res, 200, { ok: true });
}

function handleStatus(res, url) {
  const jobId = url.searchParams.get('jobId') || '';
  const job = jobs.get(jobId);
  if (!job) return json(res, 404, { error: '任务不存在' });
  return json(res, 200, {
    state: job.state,
    stage: job.stage,
    message: job.message,
    result: job.result,
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');

  if (req.method === 'OPTIONS') {
    res.writeHead(204, CORS);
    return res.end();
  }

  try {
    if (req.method === 'GET' && url.pathname === '/health') {
      return json(res, 200, {
        ok: true,
        matches: listMatchIds().length,
        maxBytes: MAX_FILE_BYTES,
        chunkBytes: MAX_CHUNK_BYTES,
        state: { remote: stateRemote, incomplete: stateIncomplete },
        env: ENV_ID,
      });
    }
    if (req.method === 'POST' && url.pathname === '/upload') {
      return await handleUpload(req, res);
    }
    if (req.method === 'POST' && url.pathname === '/parse') {
      return await handleParse(req, res);
    }
    if (req.method === 'POST' && url.pathname === '/check') {
      return await handleCheck(req, res);
    }
    if (req.method === 'POST' && url.pathname === '/cancel') {
      return await handleCancel(req, res);
    }
    if (req.method === 'GET' && url.pathname === '/status') {
      return handleStatus(res, url);
    }
    return json(res, 404, { error: 'not found' });
  } catch (err) {
    console.error('请求处理失败', err);
    return json(res, 500, { error: err.message || '内部错误' });
  }
});

setInterval(cleanupUploads, 10 * 60 * 1000).unref();

const PORT = Number(process.env.PORT || 8080);
server.listen(PORT, '0.0.0.0', async () => {
  console.log(`upload service listening on ${PORT}`);
  if (!UPLOAD_CODE) console.error('警告：未配置上传口令');
  if (!API_KEY) console.error('警告：未配置 CloudBase API Key，自动发布不可用');
  try {
    await ensureLogin();
    await ensureUploadEndpoint();
    await syncStateFromCloud();
  } catch (err) {
    console.error('启动初始化失败:', err.message);
  }
});
