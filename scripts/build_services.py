"""Rebuild public/services.json: keep Russian services, parse foreign ones from bats/*.bat."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATS = ROOT / "bats"
OUT = ROOT / "public" / "services.json"

RUSSIAN_SERVICES = [
    {"id": "wb", "name": "WB", "description": "Wildberries", "entries": [
        "# WB",
        "wb.ru 213.184.155.142",
        "www.wb.ru 213.184.155.142",
        "wildberries.ru 185.62.202.2",
        "85.198.76.0/22",
        "90.156.247.0/24",
        "91.230.107.0/24",
        "176.101.88.0/24",
        "185.62.200.0/22",
        "185.138.252.0/22",
        "194.1.214.0/24",
        "213.184.155.0/24",
        "213.184.156.0/22",
    ]},
    {"id": "nexign", "name": "Nexign", "description": "Nexign + приватные сети", "entries": [
        "# Nexign",
        "91.210.4.0/24",
        "91.210.6.0/23",
        "89.169.16.0/24",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "100.64.0.0/10",
    ]},
    {"id": "litres", "name": "Литрес", "description": "ЛитРес", "entries": [
        "# Литрес",
        "litres.ru 193.26.19.99",
        "www.litres.ru 193.26.19.7",
        "193.26.19.0/24",
    ]},
    {"id": "lamoda", "name": "Ламода", "description": "Lamoda", "entries": [
        "# Ламода",
        "lamoda.ru 81.161.98.78",
        "www.lamoda.ru 91.221.165.156",
        "81.161.98.0/23",
        "91.221.165.0/24",
    ]},
    {"id": "2gis", "name": "2ГИС", "description": "2GIS", "entries": [
        "# 2ГИС",
        "2gis.ru 91.236.51.50",
        "www.2gis.ru 91.236.51.50",
        "91.236.51.0/24",
    ]},
    {"id": "hh", "name": "HH", "description": "HeadHunter", "entries": [
        "# HH",
        "hh.ru 94.124.200.0",
        "www.hh.ru 94.124.200.1",
        "94.124.200.0/24",
    ]},
    {"id": "vkusvill", "name": "Вкусвилл", "description": "ВкусВилл", "entries": [
        "# Вкусвилл",
        "vkusvill.ru 178.248.232.221",
        "www.vkusvill.ru 178.248.232.221",
        "178.248.232.0/23",
    ]},
    {"id": "sber", "name": "Сбер", "description": "Сбербанк", "entries": [
        "# Сбер",
        "sberbank.ru 84.252.149.206",
        "84.252.144.0/21",
        "84.252.152.0/24",
        "91.217.194.0/24",
        "185.157.96.0/23",
        "185.157.99.0/24",
        "193.232.123.0/24",
        "194.54.14.0/23",
    ]},
    {"id": "vtb", "name": "ВТБ", "description": "Банк ВТБ", "entries": [
        "# ВТБ",
        "vtb.ru 195.242.82.13",
        "185.179.144.0/22",
        "193.104.70.0/24",
        "193.164.146.0/24",
        "195.242.82.0/23",
        "217.14.48.0/20",
    ]},
    {"id": "vk-max", "name": "ВК+Макс", "description": "ВКонтакте и Max", "entries": [
        "# ВК+Макс",
        "vk.com 87.240.129.133",
        "max.ru 155.212.204.140",
        "help.max.ru 155.212.204.140",
        "87.240.128.0/18",
        "91.231.132.0/22",
        "93.186.224.0/20",
        "95.142.192.0/20",
        "95.213.0.0/17",
        "185.32.248.0/22",
        "185.131.68.0/23",
        "217.69.132.0/24",
        "155.212.192.0/20",
    ]},
    {"id": "tbank", "name": "ТБанк", "description": "Т-Банк (Тинькофф)", "entries": [
        "# ТБанк",
        "tbank.ru 178.130.128.27",
        "45.137.112.0/23",
        "91.194.226.0/23",
        "91.199.205.0/24",
        "91.218.132.0/22",
        "109.172.74.0/24",
        "178.130.128.0/23",
        "185.211.156.0/22",
        "193.143.64.0/22",
        "194.8.224.0/23",
        "194.145.158.0/24",
        "212.233.80.0/21",
        "217.14.23.0/24",
    ]},
    {"id": "yandex", "name": "Яндекс", "description": "Яндекс", "entries": [
        "# Яндекс",
        "yandex.ru 77.88.55.88",
        "ya.ru 5.255.255.242",
        "passport.yandex.ru 213.180.205.78",
        "5.45.192.0/18",
        "5.255.192.0/18",
        "37.9.64.0/18",
        "37.140.128.0/18",
        "77.88.0.0/18",
        "84.252.160.0/19",
        "87.250.224.0/19",
        "92.255.112.0/20",
        "93.158.128.0/18",
        "95.108.128.0/17",
        "141.8.128.0/18",
        "178.154.128.0/18",
        "213.180.192.0/19",
    ]},
    {"id": "gosuslugi", "name": "Госуслуги + NetSchool", "description": "Госуслуги и NetSchool", "entries": [
        "# Госуслуги + NetSchool",
        "gosuslugi.ru 213.59.253.7",
        "asurso.ru 193.25.190.102",
        "smr.asurso.ru 178.237.207.2",
        "south.asurso.ru 178.237.207.2",
        "mobile.ir-tech.ru 37.61.178.231",
        "identity.ir-tech.ru 37.61.178.231",
        "esiagw.asurso.ru 193.25.190.102",
        "www.gosuslugi.ru 213.59.254.7",
        "esia.gosuslugi.ru 213.59.254.8",
        "lk.gosuslugi.ru 213.59.254.7",
        "pos.gosuslugi.ru 109.207.8.76",
        "109.207.1.0/24",
        "109.207.2.0/24",
        "109.207.8.0/24",
        "213.59.253.7/32",
        "213.59.254.7/32",
        "213.59.254.8/32",
        "178.237.207.0/24",
        "193.25.0.0/16",
        "37.61.0.0/16",
    ]},
    {"id": "2ip", "name": "2IP", "description": "2IP.ru", "entries": [
        "# 2IP",
        "2ip.ru 188.40.167.82",
        "2ip.io 188.40.167.81",
        "188.40.167.81/32",
        "188.40.167.82/32",
    ]},
    {"id": "ozon", "name": "Ozon", "description": "Озон", "entries": [
        "# Ozon",
        "ozon.ru 185.73.194.82",
        "finance.ozon.ru 31.130.141.11",
        "46.226.122.0/24",
        "91.212.64.0/24",
        "91.223.93.0/24",
        "185.73.192.0/22",
        "195.34.20.0/23",
        "31.130.140.0/22",
        "194.9.208.0/22",
    ]},
]

FOREIGN_META = {
    "chatgpt":    {"name": "ChatGPT",    "description": "OpenAI ChatGPT"},
    "claude":     {"name": "Claude",     "description": "Anthropic Claude"},
    "cloudflare": {"name": "Cloudflare", "description": "Cloudflare"},
    "facebook":   {"name": "Facebook",   "description": "Meta / Facebook / Instagram"},
    "medium":     {"name": "Medium",     "description": "Medium.com"},
    "rutracker":  {"name": "RuTracker",  "description": "RuTracker.org"},
    "telegram":   {"name": "Telegram",   "description": "Telegram"},
    "youtube":    {"name": "YouTube",    "description": "YouTube"},
}

ROUTE_RE = re.compile(
    r"^\s*route\s+add\s+(\d+\.\d+\.\d+\.\d+)\s+mask\s+(\d+\.\d+\.\d+\.\d+)",
    re.IGNORECASE,
)


def mask_to_prefix(mask: str) -> int:
    parts = [int(p) for p in mask.split(".")]
    bits = 0
    for p in parts:
        bits += bin(p).count("1")
    return bits


def parse_bat(path: Path) -> list[str]:
    cidrs: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = ROUTE_RE.match(line)
        if not m:
            continue
        ip, mask = m.group(1), m.group(2)
        prefix = mask_to_prefix(mask)
        cidr = f"{ip}/{prefix}"
        if cidr in seen:
            continue
        seen.add(cidr)
        cidrs.append(cidr)
    return cidrs


def build_foreign() -> list[dict]:
    services: list[dict] = []
    for bat in sorted(BATS.glob("*-ipv4.bat")):
        key = bat.stem.replace("-ipv4", "")
        if key not in FOREIGN_META:
            continue
        meta = FOREIGN_META[key]
        cidrs = parse_bat(bat)
        if not cidrs:
            continue
        entries = [f"# {meta['name']}", *cidrs]
        services.append({
            "id": key,
            "name": meta["name"],
            "description": meta["description"],
            "entries": entries,
        })
    return services


def main() -> None:
    for s in RUSSIAN_SERVICES:
        s["category"] = "ru"
    foreign = build_foreign()
    for s in foreign:
        s["category"] = "foreign"
    data = {
        "categories": [
            {"id": "ru", "name": "Российские сервисы"},
            {"id": "foreign", "name": "Зарубежные сервисы"},
        ],
        "services": RUSSIAN_SERVICES + foreign,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(RUSSIAN_SERVICES)} ru + {len(foreign)} foreign)")


if __name__ == "__main__":
    main()
