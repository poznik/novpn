"""Verify and refresh Russian services in public/services.json.

The script validates Russian catalog entries against live DNS A records and
selected BGP data from RIPEstat. It keeps the catalog compact:

- direct service networks can be rebuilt from full announced prefixes of
  service-specific ASNs;
- shared/CDN/hoster networks are restricted to prefixes currently observed for
  the service domains, to avoid pulling in unrelated address space;
- adjacent and overlapping networks are collapsed to a minimal CIDR set.

When changes are detected, the script writes a timestamped backup of the source
file before saving the refreshed catalog.
"""
from __future__ import annotations

import argparse
import copy
import ipaddress
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES_JSON = ROOT / "public" / "services.json"

DOH_ENDPOINTS = [
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/resolve",
]

PRIVATE_NETWORKS = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "100.64.0.0/10",
]

RU_SERVICE_RULES = {
    "wb": {
        "extra_domains": [
            "www.wildberries.ru",
            "seller.wildberries.ru",
            "catalog.wb.ru",
            "search.wb.ru",
            "user-geo-data.wildberries.ru",
            "basket-01.wbbasket.ru",
            "basket-02.wbbasket.ru",
            "basket-05.wbbasket.ru",
            "basket-10.wbbasket.ru",
            "basket-15.wbbasket.ru",
            "basket-20.wbbasket.ru",
        ],
        "full_asns": ["57073"],
    },
    "local": {
        "seed_domains": [
            "nexign.com",
            "www.nexign.com",
            "confluence.nexign.com",
            "jira.nexign.com",
            "mail.nexign.com",
            "nexign.ktalk.ru",
        ],
        "static_cidrs": PRIVATE_NETWORKS,
        "full_asns": ["48102"],
    },
    "litres": {
        "extra_domains": [
            "api.litres.ru",
            "m.litres.ru",
            "static.litres.ru",
            "cv.litres.ru",
        ],
        "full_asns": ["61306"],
    },
    "lamoda": {
        "extra_domains": [
            "a.lmcdn.ru",
            "m.lamoda.ru",
            "api.lamoda.ru",
        ],
    },
    "2gis": {
        "extra_domains": [
            "catalog.api.2gis.com",
            "catalog.api.2gis.ru",
            "tile0.maps.2gis.com",
            "tile1.maps.2gis.com",
            "tile2.maps.2gis.com",
            "tile3.maps.2gis.com",
            "routing.api.2gis.com",
        ],
        "full_asns": ["197482"],
    },
    "hh": {
        "extra_domains": [
            "api.hh.ru",
            "m.hh.ru",
            "hhcdn.ru",
            "img.hhcdn.ru",
            "employer.hh.ru",
        ],
        "full_asns": ["47724"],
    },
    "vkusvill": {
        "extra_domains": [
            "api.vkusvill.ru",
            "mobile.vkusvill.ru",
        ],
    },
    "sber": {
        "extra_domains": [
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
        "full_asns": ["35237"],
    },
    "vtb": {
        "extra_domains": [
            "www.vtb.ru",
            "online.vtb.ru",
            "vtb.com",
            "www.vtb.com",
        ],
        "full_asns": ["24823"],
    },
    "vk-max": {
        "extra_domains": [
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
        "full_asns": ["47541"],
    },
    "tbank": {
        "extra_domains": [
            "tinkoff.ru",
            "www.tinkoff.ru",
            "id.tinkoff.ru",
            "business.tinkoff.ru",
            "www.tbank.ru",
            "id.tbank.ru",
            "business.tbank.ru",
            "acdn.tinkoff.ru",
        ],
        "full_asns": ["43399"],
    },
    "yandex": {
        "extra_domains": [
            "www.yandex.ru",
            "mail.yandex.ru",
            "maps.yandex.ru",
            "market.yandex.ru",
            "music.yandex.ru",
            "disk.yandex.ru",
            "taxi.yandex.ru",
            "kinopoisk.ru",
            "yastatic.net",
            "avatars.mds.yandex.net",
            "mc.yandex.ru",
        ],
        "full_asns": ["208398", "13238"],
    },
    "gosuslugi": {
        "extra_domains": [
            "beta.gosuslugi.ru",
            "partners.gosuslugi.ru",
            "oplata.gosuslugi.ru",
        ],
        "full_asns": ["39323", "196747"],
    },
    "2ip": {
        "extra_domains": [
            "api.2ip.ru",
            "speedtest.2ip.ru",
            "stat.2ip.ru",
        ],
        "host_only": True,
    },
    "ozon": {
        "extra_domains": [
            "www.ozon.ru",
            "m.ozon.ru",
            "api.ozon.ru",
            "seller.ozon.ru",
            "docs.ozon.ru",
            "ozon.travel",
            "cdn1.ozone.ru",
            "ir.ozone.ru",
        ],
        "full_asns": ["44386", "207986"],
    },
}

DNS_CACHE: dict[str, list[str]] = {}
NETINFO_CACHE: dict[str, dict] = {}
ASN_PREFIX_CACHE: dict[str, list[str]] = {}


def http_get_json(url: str, headers: dict | None = None, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def numeric_ip_key(ip: str) -> tuple[int, int, int, int]:
    return tuple(int(part) for part in ip.split("."))


def network_sort_key(cidr: str) -> tuple[int, int, int, int, int]:
    net = ipaddress.ip_network(cidr, strict=False)
    addr = str(net.network_address)
    return (*numeric_ip_key(addr), int(net.prefixlen))


def resolve_a_records(domain: str) -> list[str]:
    cached = DNS_CACHE.get(domain)
    if cached is not None:
        return cached
    answers_seen: set[str] = set()
    for endpoint in DOH_ENDPOINTS:
        url = endpoint + "?" + urllib.parse.urlencode({"name": domain, "type": "A"})
        try:
            data = http_get_json(url, headers={"Accept": "application/dns-json"}, timeout=12)
        except Exception:
            continue
        for answer in data.get("Answer") or []:
            if answer.get("type") == 1 and answer.get("data"):
                answers_seen.add(answer["data"].strip())
    result = sorted(answers_seen, key=numeric_ip_key)
    DNS_CACHE[domain] = result
    return result


def get_network_info(ip: str) -> dict:
    cached = NETINFO_CACHE.get(ip)
    if cached is not None:
        return cached
    try:
        data = http_get_json(
            f"https://stat.ripe.net/data/network-info/data.json?resource={ip}",
            timeout=15,
        )
        info = data.get("data") or {}
    except Exception:
        info = {}
    prefix = info.get("prefix") or f"{ip}/32"
    asns = tuple(str(asn) for asn in (info.get("asns") or []))
    result = {"prefix": prefix, "asns": asns}
    NETINFO_CACHE[ip] = result
    return result


def get_announced_prefixes(asn: str) -> list[str]:
    cached = ASN_PREFIX_CACHE.get(asn)
    if cached is not None:
        return cached
    prefixes: list[str] = []
    try:
        data = http_get_json(
            f"https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}",
            timeout=30,
        )
        for item in (data.get("data") or {}).get("prefixes") or []:
            prefix = item.get("prefix") or ""
            if ":" not in prefix:
                prefixes.append(prefix)
    except Exception:
        prefixes = []
    ASN_PREFIX_CACHE[asn] = prefixes
    return prefixes


def collapse_cidrs(cidrs: list[str]) -> list[str]:
    if not cidrs:
        return []
    nets = [ipaddress.ip_network(cidr, strict=False) for cidr in cidrs]
    return [str(net) for net in sorted(ipaddress.collapse_addresses(nets), key=lambda n: network_sort_key(str(n)))]


def parse_service_entries(service: dict) -> tuple[str, list[tuple[str, str]], list[str]]:
    comment = service.get("name", service.get("id", "service"))
    domains: list[tuple[str, str]] = []
    cidrs: list[str] = []
    for line in service.get("entries") or []:
        raw = line.strip()
        if not raw:
            continue
        if raw.startswith("#"):
            if not domains and not cidrs:
                comment = raw.lstrip("#").strip()
            continue
        parts = raw.split()
        if len(parts) == 2 and "/" not in parts[0]:
            domains.append((parts[0], parts[1]))
        elif len(parts) == 1:
            token = parts[0]
            if "/" in token:
                cidrs.append(token)
            else:
                cidrs.append(f"{token}/32")
    return comment, domains, cidrs


def stable_unique(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def preferred_ip(current_ip: str | None, answers: list[str], rules: dict) -> str:
    if current_ip and current_ip in answers:
        return current_ip
    if current_ip and rules.get("full_asns"):
        current_info = get_network_info(current_ip)
        if set(current_info["asns"]) & set(rules["full_asns"]):
            return current_ip
    return answers[0]


def remove_redundant_www_domains(domains: list[tuple[str, str]]) -> list[tuple[str, str]]:
    existing = {(domain, ip) for domain, ip in domains}
    filtered: list[tuple[str, str]] = []
    for domain, ip in domains:
        if domain.startswith("www.") and (domain[4:], ip) in existing:
            continue
        filtered.append((domain, ip))
    return filtered


def remove_redundant_host_cidrs(domains: list[tuple[str, str]], cidrs: list[str]) -> list[str]:
    domain_hosts = {f"{ip}/32" for _, ip in domains}
    return [cidr for cidr in cidrs if cidr not in domain_hosts]


def rebuild_ru_service(service: dict, rules: dict) -> tuple[dict, dict]:
    comment, current_domains, current_cidrs = parse_service_entries(service)
    current_ip_map = {domain: ip for domain, ip in current_domains}
    current_domain_order = [domain for domain, _ in current_domains]

    configured_domains = rules.get("seed_domains") or []
    configured_domains = current_domain_order + rules.get("extra_domains", []) if not configured_domains else configured_domains
    domain_order = stable_unique(configured_domains)

    resolved_domains: list[tuple[str, str]] = []
    missing_domains: list[str] = []
    observed_cidrs: list[str] = []
    observed_hosts: list[str] = []

    for domain in domain_order:
        answers = resolve_a_records(domain)
        if not answers:
            missing_domains.append(domain)
            continue
        resolved_domains.append((domain, preferred_ip(current_ip_map.get(domain), answers, rules)))
        for ip in answers:
            info = get_network_info(ip)
            if rules.get("host_only"):
                observed_hosts.append(f"{ip}/32")
            else:
                observed_cidrs.append(info["prefix"])
        time.sleep(0.03)

    resolved_domains = remove_redundant_www_domains(resolved_domains)

    cidrs: list[str] = []
    cidrs.extend(rules.get("static_cidrs", []))
    cidrs.extend(observed_hosts if rules.get("host_only") else observed_cidrs)
    for asn in rules.get("full_asns", []):
        cidrs.extend(get_announced_prefixes(asn))
        time.sleep(0.03)
    collapsed_cidrs = collapse_cidrs(cidrs)
    collapsed_cidrs = remove_redundant_host_cidrs(resolved_domains, collapsed_cidrs)

    new_entries = [f"# {comment}"]
    new_entries.extend(f"{domain} {ip}" for domain, ip in resolved_domains)
    new_entries.extend(collapsed_cidrs)

    updated = copy.deepcopy(service)
    updated["entries"] = new_entries

    report = {
        "comment": comment,
        "domains_before": len(current_domains),
        "domains_after": len(resolved_domains),
        "cidrs_before": len(collapse_cidrs(current_cidrs)),
        "cidrs_after": len(collapsed_cidrs),
        "missing_domains": missing_domains,
        "added_domains": [domain for domain, _ in resolved_domains if domain not in current_ip_map],
        "removed_domains": [domain for domain, _ in current_domains if domain not in {d for d, _ in resolved_domains}],
        "changed": updated["entries"] != service.get("entries", []),
    }
    return updated, report


def make_backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak.{stamp}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


def rebuild_services(data: dict) -> tuple[dict, dict]:
    updated = copy.deepcopy(data)
    reports: dict[str, dict] = {}
    changed_any = False
    for index, service in enumerate(updated.get("services") or []):
        if service.get("category") != "ru":
            continue
        sid = service.get("id")
        rules = RU_SERVICE_RULES.get(sid)
        if not rules:
            continue
        refreshed, report = rebuild_ru_service(service, rules)
        updated["services"][index] = refreshed
        reports[sid] = report
        changed_any = changed_any or report["changed"]
    reports["_changed_any"] = {"value": changed_any}
    return updated, reports


def print_report(reports: dict) -> None:
    for sid, report in reports.items():
        if sid == "_changed_any":
            continue
        print(
            f"{sid}: domains {report['domains_before']} -> {report['domains_after']}, "
            f"cidrs {report['cidrs_before']} -> {report['cidrs_after']}, "
            f"changed={report['changed']}"
        )
        if report["added_domains"]:
            print("  added domains:", ", ".join(report["added_domains"]))
        if report["removed_domains"]:
            print("  removed domains:", ", ".join(report["removed_domains"]))
        if report["missing_domains"]:
            print("  unresolved:", ", ".join(report["missing_domains"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--services-file", default=str(SERVICES_JSON))
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    services_path = Path(args.services_file).resolve()
    original = json.loads(services_path.read_text(encoding="utf-8"))
    updated, reports = rebuild_services(original)
    print_report(reports)

    changed_any = reports["_changed_any"]["value"]
    if not changed_any:
        print("\nNo changes required.")
        return 0

    if args.check_only:
        print("\nChanges detected. Run without --check-only to write the refreshed file.")
        return 0

    backup = make_backup(services_path)
    services_path.write_text(json.dumps(updated, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    print(f"\nBackup created: {backup}")
    print(f"Updated file:   {services_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
