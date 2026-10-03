from pydantic import BaseModel
from typing import Dict, Any

class FeatureRecord(BaseModel):
    lowlevel: Dict[str, Any]
    rhythm: Dict[str, Any]
    tonal: Dict[str, Any]
    metadata: Dict[str, Any]

    