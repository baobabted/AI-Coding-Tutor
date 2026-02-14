from pydantic import BaseModel


class AttachmentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    file_type: str
    url: str


class UploadBatchOut(BaseModel):
    files: list[AttachmentOut]
