from pydantic import BaseModel


class SolicitudRequest(BaseModel):
    contract_id: str
