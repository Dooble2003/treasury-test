from typing import Literal

from pydantic import BaseModel

Status = Literal["pass", "review", "fail", "not_checked"]


class Application(BaseModel):
    beverage_type: Literal["spirits", "wine", "beer"] = "spirits"
    brand_name: str = ""
    class_type: str = ""
    alcohol_content: str = ""
    net_contents: str = ""
    bottler: str = ""
    country_of_origin: str = ""


class Box(BaseModel):
    image: int
    points: list[list[float]]


class FieldResult(BaseModel):
    key: str
    label: str
    status: Status
    expected: str = ""
    found: str = ""
    note: str = ""
    boxes: list[Box] = []


class DiffPart(BaseModel):
    kind: Literal["same", "missing", "extra", "changed"]
    expected: str = ""
    found: str = ""


class WarningDetail(BaseModel):
    heading_caps: Status
    heading_bold: Status
    wording: Status
    diff: list[DiffPart] = []
    heading_crop: str = ""


class ImageInfo(BaseModel):
    index: int
    width: int
    height: int
    notes: list[str] = []


class VerifyResponse(BaseModel):
    overall: Literal["pass", "review", "fail", "unreadable"]
    message: str
    fields: list[FieldResult]
    warning: WarningDetail | None
    images: list[ImageInfo]
    elapsed_ms: int
