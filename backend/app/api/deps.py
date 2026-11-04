from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db
from app.services.scoring import RiskConfig, load_risk_config
from app.storage import Storage, get_storage

DbDep = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
StorageDep = Annotated[Storage, Depends(get_storage)]


def get_risk_config(settings: SettingsDep) -> RiskConfig:
    return load_risk_config(settings.risk_config)


RiskDep = Annotated[RiskConfig, Depends(get_risk_config)]
