"""Verify and refresh Russian services in public/services.json.

- Resolves each host domain via DoH (Cloudflare -> Google fallback).
- Replaces the IP in host entries with the currently resolved value.
- Adds a curated set of extra subdomains per service; drops those that don't resolve.
- Rebuilds Nexign from scratch: nexign.com + subdomains + nexign.ktalk.ru + the
  full set of IPv4 prefixes announced by Nexign's ASN (looked up via RIPEstat).
- Writes the refreshed file and prints a per-service report.

Runs offline-safe: network errors are logged, never crash the build.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES_JSON = ROOT / "public" / "services.json"

DOH_ENDPOINTS = [
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/resolve",
]

IPV4_RE = re.compile(r"^(25[0-5]|2[0-4]\d|[01]?\d\d?)(\.(25[0-5]|2[0-4]\d|[01]?\d\d?)){3}$")
CIDR_RE = re.compile(r"^(25[0-5]|2[0-4]\d|[01]?\d\d?)(\.(25[0-5]|2[0-4]\d|[01]?\d\d?)){3}/([0-9]|[12]\d|3[0-2])$")

# Curated additions per Russian service (candidates — unresolvable ones are dropped).
EXTRA_DOMAINS = {
    "wb": [
        "www.wildberries.ru",
        "suppliers-api.wildberries.ru",
        "seller.wildberries.ru",
        "catalog.wb.ru",
        "search.wb.ru",
        "cart.wb.ru",
        "user-geo-data.wildberries.ru",
        "basket-01.wbbasket.ru",
        "basket-02.wbbasket.ru",
        "basket-05.wbbasket.ru",
        "basket-10.wbbasket.ru",
        "basket-15.wbbasket.ru",
        "basket-20.wbbasket.ru",
    ],
    "litres": [
        "api.litres.ru",
        "m.litres.ru",
        "static.litres.ru",
        "cv.litres.ru",
    ],
    "lamoda": [
        "a.lmcdn.ru",
        "i1.lmcdn.ru",
        "i2.lmcdn.ru",
        "m.lamoda.ru",
        "api.lamoda.ru",
    ],
    "2gis": [
        "catalog.api.2gis.com",
        "catalog.api.2gis.ru",
        "tile0.maps.2gis.com",
        "tile1.maps.2gis.com",
        "tile2.maps.2gis.com",
        "tile3.maps.2gis.com",
        "routing.api.2gis.com",
    ],
    "hh": [
        "api.hh.ru",
        "m.hh.ru",
        "hhcdn.ru",
        "img.hhcdn.ru",
        "employer.hh.ru",
    ],
    "vkusvill": [
        "api.vkusvill.ru",
        "mobile.vkusvill.ru",
    ],
    "sber": [
        "www.sberbank.ru",
        "online.sberbank.ru",
        "sberbank.com",
        "www.sberbank.com",
        "sber.ru",
        "www.sber.ru",
        "id.sber.ru",
        "sbermarket.ru",
        "www.sbermarket.ru",
        "sbermegamarket.ru",
        "securepayments.sberbank.ru",
    ],
    "vtb": [
        "www.vtb.ru",
        "online.vtb.ru",
        "vtb.com",
        "www.vtb.com",
    ],
    "vk-max": [
        "vk.ru",
        "www.vk.ru",
        "www.vk.com",
        "m.vk.com",
        "m.vk.ru",
        "login.vk.com",
        "api.vk.com",
        "vk.me",
        "sun9-1.userapi.com",
        "sun9-25.userapi.com",
        "web.max.ru",
        "api.max.ru",
    ],
    "tbank": [
        "tinkoff.ru",
        "www.tinkoff.ru",
        "id.tinkoff.ru",
        "secure.tinkoff.ru",
        "business.tinkoff.ru",
        "www.tbank.ru",
        "id.tbank.ru",
        "business.tbank.ru",
        "acdn.tinkoff.ru",
    ],
    "yandex": [
        "www.yandex.ru",
        "mail.yandex.ru",
        "maps.yandex.ru",
        "market.yandex.ru",
        "music.yandex.ru",
        "disk.yandex.ru",
        "taxi.yandex.ru",
        "dzen.ru",
        "kinopoisk.ru",
        "yastatic.net",
        "avatars.mds.yandex.net",
        "mc.yandex.ru",
    ],
    "gosuslugi": [
        "beta.gosuslugi.ru",
        "partners.gosuslugi.ru",
        "oplata.gosuslugi.ru",
    ],
    "2ip": [
        "api.2ip.ru",
        "speedtest.2ip.ru",
        "stat.2ip.ru",
    ],
    "ozon": [
        "www.ozon.ru",
        "m.ozon.ru",
        "api.ozon.ru",
        "seller.ozon.ru",
        "docs.ozon.ru",
        "ozon.travel",
        "cdn1.ozone.ru",
        "ir.ozone.ru",
    ],
}

# Nexign gets fully rebuilt from these seeds (+ ASN prefixes from BGP).
NEXIGN_DOMAINS = [
    "nexign.com",
    "www.nexign.com",
    "support.nexign.com",
    "confluence.nexign.com",
    "jira.nexign.com",
    "mail.nexign.com",
    "nexign.ktalk.ru",
]


def http_get_json(url: str, timeout: int = 15, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def resolve_doh(domain: str) -> str | None:
    for base in DOH_ENDPOINTS:
        url = base + "?" + urllib.parse.urlencode({"name": domain, "type": "A"})
        try:
            data = http_get_json(url, timeout=10, headers={"Accept": "application/dns-json"})
        except Exception:
            continue
        for rec in data.get("Answer") or []:
            if rec.get("type") == 1 and rec.get("data"):
                ip = rec["data"].strip()
                if IPV4_RE.match(ip):
                    return ip
    return None


def get_asn_for_ip(ip: str) -> int | None:
    try:
        data = http_get_json(
            f"https://stat.ripe.net/data/network-info/data.json?resource={ip}",
            timeout=15,
        )
    except Exception as e:
        print(f"  ! RIPEstat network-info for {ip}: {e}", file=sys.stderr)
        return None
    asns = (data.get("data") or {}).get("asns") or []
    if asns:
        try:
            return int(asns[0])
        except (TypeError, ValueError):
            return None
    return None


def get_prefixes_for_asn(asn: int) -> list[str]:
    try:
        data = http_get_json(
            f"https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}",
            timeout=30,
        )
    except Exception as e:
        print(f"  ! RIPEstat announced-prefixes AS{asn}: {e}", file=sys.stderr)
        return []
    prefixes = (data.get("data") or {}).get("prefixes") or []
    result = []
    for p in prefixes:
        pref = p.get("prefix") or ""
        if ":" in pref:
            continue
        if CIDR_RE.match(pref):
            result.append(pref)
    return sorted(set(result), key=lambda s: tuple(int(x) for x in s.split("/")[0].split(".")) + (int(s.split("/")[1]),))


def parse_entry(line: str):
    s = line.strip()
    if not s:
        return None
    if s.startswith("#"):
        return ("comment", s.lstrip("#").strip())
    parts = s.split()
    if len(parts) == 1:
        tok = parts[0]
        if CIDR_RE.match(tok):
            return ("cidr", tok)
        if IPV4_RE.match(tok):
            return ("cidr", tok + "/32")
        return ("domain", tok, None)
    if len(parts) == 2:
        return ("domain", parts[0], parts[1])
    return None


def format_entry(e) -> str:
    if e[0] == "comment":
        return f"# {e[1]}"
    if e[0] == "cidr":
        return e[1]
    if e[0] == "domain":
        return f"{e[1]} {e[2]}" if e[2] else e[1]
    raise ValueError(e)


def refresh_service(svc: dict, extra_domains: list[str]) -> dict:
    name = svc.get("name", svc.get("id"))
    print(f"\n== {name} ==")
    parsed = [p for p in (parse_entry(l) for l in svc.get("entries", [])) if p]
    comment = next((p for p in parsed if p[0] == "comment"), ("comment", name))
    existing_domains = [p for p in parsed if p[0] == "domain"]
    existing_cidrs = [p for p in parsed if p[0] == "cidr"]

    # Merge domain candidate list (preserve order, dedupe case-insensitive)
    domain_order: list[str] = []
    seen = set()
    for p in existing_domains:
        d = p[1].lower()
        if d not in seen:
            seen.add(d)
            domain_order.append(d)
    for d in extra_domains:
        dl = d.lower()
        if dl not in seen:
            seen.add(dl)
            domain_order.append(dl)

    # Resolve
    resolved: list[tuple[str, str]] = []
    dropped: list[str] = []
    for d in domain_order:
        ip = resolve_doh(d)
        if ip:
            resolved.append((d, ip))
            print(f"  ok  {d} -> {ip}")
        else:
            dropped.append(d)
            print(f"  --  {d} (не резолвится)")
        time.sleep(0.05)

    new_entries = [format_entry(comment)]
    new_entries += [format_entry(("domain", d, ip)) for d, ip in resolved]
    new_entries += [format_entry(p) for p in existing_cidrs]

    result = dict(svc)
    result["entries"] = new_entries
    result["_report"] = {
        "resolved": len(resolved),
        "dropped": dropped,
        "cidrs_kept": len(existing_cidrs),
    }
    return result


def rebuild_nexign(svc: dict) -> dict:
    print("\n== Nexign (полная перестройка) ==")
    resolved: list[tuple[str, str]] = []
    dropped: list[str] = []
    for d in NEXIGN_DOMAINS:
        ip = resolve_doh(d)
        if ip:
            resolved.append((d, ip))
            print(f"  ok  {d} -> {ip}")
        else:
            dropped.append(d)
            print(f"  --  {d} (не резолвится)")
        time.sleep(0.05)

    # Find ASN via main domain IP
    prefixes: list[str] = []
    main_ip = next((ip for d, ip in resolved if d in ("nexign.com", "www.nexign.com")), None)
    if main_ip:
        asn = get_asn_for_ip(main_ip)
        print(f"  asn for {main_ip}: AS{asn}")
        if asn:
            prefixes = get_prefixes_for_asn(asn)
            print(f"  prefixes from AS{asn}: {len(prefixes)}")

    new_entries = ["# Nexign"]
    new_entries += [f"{d} {ip}" for d, ip in resolved]
    new_entries += prefixes

    result = dict(svc)
    result["entries"] = new_entries
    result["_report"] = {
        "resolved": len(resolved),
        "dropped": dropped,
        "cidrs_kept": len(prefixes),
        "note": "RFC1918/private networks removed; CIDRs rebuilt from BGP",
    }
    return result


def main() -> int:
    data = json.loads(SERVICES_JSON.read_text(encoding="utf-8"))
    services = data.get("services", [])
    reports = []

    for i, svc in enumerate(services):
        if svc.get("category") != "ru":
            continue
        sid = svc.get("id")
        if sid == "nexign":
            services[i] = rebuild_nexign(svc)
        else:
            extra = EXTRA_DOMAINS.get(sid, [])
            services[i] = refresh_service(svc, extra)
        reports.append((svc.get("name", sid), services[i].pop("_report", {})))

    data["services"] = services
    SERVICES_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )

    print("\n===== ИТОГ =====")
    for name, rep in reports:
        dropped = rep.get("dropped") or []
        print(
            f"{name}: domains={rep.get('resolved', 0)}, "
            f"cidrs={rep.get('cidrs_kept', 0)}, "
            f"dropped={len(dropped)}"
            + (f" [{', '.join(dropped)}]" if dropped else "")
        )
    print(f"\nsaved: {SERVICES_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
