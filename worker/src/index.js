// DailyNews tap receiver + scheduler (Cloudflare Worker).
//
//   POST /telegram   Telegram webhook. Answers 👍/👎 taps instantly (popup + ✓ button)
//                    and stores them in KV for the pipeline.
//   GET  /taps       Pipeline pulls stored taps (Bearer PULL_TOKEN).
//   POST /taps/ack   Pipeline deletes taps it recorded (only if unchanged since the pull).
//   GET  /health     Liveness + config check (no secrets revealed).
//   cron             Dispatches the GitHub workflow hourly (GitHub's own schedule runs late).
//
// Secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_SECRET, PULL_TOKEN, GITHUB_TOKEN
// Vars:    GITHUB_REPO ("owner/repo"), GITHUB_WORKFLOW ("dailynews.yml"), GITHUB_REF ("main")
// KV:      TAPS

const TAP_RE = /^fb:(\d+):(-?1)$/;
const PREFIX = "tap:";

export function buttons(itemId, selected) {
  return {
    inline_keyboard: [[
      { text: selected === 1 ? "👍 ✓" : "👍", callback_data: `fb:${itemId}:1` },
      { text: selected === -1 ? "👎 ✓" : "👎", callback_data: `fb:${itemId}:-1` },
    ]],
  };
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

// Constant-time comparison so secrets can't be guessed byte by byte from response timing.
function safeEqual(a, b) {
  a = String(a ?? ""); b = String(b ?? "");
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0 && a.length > 0;
}

async function tg(env, method, params) {
  const resp = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(params),
  });
  const data = await resp.json().catch(() => ({}));
  if (!data.ok) console.log(`telegram ${method} failed: ${resp.status} ${data.description || ""}`);
  return data;
}

export async function handleTelegram(request, env) {
  if (!safeEqual(request.headers.get("x-telegram-bot-api-secret-token"), env.WEBHOOK_SECRET)) {
    return new Response("forbidden", { status: 403 });
  }
  let update;
  try { update = await request.json(); } catch { return new Response("ok"); }   // never make Telegram retry junk

  const cq = update.callback_query;
  if (!cq) return new Response("ok");   // plain messages etc. are ignored

  const chatId = String(cq.message?.chat?.id ?? "");
  const m = TAP_RE.exec(cq.data || "");
  if (chatId !== String(env.TELEGRAM_CHAT_ID).trim() || !m) {
    await tg(env, "answerCallbackQuery", { callback_query_id: cq.id });   // stop the spinner, record nothing
    return new Response("ok");
  }

  const itemId = Number(m[1]);
  const label = Number(m[2]);
  // Latest tap per item wins, matching the pipeline's semantics.
  await env.TAPS.put(PREFIX + itemId, JSON.stringify({ item_id: itemId, label, at: new Date().toISOString() }));

  await Promise.all([
    tg(env, "answerCallbackQuery", { callback_query_id: cq.id, text: label === 1 ? "Saved 👍" : "Saved 👎" }),
    cq.message?.message_id
      ? tg(env, "editMessageReplyMarkup", {
          chat_id: chatId, message_id: cq.message.message_id, reply_markup: buttons(itemId, label),
        })
      : null,
  ]);
  return new Response("ok");
}

function authorized(request, env) {
  const h = request.headers.get("authorization") || "";
  return safeEqual(h.replace(/^Bearer\s+/i, ""), env.PULL_TOKEN);
}

export async function listTaps(env) {
  const taps = [];
  let cursor;
  do {
    const page = await env.TAPS.list({ prefix: PREFIX, cursor });
    for (const k of page.keys) {
      const v = await env.TAPS.get(k.name);
      if (v) taps.push(JSON.parse(v));
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return taps;
}

export async function ackTaps(env, acks) {
  let deleted = 0;
  for (const { item_id, at } of acks || []) {
    const key = PREFIX + Number(item_id);
    const cur = await env.TAPS.get(key);
    // Only delete what the pipeline actually recorded; a newer tap made in between survives.
    if (cur && JSON.parse(cur).at === at) {
      await env.TAPS.delete(key);
      deleted++;
    }
  }
  return deleted;
}

export async function dispatchWorkflow(env) {
  const [owner, repo] = String(env.GITHUB_REPO || "").split("/");
  const url = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${env.GITHUB_WORKFLOW || "dailynews.yml"}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "user-agent": "dailynews-worker",
      "content-type": "application/json",
    },
    body: JSON.stringify({ ref: env.GITHUB_REF || "main" }),
  });
  if (resp.status !== 204) {
    const text = await resp.text().catch(() => "");
    throw new Error(`workflow dispatch failed: ${resp.status} ${text.slice(0, 200)}`);
  }
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (request.method === "POST" && pathname === "/telegram") return handleTelegram(request, env);
    if (request.method === "GET" && pathname === "/taps") {
      if (!authorized(request, env)) return new Response("unauthorized", { status: 401 });
      return json({ taps: await listTaps(env) });
    }
    if (request.method === "POST" && pathname === "/taps/ack") {
      if (!authorized(request, env)) return new Response("unauthorized", { status: 401 });
      const body = await request.json().catch(() => ({}));
      return json({ deleted: await ackTaps(env, body.acks) });
    }
    if (request.method === "GET" && pathname === "/health") {
      const missing = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "WEBHOOK_SECRET", "PULL_TOKEN", "GITHUB_TOKEN"]
        .filter((k) => !env[k]);
      return json({ ok: missing.length === 0 && !!env.TAPS, missing, kv: !!env.TAPS });
    }
    return new Response("not found", { status: 404 });
  },

  async scheduled(_event, env, ctx) {
    ctx.waitUntil(dispatchWorkflow(env));
  },
};
