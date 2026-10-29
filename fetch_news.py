"""Descarga los feeds de feeds.json, traduce al español lo que venga en inglés
y escribe news.json.

Si un feed falla, se omite y se registra en la sección "failed" de news.json,
para que la página siga funcionando aunque una fuente esté caída.
"""
import json
import email.utils
import datetime as dt
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from deep_translator import GoogleTranslator

ROOT = Path(__file__).parent
UA = "Mozilla/5.0 (compatible; EdicionDelDia/1.0)"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def parse_date(text):
    if not text:
        return None
    text = text.strip()
    try:
        d = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d


def local(tag):
    return tag.split("}", 1)[-1].lower()


def items_from(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        title = link = date = ""
        for child in el:
            name = local(child.tag)
            if name == "title" and child.text:
                title = child.text.strip()
            elif name == "link":
                link = (child.get("href") or child.text or "").strip()
            elif name in ("pubdate", "published", "updated", "date") and child.text and not date:
                date = child.text
        if title:
            out.append({"title": title, "link": link, "date": parse_date(date)})
    return out


def ago(d, now):
    if not d:
        return ""
    mins = int((now - d).total_seconds() // 60)
    if mins < 60:
        return f"hace {max(mins, 1)} min"
    if mins < 60 * 24:
        return f"hace {mins // 60} h"
    return f"hace {mins // 1440} d"


def translate(text):
    try:
        return GoogleTranslator(source="en", target="es").translate(text)
    except Exception as e:  # noqa: BLE001 - si falla la traducción, dejamos el original
        print(f"Traducción fallida: {e}")
        return text


def clean_gnews_title(title):
    # Google News añade " - Nombre del medio" al final del titular.
    return title.rsplit(" - ", 1)[0] if " - " in title else title


def main():
    cfg = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
    now = dt.datetime.now(dt.timezone.utc)
    per_source, failed = [], []

    for feed in cfg["feeds"]:
        try:
            items = items_from(fetch(feed["url"]))[: cfg["perFeed"]]
            for it in items:
                if feed.get("gnews"):
                    it["title"] = clean_gnews_title(it["title"])
                if feed.get("lang") == "en":
                    it["title"] = translate(it["title"])
                it["source"] = feed["name"]
                it["group"] = feed["group"]
            per_source.append(items)
        except Exception as e:  # noqa: BLE001 - queremos seguir con las demás fuentes
            failed.append({"source": feed["name"], "error": str(e)[:120]})

    # Tomamos una noticia de cada fuente por turno, para que ninguna se quede fuera.
    top = []
    for rnd in range(cfg["perFeed"]):
        for items in per_source:
            if rnd < len(items) and len(top) < cfg["maxItems"]:
                top.append(items[rnd])
    top.sort(key=lambda x: x["date"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)

    previous = {}
    p = ROOT / "news.json"
    if p.exists():
        previous = json.loads(p.read_text(encoding="utf-8"))

    news = [
        {
            "title": it["title"],
            "time": ago(it["date"], now),
            "source": it["source"],
            "link": it["link"],
        }
        for it in top
    ]

    data = {
        "edition": previous.get("edition", "Edición del día"),
        "source": "varias fuentes",
        "news": news,
        "updated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "failed": failed,
    }
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(news)} noticias, {len(failed)} fuentes fallidas")


if __name__ == "__main__":
    main()
