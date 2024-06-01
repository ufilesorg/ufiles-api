import uuid
from typing import Literal

from apps.base.models import BaseEntity, OwnedEntity


class ObjectMetadata(BaseEntity):
    s3_key: str
    url: str
    size: int
    object_hash: str
    content_type: str


class FileMetadata(OwnedEntity):
    business_id: uuid.UUID | None = None
    parent: uuid.UUID | None = None
    is_directory: bool = False
    permission: Literal["private", "public"] = "public"

    filehash: str
    filename: str

    s3_key: str
    url: str

    content_type: str
    size: int

    @classmethod
    def list(cls):
        import json
        from pathlib import Path

        files_db = Path("db.json")
        if files_db.exists():
            with open("db.json", "r") as f:
                files = json.load(f)
        else:
            files = {}

        return files

    async def save(self):
        import json
        from pathlib import Path

        from json_advanced import JSONSerializer

        files_db = Path("db.json")
        if files_db.exists():
            with open("db.json", "r") as f:
                files = json.load(f)
        else:
            files = {}

        files[self.filehash] = self.model_dump()

        with open("db.json", "w") as f:
            json.dump(files, f, cls=JSONSerializer, indent=4)

    async def delete(self):
        import json
        from pathlib import Path

        from json_advanced import JSONSerializer

        files_db = Path("db.json")
        if files_db.exists():
            with open("db.json", "r") as f:
                files = json.load(f)
        else:
            files = {}

        del files[self.filehash]

        with open("db.json", "w") as f:
            json.dump(files, f, cls=JSONSerializer, indent=4)
