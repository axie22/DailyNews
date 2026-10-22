import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import worker, { ackTaps, listTaps } from "../src/index.js";

class FakeKV {
  constructor() { this.m = new Map(); }
  async get(k) { return this.m.has(k) ? this.m.get(k) : null; }
  async put(k, v) { this.m.set(k, v); }
  async delete(k) { this.m.delete(k); }
  async list({ prefix, cursor }) {
    const keys = [...this.m.keys()].filter((k) => k.startsWith(prefix)).sort();
    const start = cursor ? Number(cursor) : 0, page = keys.slice(start, start + 2);   // tiny pages: exercise paging
    const done = start + 2 >= keys.length;
    return { keys: page.map((name) => ({ name })), list_complete: done, cursor: done ? undefined : String(start + 2) };
  }
}

let env, calls;
beforeEach(() => {
  calls = [];
  env = { TELEGRAM_BOT_TOKEN: "BOT", TELEGRAM_CHAT_ID: "42\n", WEBHOOK_SECRET: "hook", PULL_TOKEN: "pull",
          GITHUB_TOKEN: "gh", GITHUB_REPO: "axie22/DailyNews", GITHUB_WORKFLOW: "dailynews.yml", GITHUB_REF: "main",
          TAPS: new FakeKV() };
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), body: init.body ? JSON.parse(init.body) : null, headers: init.headers });
    if (String(url).includes("api.github.com")) return new Response(null, { status: 204 });
    return new Response(JSON.stringify({ ok: true, result: true }), { headers: { "content-type": "application/json" } });
  };
});

const tapUpdate = (data, chat = 42, msg = 7) => ({ update_id: 1, callback_query: { id: "cq1", data,
  message: { message_id: msg, chat: { id: chat } } } });
const hook = (body, secret = "hook") => new Request("https://w.dev/telegram", { method: "POST",
  headers: { "x-telegram-bot-api-secret-token": secret, "content-type": "application/json" }, body: JSON.stringify(body) });
const get = (path, token = "pull") => new Request("https://w.dev" + path, { headers: { authorization: `Bearer ${token}` } });
const post = (path, body, token = "pull") => new Request("https://w.dev" + path, { method: "POST",
  headers: { authorization: `Bearer ${token}`, "content-type": "application/json" }, body: JSON.stringify(body) });

test("a tap is answered instantly, the button gets a check, and the tap is stored", async () => {
  const r = await worker.fetch(hook(tapUpdate("fb:123:1")), env);
  assert.equal(r.status, 200);
  const methods = calls.map((c) => c.url.split("/").pop());
  assert.deepEqual(methods.sort(), ["answerCallbackQuery", "editMessageReplyMarkup"]);
  const answer = calls.find((c) => c.url.endsWith("answerCallbackQuery")).body;
  assert.equal(answer.text, "Saved 👍");
  const edit = calls.find((c) => c.url.endsWith("editMessageReplyMarkup")).body;
  assert.equal(edit.message_id, 7);
  assert.equal(edit.reply_markup.inline_keyboard[0][0].text, "👍 ✓");
  assert.equal(edit.reply_markup.inline_keyboard[0][1].text, "👎");
  const taps = await listTaps(env);
  assert.equal(taps.length, 1);
  assert.equal(taps[0].item_id, 123);
  assert.equal(taps[0].label, 1);
});

test("changing your mind keeps only the latest tap", async () => {
  await worker.fetch(hook(tapUpdate("fb:5:1")), env);
  await worker.fetch(hook(tapUpdate("fb:5:-1")), env);
  const taps = await listTaps(env);
  assert.deepEqual(taps.map((t) => [t.item_id, t.label]), [[5, -1]]);
});

test("requests without the webhook secret are rejected and nothing is stored", async () => {
  const r = await worker.fetch(hook(tapUpdate("fb:1:1"), "wrong"), env);
  assert.equal(r.status, 403);
  assert.equal(calls.length, 0);
  assert.equal((await listTaps(env)).length, 0);
});

test("taps from another chat or with junk data stop the spinner but store nothing", async () => {
  await worker.fetch(hook(tapUpdate("fb:1:1", 999)), env);
  await worker.fetch(hook(tapUpdate("hello")), env);
  assert.equal((await listTaps(env)).length, 0);
  assert.deepEqual(calls.map((c) => c.url.split("/").pop()), ["answerCallbackQuery", "answerCallbackQuery"]);
});

test("non-tap updates and malformed bodies get 200 so Telegram doesn't retry", async () => {
  assert.equal((await worker.fetch(hook({ update_id: 2, message: { text: "hi" } }), env)).status, 200);
  const bad = new Request("https://w.dev/telegram", { method: "POST",
    headers: { "x-telegram-bot-api-secret-token": "hook" }, body: "{not json" });
  assert.equal((await worker.fetch(bad, env)).status, 200);
});

test("pull requires the token and pages through all taps", async () => {
  for (const id of [1, 2, 3, 4, 5]) await worker.fetch(hook(tapUpdate(`fb:${id}:1`)), env);
  assert.equal((await worker.fetch(get("/taps", "nope"), env)).status, 401);
  const r = await worker.fetch(get("/taps"), env);
  const { taps } = await r.json();
  assert.deepEqual(taps.map((t) => t.item_id).sort(), [1, 2, 3, 4, 5]);
});

test("ack deletes recorded taps but keeps one re-tapped after the pull", async () => {
  await worker.fetch(hook(tapUpdate("fb:1:1")), env);
  await worker.fetch(hook(tapUpdate("fb:2:1")), env);
  const { taps } = await (await worker.fetch(get("/taps"), env)).json();
  await new Promise((r) => setTimeout(r, 5));
  await worker.fetch(hook(tapUpdate("fb:2:-1")), env);          // changed mind while the pipeline ran
  const r = await worker.fetch(post("/taps/ack", { acks: taps.map(({ item_id, at }) => ({ item_id, at })) }), env);
  assert.deepEqual(await r.json(), { deleted: 1 });
  assert.deepEqual((await listTaps(env)).map((t) => [t.item_id, t.label]), [[2, -1]]);
  assert.equal((await worker.fetch(post("/taps/ack", { acks: [] }, "nope"), env)).status, 401);
});

test("cron dispatches the GitHub workflow on main", async () => {
  const waits = [];
  await worker.scheduled({}, env, { waitUntil: (p) => waits.push(p) });
  await Promise.all(waits);
  const c = calls[0];
  assert.equal(c.url, "https://api.github.com/repos/axie22/DailyNews/actions/workflows/dailynews.yml/dispatches");
  assert.deepEqual(c.body, { ref: "main" });
  assert.equal(c.headers.authorization, "Bearer gh");
});

test("a failed dispatch surfaces as an error (visible in Worker logs)", async () => {
  globalThis.fetch = async () => new Response("Bad credentials", { status: 401 });
  const waits = [];
  await worker.scheduled({}, env, { waitUntil: (p) => waits.push(p) });
  await assert.rejects(Promise.all(waits), /401/);
});

test("health reports missing config without revealing secrets", async () => {
  delete env.GITHUB_TOKEN;
  const body = await (await worker.fetch(new Request("https://w.dev/health"), env)).json();
  assert.deepEqual(body, { ok: false, missing: ["GITHUB_TOKEN"], kv: true });
});
