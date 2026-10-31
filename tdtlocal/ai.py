"""Local AI assistant: talks to any OpenAI-compatible chat server (llama.cpp's ``llama-server``)."""

from __future__ import annotations

import json
import re
import time
import urllib.request
from typing import Any

from .config import Config
from .net import LOCAL_OPENER
from .settings import RESERVED_PARAMS
from .store import Store, channel_ok
from .util import normalize

DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MAX_QUESTION = 500
MAX_REPLY_BYTES = 4_000_000
MAX_ACTIONS = 4
MAX_RESULTS = 6
ROTATE_RANGE = (3, 600)

AI_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "say": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "do": {"type": "string", "enum": ["play", "multi", "kind", "guide"]},
                    "id": {"type": "string"},
                    "ids": {"type": "array", "items": {"type": "string"}},
                    "kind": {"type": "string", "enum": ["tv", "radio"]},
                    "rotate": {"type": "integer"},
                },
                "required": ["do"],
            },
        },
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["id", "why"],
            },
        },
    },
    "required": ["say", "actions", "results"],
}

# The prompt is in Spanish on purpose: the channels, programmes and users are Spanish.
SYSTEM_PROMPT = (
    "Eres el asistente de un visor local de televisión (TDT) y radio. Respondes SIEMPRE con un único JSON "
    '{"say": texto breve en español, "actions": [...], "results": [...]}.\n'
    "Recibes CANDIDATOS preseleccionados, uno por línea: id|nombre|ahora: título (inicio-fin)|luego: título (inicio).\n"
    "Acciones posibles:\n"
    '- {"do":"play","id":ID}: poner un canal.\n'
    '- {"do":"multi","ids":[ID,...],"rotate":SEGUNDOS}: multivisión con hasta 4 canales; rotate '
    "(opcional) pasa el audio de uno a otro cada tantos segundos.\n"
    '- {"do":"kind","kind":"tv"|"radio"}: cambiar entre televisión y radio.\n'
    '- {"do":"guide"}: abrir la guía de programación del canal activo.\n'
    "Reglas:\n"
    "1. Usa SOLO ids de los candidatos. Nunca inventes canales ni programas.\n"
    "2. Si el usuario da una ORDEN (pon, ve, muestra, abre, cambia...), ejecútala con actions y deja results vacío.\n"
    "3. Si el usuario PREGUNTA o BUSCA (hay, qué ponen, dónde dan, algo de...), no ejecutes acciones: devuelve en "
    "results hasta 6 canales que encajen con el id y en why una frase corta con el programa concreto de la "
    "lista; si no hay "
    "nada, dilo en say y deja results vacío.\n"
    "4. Básate en el 'ahora' y el 'luego' de la lista y en la hora actual; si el canal no tiene programa indicado, no "
    "sabes qué emite.\n"
    "5. say: UNA frase de menos de 20 palabras, sin markdown; why: menos de 12 palabras. Responde en JSON compacto."
)

STOPWORDS = {
    "pon",
    "ponme",
    "poner",
    "ver",
    "ves",
    "quiero",
    "puedes",
    "algo",
    "hay",
    "ahora",
    "que",
    "qué",
    "cual",
    "donde",
    "dan",
    "dame",
    "los",
    "las",
    "una",
    "unos",
    "unas",
    "del",
    "por",
    "con",
    "para",
    "esta",
    "este",
    "estan",
    "ponen",
    "emiten",
    "sobre",
    "tele",
    "television",
    "canal",
    "canales",
    "muestra",
    "abre",
    "dime",
    "y",
}
# Words that usually travel together in schedules: asking for one brings the others.
TOPICS = [
    ("noticia", "telediario", "informativ", "actualidad", "24 horas", "boletin"),
    (
        "deport",
        "futbol",
        "partido",
        "liga",
        "baloncesto",
        "tenis",
        "ciclismo",
        "formula",
        "motogp",
        "champions",
        "nba",
        "balonmano",
    ),
    ("pelicula", "cine", "film"),
    ("serie", "capitulo", "temporada"),
    ("document", "naturaleza", "historia", "viaje", "ciencia"),
    ("infantil", "dibujo", "nino", "animacion", "kids", "peque"),
    ("music", "concierto", "cancion", "videoclip", "hits"),
    ("debate", "tertulia", "politica", "congreso", "entrevista", "parlament"),
    ("tiempo", "meteorolog", "prevision"),
    ("cocina", "gastronom", "receta", "chef"),
    ("taurin", "corrida", "toros"),
    ("concurso", "quiz", "preguntas"),
    ("humor", "comedia", "monologo"),
    ("magazine", "corazon", "sociedad", "cotilleo"),
]


class ModelError(RuntimeError):
    """The model answered, but not with something we can use. The message is shown to the user."""


def _clock(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


def parse_reply(raw: str) -> dict[str, Any]:
    """JSON object from the model's reply; tolerates text around it. Falls back to a plain message."""
    try:
        data = json.loads(raw)
    except ValueError:
        match = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(match.group(0)) if match else None
        except ValueError:
            data = None
        if data is None:
            return {"say": raw[:300], "actions": [], "results": []}
    return data if isinstance(data, dict) else {"say": str(data)[:300], "actions": [], "results": []}


def sanitize_reply(data: dict[str, Any], valid: dict[str, str]) -> dict[str, Any]:
    """Keep only well-formed actions and results that refer to ids we offered (``valid``).

    The model is untrusted: it can hallucinate ids or actions, and none of that reaches the browser.
    """
    actions: list[dict[str, Any]] = []
    for action in (data.get("actions") or [])[:MAX_ACTIONS]:
        if not isinstance(action, dict):
            continue
        do = action.get("do")
        if do == "play" and action.get("id") in valid:
            actions.append({"do": "play", "id": action["id"]})
        elif do == "multi":
            ids = [i for i in (action.get("ids") or []) if i in valid][:4]
            if ids:
                rotate = action.get("rotate")
                lo, hi = ROTATE_RANGE
                ok = isinstance(rotate, int) and not isinstance(rotate, bool) and lo <= rotate <= hi
                actions.append({"do": "multi", "ids": ids, "rotate": rotate if ok else None})
        elif do == "kind" and action.get("kind") in ("tv", "radio"):
            actions.append({"do": "kind", "kind": action["kind"]})
        elif do == "guide":
            actions.append({"do": "guide"})
    results = [
        {"id": r["id"], "why": str(r.get("why") or "")[:200]}
        for r in (data.get("results") or [])
        if isinstance(r, dict) and r.get("id") in valid
    ][:MAX_RESULTS]
    return {"say": str(data.get("say") or "")[:500], "actions": actions, "results": results}


class Assistant:
    def __init__(self, config: Config, store: Store) -> None:
        self.config = config
        self.store = store

    def _headers(self, api_key: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        key = self.config.llm_api_key if api_key is None else api_key
        if key:
            headers["Authorization"] = "Bearer " + key
        return headers

    def request_body(
        self, messages: list[dict[str, str]], max_tokens: int | None = None, schema: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """The chat request, built from the current settings."""
        config = self.config
        body: dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens or config.llm_max_tokens,
            "temperature": config.llm_temperature,
            "cache_prompt": True,  # the system prompt is reused between queries
        }
        if config.llm_disable_thinking:
            # Latency matters and reasoning would eat the JSON. Both switches are sent because, depending on
            # model and template, one or the other applies (reasoning_budget=0 has no effect in llama.cpp).
            body["chat_template_kwargs"] = {"enable_thinking": False}
            body["reasoning_effort"] = "none"
        if config.llm_model:
            body["model"] = config.llm_model
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "respuesta", "schema": schema}}
        if config.llm_extra_params:
            try:
                extra = json.loads(config.llm_extra_params)
            except ValueError:
                extra = {}
            body.update({k: v for k, v in extra.items() if k not in RESERVED_PARAMS})
        return body

    def list_models(self, url: str | None = None, api_key: str | None = None) -> list[str]:
        """Model ids offered by the endpoint (``GET <url>/models``); used by the settings dialog."""
        request = urllib.request.Request(
            (url or self.config.llm_url).rstrip("/") + "/models", headers=self._headers(api_key)
        )
        with LOCAL_OPENER.open(request, timeout=min(self.config.llm_timeout, 15)) as response:
            data = json.loads(response.read(MAX_REPLY_BYTES).decode("utf-8", "replace"))
        entries = data.get("data") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise ModelError("el servidor no devuelve la lista de modelos de la API de OpenAI")
        return [str(m["id"]) for m in entries if isinstance(m, dict) and m.get("id")]

    def chat(
        self, messages: list[dict[str, str]], max_tokens: int | None = None, schema: dict[str, Any] | None = None
    ) -> str:
        """One chat completion; every parameter comes from the settings."""
        request = urllib.request.Request(
            self.config.llm_url.rstrip("/") + "/chat/completions",
            data=json.dumps(self.request_body(messages, max_tokens, schema)).encode("utf-8"),
            headers=self._headers(),
        )
        with LOCAL_OPENER.open(request, timeout=self.config.llm_timeout) as response:
            raw = response.read(MAX_REPLY_BYTES).decode("utf-8", "replace")
        try:
            choice = json.loads(raw)["choices"][0]
            text = choice["message"].get("content") or ""
        except (ValueError, LookupError, TypeError, AttributeError) as exc:
            raise ModelError("el modelo devolvió una respuesta que no se entiende") from exc
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)  # empty or complete block
        text = re.sub(r"<think>.*\Z", "", text, flags=re.S).strip()  # unterminated: it was cut while thinking
        if not text and choice.get("finish_reason") == "length":
            raise ModelError("el modelo se quedó pensando y no llegó a contestar")
        return text

    def candidates(
        self, question: str, kinds: list[str], limit: int = 20, now: float | None = None
    ) -> tuple[list[str], dict[str, str]]:
        """Pre-select channels that match the question (name, current programme, category).

        The local model processes prompts slowly, so only a few dozen lines reach it.
        Returns ``(lines for the prompt, {id: name})``.
        """
        now = time.time() if now is None else now
        nq = normalize(question)
        tokens = [t for t in re.findall(r"[a-z0-9]+", nq) if len(t) >= 3 and t not in STOPWORDS]
        topic_words = {w for group in TOPICS if any(w in nq for w in group) for w in group}
        scored: list[tuple[int, str, str, str]] = []
        with_now: list[tuple[int, str, str, str]] = []
        store = self.store
        with store.lock:
            for kind in kinds:
                own = [c for c in store.custom if c["kind"] == kind]
                pool = (store.radios if kind == "radio" else store.channels) + own
                guide = store.epg["radio" if kind == "radio" else "tv"]
                for ch in pool:
                    if not ch["sources"] or channel_ok(ch, store.status) is False:
                        continue
                    current = upcoming = None
                    for p in guide.get(ch.get("epg") or "", []):
                        if p[0] <= now < p[1]:
                            current = p
                        elif p[0] >= now and upcoming is None:
                            upcoming = p
                    name = normalize(ch["name"])
                    score = 0
                    if name and re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", nq):
                        score += 12
                    score += 3 * len(set(re.findall(r"[a-z0-9]+", name)) & set(tokens))
                    parts = [
                        *(current[2:5] if current else []),
                        upcoming[2] if upcoming else "",
                        ch["category"],
                        ch["group"],
                    ]
                    text = normalize(" ".join(parts))
                    score += sum(2 for t in tokens if t in text) + sum(1 for w in topic_words if w in text)
                    row = f"{ch['id']}|{ch['name']}"
                    if current:
                        row += f"|ahora: {current[2][:70]} ({_clock(current[0])}-{_clock(current[1])})"
                    if upcoming:
                        row += f"|luego: {upcoming[2][:60]} ({_clock(upcoming[0])})"
                    if not current and not upcoming:
                        row += "|" + ch["category"]
                    entry = (score, row, ch["id"], ch["name"])
                    if score > 0:
                        scored.append(entry)
                    elif current:
                        with_now.append(entry)
        scored.sort(key=lambda e: -e[0])
        picked = scored[:limit]
        if len(picked) < 6:  # vague question: top up with channels that have a guide
            picked += with_now[: max(0, 10 - len(picked))]
        return [p[1] for p in picked], {p[2]: p[3] for p in picked}

    def ask(self, question: str, kind: str = "tv", now: float | None = None) -> dict[str, Any]:
        """Answer a free-text request with validated actions and/or search results."""
        question = (question or "").strip()[:MAX_QUESTION]
        if not question:
            raise ValueError("pregunta vacía")
        wants_radio = re.search(r"radio|emisora|\bfm\b", question, re.I)
        kinds = ["tv", "radio"] if wants_radio else ["radio" if kind == "radio" else "tv"]
        now = time.time() if now is None else now
        lines, valid = self.candidates(question, kinds, now=now)
        clock = time.localtime(now)
        user = (
            f"CANDIDATOS ({' + '.join(kinds)}):\n"
            + ("\n".join(lines) or "(ninguno)")
            + f"\n\nAhora es {DAYS[clock.tm_wday]}, {time.strftime('%H:%M', clock)}.\nPetición: {question}"
        )
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
        raw = self.chat(messages, schema=AI_SCHEMA)
        return sanitize_reply(parse_reply(raw), valid)
