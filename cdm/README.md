# SI² Commercial Lines CDM + Ontology generator

One governed store (`model.py`) generates the CDM and the ontology together for Commercial Property, Workers' Compensation, General Liability and Commercial Auto, with synthetic data.

    cd cdm
    python build.py out            # workbook, SQL Server script, CSV zip, Turtle, JSON-LD
    python page.py ../website      # also rebuilds website/cdm-ontology.html and website/downloads/

Context key: country · state · company · line · lob · product · object · module · effective dates. `*` = all; the most specific match wins.
Codes, rates and data are illustrative.
