import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b24_client import B24Client, PROJECT_ROOT


ENTITIES = {
    "deal": "crm.deal.list",
    "contact": "crm.contact.list",
    "company": "crm.company.list",
    "lead": "crm.lead.list",
    "product": "crm.product.list",
}


def export_entity(client, entity, fields=None, where=None, out_format="csv"):
    method = ENTITIES[entity]
    if fields:
        select = fields
    else:
        sample = client.call(method, {"limit": 1}).get("result") or [{}]
        select = list(sample[0].keys()) if sample else []
    params = {"select": select}
    if where:
        params["filter"] = where
    rows = client.get_all(method, params)
    return rows


def main():
    ap = argparse.ArgumentParser(description="Выгрузка справочников CRM из b24")
    ap.add_argument("entity", choices=list(ENTITIES), help="Сущность для выгрузки")
    ap.add_argument("-f", "--format", choices=["csv", "json"], default="csv")
    ap.add_argument("--fields", nargs="*", help="Список полей (по умолчанию — все доступные)")
    ap.add_argument("-o", "--output", help="Путь к выходному файлу (по умолчанию data/<entity>.<fmt>)")
    args = ap.parse_args()

    client = B24Client()
    rows = export_entity(client, args.entity, args.fields)

    if args.output:
        out = Path(args.output)
    else:
        out = PROJECT_ROOT / "data" / f"{args.entity}.{args.format}"

    if args.format == "json":
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        fields = list(rows[0].keys()) if rows else []
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in fields})

    print(f"Выгружено {len(rows)} записей -> {out}")


if __name__ == "__main__":
    main()
