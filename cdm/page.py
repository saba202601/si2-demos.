"""Build the downloads and the website page cdm-ontology.html.   python page.py SITE_DIR"""
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

import build as B
import model as M

HERE = Path(__file__).resolve().parent


def size(p: Path) -> str:
    n = p.stat().st_size
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def clean(rows):
    out = []
    for r in rows:
        out.append({k: (None if (not isinstance(v, (list, dict, str, bool)) and pd.isna(v)) else
                        (int(v) if isinstance(v, float) and v.is_integer() else v)) for k, v in r.items()})
    return [{k: ("" if v is None else ("Yes" if v is True else "No" if v is False else v)) for k, v in r.items()} for r in out]


def main(site: Path):
    dl = site / "downloads"
    stats, meta, data, _matrix = B.main(dl)
    pol = data["Policy"].merge(data["Party"][["party_id", "named_insured_name"]], on="party_id")
    prem = data["Premium"].groupby("policy_number", as_index=False)[["written_premium", "surplus_lines_tax"]].sum(min_count=1)
    pol = pol.merge(prem, on="policy_number", how="left")
    head = ["policy_number", "named_insured_name", "country", "state", "writing_company"]
    cp = pol.merge(data["Location"][["location_id", "policy_number"]], on="policy_number").merge(data["Building"], on="location_id")
    cp = cp.merge(data["Coverage"][["building_id", "building_limit", "deductible_type", "wind_deductible_pct", "eq_deductible_pct"]], on="building_id")
    samples = {
        "CP": cp[head + ["building_id", "construction_class", "roof_year", "sprinkler", "building_limit", "deductible_type",
                         "wind_deductible_pct", "eq_deductible_pct", "written_premium", "surplus_lines_tax"]],
        "WC": pol.merge(data["Classification"].query("lob == 'WC'")[["policy_number", "wc_class_code", "estimated_payroll"]], on="policy_number")
                 .merge(data["StateCoverage"].query("wc_part3_type == '3A'")[["policy_number", "wc_bureau", "experience_mod"]], on="policy_number")
                 [head[:4] + ["wc_bureau", "wc_class_code", "estimated_payroll", "experience_mod", "written_premium"]],
        "GL": pol.merge(data["Classification"].query("lob == 'GL'")[["policy_number", "gl_class_code", "gl_premium_basis", "gl_exposure",
                                                                     "subcontractor_cost", "ny_labor_law_exposure"]], on="policy_number")
                 .merge(data["Coverage"].query("line_of_business == 'GL'")[["policy_number", "gl_coverage_form", "retroactive_date"]], on="policy_number")
                 [head + ["product_code", "gl_class_code", "gl_premium_basis", "gl_exposure", "gl_coverage_form", "retroactive_date",
                          "ny_labor_law_exposure", "written_premium", "surplus_lines_tax"]],
        "CA": pol.merge(data["Vehicle"], on="policy_number").merge(data["Driver"][["vehicle_id", "driver_mvr_points", "cdl_ind"]], on="vehicle_id")
                 .merge(data["Coverage"].query("line_of_business == 'CA'")[["policy_number", "pip_limit", "um_limit"]], on="policy_number")
                 [head[:5] + ["vehicle_id", "vehicle_type", "gvw", "radius_class", "driver_mvr_points", "cdl_ind", "pip_limit", "um_limit"]],
    }
    hits = data["RuleHits"].merge(data["Policy"][["policy_number", "line_of_business"]], on="policy_number")
    lobs = {}
    used = {"CP": ["Policy", "Party", "Location", "Building", "Coverage", "Premium", "Claim", "Cession"],
            "WC": ["Policy", "Party", "StateCoverage", "Classification", "Coverage", "Premium", "Claim", "BillingAccount"],
            "GL": ["Policy", "Party", "Location", "Classification", "Coverage", "Premium", "Claim"],
            "CA": ["Policy", "Party", "Vehicle", "Driver", "Coverage", "Premium", "Claim", "Cession"]}
    for code in M.LOBS:
        lobs[code] = {
            "objects": used[code],
            "elements": [[e["element_code"], e["name"], e["pick_list"]] for e in M.ELEMENTS if code in e["lobs"].split(",") and e["lobs"] != "*"][:14],
            "rating": [[d, f] for l, _s, d, f, _t in M.RATING if l == code],
            "rules": [[c, n, cond, a] for c, n, s, _p, cond, a, _o in M.RULES if s.get("lob") == code],
            "sample": clean(samples[code].head(8).to_dict("records")),
            "hits": [[h.rule_code, h.policy_number, h.finding] for h in hits[hits.line_of_business == code].itertuples()],
        }
    files = [
        ("SI2_Commercial_CDM_and_Ontology.zip", "ZIP", "Everything in one file", "The workbook, SQL Server script, CSV tables, Turtle and JSON-LD, generated in the same run."),
        ("SI2_Commercial_CDM.xlsx", "XLSX", "CDM workbook", "Keys, objects, elements, applicability, resolved examples, pick lists, rules, rating, crosswalk and synthetic data."),
        ("SI2_Commercial_CDM_SQLServer.sql", "SQL", "SQL Server script", "Schema cdm: metadata tables, entity tables with synthetic rows, the resolve function and a premium view."),
        ("SI2_Commercial_CDM_csv.zip", "CSV", "CSV tables", "Every metadata and sample-data table as CSV."),
        ("SI2_Commercial_Ontology.ttl", "TTL", "Ontology (Turtle)", "OWL classes and properties, SKOS pick lists and synonyms, applicability by key, rules and rating steps."),
        ("SI2_Commercial_Ontology.jsonld", "JSON", "Ontology (JSON-LD)", "The same graph as JSON-LD for APIs and AI agents."),
    ]
    payload = {
        "stats": [[4, "commercial lines"], [stats["objects"], "objects"], [stats["elements"], "data elements"],
                  [stats["applicability"], "scoped applicability rows"], [f"{stats['pick_lists']} / {stats['options']}", "pick lists / options"],
                  [stats["rules"], "business rules"], [stats["rating_steps"], "rating steps"], [stats["triples"], "ontology triples"]],
        "keys": [list(k) for k in M.KEY_DOC],
        "elements": [{k: e[k] for k in ("element_code", "name", "object", "lobs", "modules", "base_required")} | {"code": e["element_code"]} for e in M.ELEMENTS],
        "applic": [{"e": c, "s": s, "r": r, "d": d, "l": l, "why": w} for c, s, r, d, l, w in M.APPLIC],
        "lobs": lobs,
        "downloads": [{"file": f, "ext": x, "title": t, "desc": d, "size": size(dl / f)} for f, x, t, d in files],
    }
    html = (HERE / "page_template.html").read_text(encoding="utf-8")
    html = html.replace("__DATA__", json.dumps(payload, ensure_ascii=False)).replace("__VERSION__", B.VERSION)
    (site / "cdm-ontology.html").write_text(html, encoding="utf-8")
    print(json.dumps(stats))


if __name__ == "__main__":
    site = Path(sys.argv[1])
    site.mkdir(parents=True, exist_ok=True)
    main(site)
