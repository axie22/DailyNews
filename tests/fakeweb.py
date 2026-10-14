"""A fake internet for offline tests: feeds, HF, arXiv, Anthropic, Jev and Telegram."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import httpx


def rfc822(dt: datetime) -> str:
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


class FakeWeb:
    def __init__(self, now: datetime):
        self.now = now
        self.jev_mode = "ok"          # ok | auth | down | flaky
        self.jev_calls = 0
        self.jev_states: list[str] = []
        self.tg_sent: list[dict] = []
        self.tg_edits: list[dict] = []
        self.tg_answered: list[str] = []
        self.tg_updates: list[dict] = []
        self.next_msg_id = 100
        self.requests: list[str] = []
        self.openai_items = [
            ("Introducing GPT-7", "https://openai.com/index/gpt-7", "Today we are releasing GPT-7, a new model.", 2),
            ("Customer story: Acme uses ChatGPT", "https://openai.com/index/acme", "Acme rolled out ChatGPT.", 30),
        ]
        self.anthropic_html = """<html><body>
          <a href="/news/claude-5-release"><h3>Claude 5 is here</h3><span>Announcements</span><span>Oct 14, 2026</span></a>
          <a href="/news/singapore-office">Announcements Oct 1, 2026 Anthropic opens Singapore office</a>
          <a href="/careers">Careers</a></body></html>"""

    # ── fixtures ──
    def rss(self) -> str:
        items = "".join(
            f"<item><title>{t}</title><link>{u}</link><description>{d}</description>"
            f"<pubDate>{rfc822(self.now - timedelta(hours=h))}</pubDate></item>"
            for t, u, d, h in self.openai_items)
        return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{items}</channel></rss>'

    def arxiv(self) -> str:
        entries = []
        papers = [
            ("2610.00001", "Sparse Autoencoders Reveal Deceptive Features in Language Models",
             "We use interpretability tools to study alignment and deception in LLMs."),
            ("2610.00002", "FlashDecode-3: Faster KV Cache Inference Kernels",
             "We present new kernels for LLM inference and serving with quantization."),
            ("2610.00003", "A Survey of Crop Yield Prediction", "We survey agriculture applications."),
            ("2610.00004", "End-to-End Planning for Autonomous Driving with World Models",
             "Autonomous driving end-to-end planning with world models."),
        ]
        for aid, title, abs_ in papers:
            entries.append(
                f"<entry><id>http://arxiv.org/abs/{aid}v1</id><title>{title}</title><summary>{abs_}</summary>"
                f"<published>{(self.now - timedelta(hours=20)).strftime('%Y-%m-%dT%H:%M:%SZ')}</published>"
                f"<author><name>A. Author</name></author></entry>")
        return ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">' + "".join(entries) + "</feed>")

    def hf_papers(self) -> list:
        return [{"paper": {"id": "2610.00001", "title": "Sparse Autoencoders Reveal Deceptive Features in Language Models",
                           "summary": "We use interpretability tools to study alignment and deception in LLMs. Longer abstract.",
                           "upvotes": 87, "publishedAt": self.now.isoformat(), "organization": {"name": "google"},
                           "authors": [{"name": "A. Author"}]}}]

    def hf_models(self, org: str) -> list:
        if org != "Qwen":
            return []
        ts = (self.now - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        return [{"id": f"Qwen/Qwen5-72B{s}", "createdAt": ts, "pipeline_tag": "text-generation",
                 "tags": ["transformers"], "likes": 10} for s in ("-Instruct", "-Instruct-FP8", "")]

    # ── Jev: deterministic answers derived from the state text ──
    def jev_answer(self, payload: dict) -> dict:
        state = payload["state"].lower()
        self.jev_states.append(payload["state"])
        q = payload["questions"]
        kinds = list(q["kind"]["criteria"])
        topics = list(q["topic"]["criteria"])

        def dist(options, winner):
            return {o: (0.86 if o == winner else 0.14 / (len(options) - 1)) for o in options}

        if "hugging face model hub" in state or "releasing" in state or "claude 5" in state:
            kind = "model_release"
        elif "arxiv" in state or "daily papers" in state:
            kind = "research_paper"
        elif "office" in state or "customer" in state:
            kind = "other_news"
        else:
            kind = "product_or_api"
        topic = ("alignment_safety" if "alignment" in state else
                 "inference_efficiency" if "inference" in state else
                 "driving_robotics" if "driving" in state else
                 "llm_training" if kind == "model_release" else "other")
        sig = {"model_release": 3.2, "research_paper": 2.0, "other_news": 0.4}.get(kind, 1.5)
        if "survey" in state:
            sig = 0.6
        levels = len(q["significance"]["criteria"])
        return {"model": "jev-1.13.0", "usage": {"input_tokens": 500, "output_tokens": 40}, "answers": {
            "kind": {"type": "choice", "choice": kind, "probabilities": dist(kinds, kind), "confidence": 0.8},
            "topic": {"type": "choice", "choice": topic, "probabilities": dist(topics, topic), "confidence": 0.8},
            "significance": {"type": "score", "score": sig, "confidence": 0.7,
                             "probabilities": {str(i): 1 / levels for i in range(levels)}},
            "substantive": {"type": "noul", "noul": 0.2 if "customer" in state else 0.85},
        }}

    # ── router ──
    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        host, path = request.url.host, request.url.path
        if host == "openai.com":
            return httpx.Response(200, text=self.rss(), headers={"content-type": "application/rss+xml"})
        if host == "export.arxiv.org":
            return httpx.Response(200, text=self.arxiv())
        if host == "huggingface.co" and path == "/api/daily_papers":
            return httpx.Response(200, json=self.hf_papers())
        if host == "huggingface.co" and path == "/api/models":
            return httpx.Response(200, json=self.hf_models(request.url.params.get("author")))
        if host == "www.anthropic.com" and path == "/news":
            return httpx.Response(200, text=self.anthropic_html)
        if host == "api.typesafe.ai":
            self.jev_calls += 1
            if self.jev_mode == "auth":
                return httpx.Response(401, json={"error": "bad key"})
            if self.jev_mode == "down":
                return httpx.Response(503, text="down")
            if self.jev_mode == "flaky" and self.jev_calls % 2 == 1:
                return httpx.Response(429, headers={"retry-after": "0"}, text="slow down")
            return httpx.Response(200, json=self.jev_answer(json.loads(request.content)))
        if host == "api.telegram.org":
            return self.telegram(path.rsplit("/", 1)[-1], json.loads(request.content or b"{}"))
        return httpx.Response(404, text="not found")

    def telegram(self, method: str, body: dict) -> httpx.Response:
        if method == "sendMessage":
            self.next_msg_id += 1
            self.tg_sent.append({**body, "message_id": self.next_msg_id})
            return httpx.Response(200, json={"ok": True, "result": {"message_id": self.next_msg_id}})
        if method == "getUpdates":
            off = body.get("offset") or 0
            ups = [u for u in self.tg_updates if u["update_id"] >= off]
            return httpx.Response(200, json={"ok": True, "result": ups})
        if method == "editMessageReplyMarkup":
            self.tg_edits.append(body)
            return httpx.Response(200, json={"ok": True, "result": True})
        if method == "answerCallbackQuery":
            self.tg_answered.append(body["callback_query_id"])
            return httpx.Response(200, json={"ok": True, "result": True})
        return httpx.Response(200, json={"ok": False, "description": "unknown method"})

    def tap(self, update_id: int, item_id: int, label: int, chat_id: str = "42", message_id: int = 1):
        self.tg_updates.append({"update_id": update_id, "callback_query": {
            "id": f"cq{update_id}", "data": f"fb:{item_id}:{label}",
            "message": {"message_id": message_id, "chat": {"id": int(chat_id)}}}})

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


def sent_item_ids(sent: list[dict]) -> list[int]:
    out = []
    for m in sent:
        for row in (m.get("reply_markup") or {}).get("inline_keyboard", []):
            mm = re.match(r"fb:(\d+):", row[0]["callback_data"])
            if mm:
                out.append(int(mm.group(1)))
    return out


UTC = timezone.utc
