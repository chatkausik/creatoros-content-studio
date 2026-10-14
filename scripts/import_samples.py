#!/usr/bin/env python3
"""Import a creator's source-attributed samples into the local, ignored database."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.creatoros.config import load_settings
from backend.creatoros.store import Store, utcnow


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="JSON with id, name, description, and samples [{text, source}]")
    parser.add_argument("--learn", action="store_true", help="Extract the voice through Mesh (uses API credits)")
    args = parser.parse_args()
    data = json.loads(args.file.read_text())
    from backend.creatoros.main import BrandInput
    validated = BrandInput.model_validate(data)
    settings = load_settings()
    store = Store(settings.data_dir)
    identifier = data.get("id", "imported-creator")
    old = store.get("brands", identifier)
    brand = {**validated.model_dump(), "id": identifier, "is_demo": False,
             "profile": old.get("profile") if old else None,
             "profile_version": old.get("profile_version", 0) if old else 0,
             "created_at": old.get("created_at", utcnow()) if old else utcnow(),
             "imported_at": utcnow(), "profile_url": data.get("profile_url"),
             "import_note": data.get("import_note", "User-provided writing samples")}
    store.put("brands", brand)
    print(f"Imported {len(brand['samples'])} samples for {brand['name']}. Source URLs retained. No engagement inferred.")
    if args.learn:
        from backend.creatoros.pipeline import extract_profile
        try:
            profile = await extract_profile(brand["samples"], settings)
            version = brand["profile_version"] + 1
            store.patch("brands", identifier, {"profile": profile, "profile_version": version, "profile_source": "live"})
            store.put("profiles", {"id": f"{identifier}:v{version}", "brand_id": identifier,
                                   "version": version, "profile": profile, "source": "live", "created_at": utcnow()})
            print(f"Learned profile v{version} through Mesh ({settings.chat_model}).")
        except Exception as error:
            # Adapter errors contain only safe descriptions; avoid tracebacks with request state.
            from backend.creatoros.mesh import MeshError
            print(str(error) if isinstance(error, MeshError) else "Voice extraction failed; imported samples are saved.", file=sys.stderr)
            sys.exit(1)
    store.close()


if __name__ == "__main__":
    asyncio.run(main())
