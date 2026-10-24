from sqlalchemy import func, select

from api.app.core.models import EmissionFactor, RegionTariff
from api.app.engine import importer

HEADER = "activity_type,region,year,unit,kg_co2e_per_unit,scope,ghg_category,source\n"


def count(db, model):
    return db.execute(select(func.count()).select_from(model)).scalar()


def test_fr_2_02_import_factors_csv(db):
    r = importer.import_factors_text(db, HEADER + "electricity,DE,2024,kWh,0.363,scope_2,Purchased electricity,UBA\n"
                                                  "diesel,GB,2026,litre,2.51,scope_1,Fuels,DESNZ 2026\n")
    assert r["status"] == "completed" and r["created"] == 2 and count(db, EmissionFactor) == 2


def test_nfr_2_08_reimport_is_idempotent_and_changed_value_creates_version(db):
    row = "electricity,DE,2024,kWh,0.363,scope_2,Purchased electricity,UBA\n"
    importer.import_factors_text(db, HEADER + row)
    again = importer.import_factors_text(db, HEADER + row)
    assert again["unchanged"] == 1 and count(db, EmissionFactor) == 1
    changed = importer.import_factors_text(db, HEADER + row.replace("0.363", "0.380"))
    assert changed["versioned"] == 1 and count(db, EmissionFactor) == 2


def test_nfr_2_05_source_and_year_are_required_and_errors_are_per_row(db):
    r = importer.import_factors_text(db, HEADER + "electricity,DE,,kWh,0.363,scope_2,x,UBA\n"
                                                  "electricity,DE,2024,kWh,0.363,scope_2,x,\n"
                                                  "electricity,DE,2024,parsec,0.363,scope_2,x,UBA\n"
                                                  "electricity,DE,2024,kWh,-1,scope_2,x,UBA\n")
    assert r["status"] == "failed" and [e["row"] for e in r["errors"]] == [2, 3, 4, 5]


def test_import_is_atomic_one_bad_row_saves_nothing(db):
    r = importer.import_factors_text(db, HEADER + "electricity,DE,2024,kWh,0.363,scope_2,x,UBA\n"
                                                  "electricity,DE,2025,kWh,abc,scope_2,x,UBA\n")
    assert r["status"] == "failed" and count(db, EmissionFactor) == 0


def test_missing_columns_and_semicolon_csv(db):
    assert importer.import_factors_text(db, "activity_type,region\nelectricity,DE\n")["status"] == "failed"
    r = importer.import_factors_text(db, HEADER.replace(",", ";") + "electricity;DE;2024;kWh;0,363;scope_2;x;UBA\n")
    assert r["status"] == "completed"


def test_fr_2_02_import_tariffs_and_update(db):
    head = "activity_type,region,year,unit,eur_per_unit,source\n"
    assert importer.import_tariffs_text(db, head + "electricity,DE,2024,kWh,0.30,admin\n")["created"] == 1
    r = importer.import_tariffs_text(db, head + "electricity,DE,2024,kWh,0.35,admin\n")
    assert r["updated"] == 1 and count(db, RegionTariff) == 1


def test_seed_files_load_and_are_idempotent(db, tmp_path):
    (tmp_path / "factors.csv").write_text(HEADER + "electricity,DE,2024,kWh,0.363,scope_2,x,UBA\n")
    importer.load_seed_files(db, tmp_path)
    importer.load_seed_files(db, tmp_path)
    assert count(db, EmissionFactor) == 1
