"""Read-only access to the SI2Canonical master for the Canonical Master page (SQL Server or the model in memory).

    python -m si2_common.master_source            # check every query against SI2Canonical (SI2_SQL_SERVER)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

DRIVERS = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 13 for SQL Server",
           "SQL Server Native Client 11.0", "SQL Server"]
FORM_NOTE = "Field on an insurance form"


# ------------------------------------------------------------------------------------------ sources
class SqlSource:
    kind = "sql"

    def __init__(self, server: str, database: str):
        import pyodbc
        driver = next((d for d in DRIVERS if d in pyodbc.drivers()), None)
        if not driver:
            raise RuntimeError("no SQL Server ODBC driver on this PC")
        self.server = server
        self.cn = pyodbc.connect(f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;"
                                 "TrustServerCertificate=yes;", autocommit=True)

    def q(self, sql: str, *args) -> pd.DataFrame:
        cur = self.cn.cursor()
        cur.execute(sql, *args)
        cols = [d[0] for d in cur.description]
        return pd.DataFrame.from_records([tuple(r) for r in cur.fetchall()], columns=cols)

    def summary(self) -> dict:
        d = self.q("SELECT * FROM canon.vw_Summary")
        return d.iloc[0].to_dict() if len(d) else {}

    def elements(self, text: str, subject: str) -> pd.DataFrame:
        like = f"%{text.strip()}%"
        return self.q(
            "SELECT TOP (300) e.ElementCode AS Code, e.Name, e.SubjectAreaCode AS Subject, e.DataType AS Type, p.PickListCode AS PickList, "
            "CAST(e.IsPII AS int) AS PII, (SELECT COUNT(*) FROM canon.ElementUsage u WHERE u.ElementId = e.ElementId) AS UsedIn, "
            "(SELECT COUNT(*) FROM canon.Synonym s WHERE s.ObjectType = 'ELEMENT' AND s.ObjectId = e.ElementId AND s.Status <> 'EXPIRED') AS Aliases "
            "FROM canon.DataElement e LEFT JOIN canon.PickList p ON p.PickListId = e.PickListId "
            "WHERE e.ScopeId = 1 AND e.Status <> 'EXPIRED' AND (? = '' OR e.SubjectAreaCode = ?) "
            "AND (? = '%%' OR e.ElementCode LIKE ? OR e.Name LIKE ? OR EXISTS (SELECT 1 FROM canon.Synonym s WHERE s.ObjectType = 'ELEMENT' "
            "AND s.ObjectId = e.ElementId AND s.SynonymText LIKE ?)) ORDER BY e.Name", subject, subject, like, like, like, like)

    def subjects(self) -> list[str]:
        return self.q("SELECT SubjectAreaCode FROM canon.SubjectArea ORDER BY SortOrder, SubjectAreaCode")["SubjectAreaCode"].tolist()

    def element(self, code: str) -> dict:
        e = self.q("SELECT e.ElementId, e.ElementCode, e.Name, e.BusinessDescription, e.SubjectAreaCode, e.DataType, CAST(e.IsPII AS int) AS IsPII, "
                   "p.PickListCode, p.Name AS PickListName FROM canon.DataElement e LEFT JOIN canon.PickList p ON p.PickListId = e.PickListId "
                   "WHERE e.ElementCode = ? AND e.ScopeId = 1", code)
        if not len(e):
            return {}
        r = e.iloc[0].to_dict()
        r["aliases"] = self.q("SELECT SynonymText AS Alias, SourceSystem AS Source, SynonymType AS Kind FROM canon.Synonym "
                              "WHERE ObjectType = 'ELEMENT' AND ObjectId = ? AND Status <> 'EXPIRED' ORDER BY SynonymText", int(r["ElementId"]))
        r["usage"] = self.q("SELECT UsedIn AS [Used in], ObjectName AS [Section], FieldName AS Field FROM canon.ElementUsage "
                            "WHERE ElementId = ? ORDER BY UsedIn, FieldName", int(r["ElementId"]))
        r["options"] = self.options(r["PickListCode"]) if r.get("PickListCode") else pd.DataFrame()
        return r

    def options(self, picklist: str) -> pd.DataFrame:
        return self.q("SELECT o.OptionCode AS Code, o.OptionName AS Name, o.LobScope AS Lines, o.StateScope AS States FROM canon.PickListOption o "
                      "JOIN canon.PickList p ON p.PickListId = o.PickListId WHERE p.PickListCode = ? AND p.ScopeId = 1 AND o.Status <> 'EXPIRED' "
                      "ORDER BY o.SortOrder, o.OptionName", picklist)

    def picklists(self, text: str) -> pd.DataFrame:
        like = f"%{text.strip()}%"
        return self.q("SELECT TOP (300) p.PickListCode AS Code, p.Name, p.LibrarySource AS Library, "
                      "(SELECT COUNT(*) FROM canon.PickListOption o WHERE o.PickListId = p.PickListId AND o.Status <> 'EXPIRED') AS Options, "
                      "(SELECT COUNT(*) FROM canon.DataElement e WHERE e.PickListId = p.PickListId AND e.Status <> 'EXPIRED') AS Elements "
                      "FROM canon.PickList p WHERE p.ScopeId = 1 AND p.Status <> 'EXPIRED' AND (p.PickListCode LIKE ? OR p.Name LIKE ?) "
                      "ORDER BY p.Name", like, like)

    def forms(self) -> pd.DataFrame:
        return self.q("SELECT UsedIn AS Form, COUNT(*) AS Fields, COUNT(DISTINCT ElementId) AS Elements FROM canon.ElementUsage "
                      "WHERE Notes = ? GROUP BY UsedIn ORDER BY UsedIn", FORM_NOTE)

    def form_fields(self, form: str) -> pd.DataFrame:
        return self.q("SELECT u.ObjectName AS [Section], u.FieldName AS Field, e.ElementCode AS Element, e.Name AS [Element name], "
                      "e.DataType AS Type, p.PickListCode AS PickList FROM canon.ElementUsage u JOIN canon.DataElement e ON e.ElementId = u.ElementId "
                      "LEFT JOIN canon.PickList p ON p.PickListId = e.PickListId WHERE u.UsedIn = ? ORDER BY u.ObjectName, u.FieldName", form)

    def entity_model(self) -> pd.DataFrame:
        return self.q("SELECT Entity, EntityName, ParentEntity, Seq, ElementCode, ElementName, DataType, PickList, SubjectArea, InMaster "
                      "FROM canon.vw_EntityModel ORDER BY SortOrder, Entity, Seq")


class ModelSource:
    """The commercial application model in memory: the same pages without SQL Server."""
    kind = "memory"
    server = ""

    def __init__(self):
        root = Path(__file__).resolve().parents[1]
        for p in (root / "sql" / "si2_canonical", root.parent / "si2_canonical_db", root):
            if (p / "commercial_app_model.py").exists() and str(p) not in sys.path:
                sys.path.insert(0, str(p))
        import commercial_app_model as M
        self.M = M
        self.pl = {p[0]: p for p in M.PICKLISTS}
        self.el = {e[0]: e for e in M.ELEMENTS}

    def summary(self) -> dict:
        return {"DataElements": len(self.el), "PickLists": len(self.pl), "PickListOptions": sum(len(p[3]) for p in self.pl.values()),
                "Synonyms": sum(len(e[7]) for e in self.el.values()), "WhereUsed": 0}

    def subjects(self) -> list[str]:
        return sorted({e[2] for e in self.el.values()})

    def elements(self, text: str, subject: str) -> pd.DataFrame:
        t = text.strip().lower()
        rows = [{"Code": c, "Name": e[1], "Subject": e[2], "Type": e[3], "PickList": e[5], "PII": int(e[6]), "UsedIn": 0, "Aliases": len(e[7])}
                for c, e in self.el.items() if (not subject or e[2] == subject)
                and (not t or t in c.lower() or t in e[1].lower() or any(t in a.lower() for a in e[7]))]
        return pd.DataFrame(rows).sort_values("Name") if rows else pd.DataFrame()

    def element(self, code: str) -> dict:
        e = self.el.get(code)
        if not e:
            return {}
        return {"ElementCode": code, "Name": e[1], "BusinessDescription": e[4], "SubjectAreaCode": e[2], "DataType": e[3], "IsPII": int(e[6]),
                "PickListCode": e[5], "PickListName": self.pl[e[5]][1] if e[5] in self.pl else e[5],
                "aliases": pd.DataFrame({"Alias": e[7]}), "usage": pd.DataFrame(), "options": self.options(e[5]) if e[5] else pd.DataFrame()}

    def options(self, picklist: str) -> pd.DataFrame:
        p = self.pl.get(picklist)
        return pd.DataFrame([{"Code": c, "Name": n} for c, n in p[3]]) if p else pd.DataFrame()

    def picklists(self, text: str) -> pd.DataFrame:
        t = text.strip().lower()
        rows = [{"Code": c, "Name": p[1], "Library": "COMPANY", "Options": len(p[3]), "Elements": sum(1 for e in self.el.values() if e[5] == c)}
                for c, p in self.pl.items() if not t or t in c.lower() or t in p[1].lower()]
        return pd.DataFrame(rows)

    def forms(self) -> pd.DataFrame:
        return pd.DataFrame()

    def form_fields(self, form: str) -> pd.DataFrame:
        return pd.DataFrame()

    def entity_model(self) -> pd.DataFrame:
        rows = []
        for code, name, _desc, parent, attrs in self.M.ENTITIES:
            for i, a in enumerate(attrs, 1):
                e = self.el.get(a)
                rows.append({"Entity": code, "EntityName": name, "ParentEntity": parent, "Seq": i, "ElementCode": a,
                             "ElementName": e[1] if e else a, "DataType": e[3] if e else "", "PickList": e[5] if e else None,
                             "SubjectArea": e[2] if e else "", "InMaster": "IN MODEL"})
        return pd.DataFrame(rows)




def _check() -> int:
    server = os.environ.get("SI2_SQL_SERVER", "").strip()
    if not server:
        print("SI2_SQL_SERVER is not set: the page will show the model in memory.")
        return 0
    s = SqlSource(server, os.environ.get("SI2_SQL_DATABASE", "SI2Canonical"))
    summ = s.summary()
    print("Canonical Master check on", server)
    print("  summary:", ", ".join(f"{k} {v}" for k, v in summ.items()))
    el = s.elements("", "")
    print(f"  elements: {len(el)} shown (first 300); subjects: {len(s.subjects())}")
    if len(el):
        e = s.element(el.iloc[0]["Code"])
        print(f"  element {e['ElementCode']}: {len(e['aliases'])} aliases, {len(e['usage'])} uses, {len(e['options'])} options")
    pls = s.picklists("")
    print(f"  pick lists: {len(pls)} shown" + (f"; {pls.iloc[0]['Code']} has {len(s.options(pls.iloc[0]['Code']))} options" if len(pls) else ""))
    fm = s.forms()
    print(f"  forms: {len(fm)}" + (f"; {fm.iloc[0]['Form']} has {len(s.form_fields(fm.iloc[0]['Form']))} fields" if len(fm) else ""))
    print(f"  Party model: {len(s.entity_model())} entity elements")
    print("  OK")
    return 0


if __name__ == "__main__":
    sys.exit(_check())
