"""Mexican REPSE-relevant institutions and the internal-client bucket."""

from __future__ import annotations

from enum import StrEnum


class Institution(StrEnum):
    STPS_REPSE = "stps_repse"
    SAT = "sat"
    IMSS = "imss"
    INFONAVIT = "infonavit"
    INTERNO_CLIENTE = "interno_cliente"


INSTITUTION_LABELS: dict[Institution, str] = {
    Institution.STPS_REPSE: "STPS / REPSE",
    Institution.SAT: "SAT",
    Institution.IMSS: "IMSS",
    Institution.INFONAVIT: "INFONAVIT",
    Institution.INTERNO_CLIENTE: "Interno / Cliente",
}
