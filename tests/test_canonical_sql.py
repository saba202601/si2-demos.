"""SI² Canonical Master SQL: the generated seed is current and internally consistent."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "sql" / "si2_canonical"
sys.path.insert(0, str(SQL))


def test_seed_is_up_to_date():
    import build_seed
    assert build_seed.build() == (SQL / "03_seed.sql").read_text(encoding="utf-8"), "run sql/si2_canonical/build_seed.py"


def test_scripts_have_balanced_batches():
    for f in ("01_schema.sql", "02_procedures.sql", "04_demo_source.sql"):
        text = (SQL / f).read_text(encoding="utf-8")
        assert text.count("(") == text.count(")"), f
        assert "GO" in text


def test_every_procedure_the_installer_calls_exists():
    procs = {p for f in ("02_procedures.sql", "06_rule_engine.sql", "08_coverage.sql")
             for p in re.findall(r"CREATE OR ALTER PROCEDURE (\w+\.\w+)", (SQL / f).read_text(encoding="utf-8"))}
    used = set(re.findall(r"EXEC (\w+\.usp_\w+)", (SQL / "install_si2_canonical.py").read_text(encoding="utf-8")))
    used |= set(re.findall(r"EXEC (\w+\.usp_\w+)", (SQL / "05_how_to.sql").read_text(encoding="utf-8")))
    assert used and used <= procs, used - procs
