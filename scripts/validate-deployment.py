"""Read-only local validation against Render's official JSON schema."""

from pathlib import Path

import jsonschema
import requests
import yaml

root = Path(__file__).resolve().parent.parent
response = requests.get("https://render.com/schema/render.yaml.json", timeout=20)
response.raise_for_status()
jsonschema.Draft202012Validator(response.json()).validate(
    yaml.safe_load((root / "render.yaml").read_text())
)
print("Render Blueprint schema: PASS (does not create or deploy resources)")
