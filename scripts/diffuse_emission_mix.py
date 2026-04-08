from PIL import Image
from pathlib import Path


def merge_emission_to_alpha(diffuse_path: Path, emission_path: Path):
    if not diffuse_path.is_file():
        print(f"ERROR: diffuse file didn't found: {diffuse_path}")
        return

    if not emission_path.is_file():
        print(f"ERROR: emission mask file didn't found: {emission_path}")
        return

    diffuse = Image.open(diffuse_path).convert("RGBA")

    emission = Image.open(emission_path).convert("L")

    if diffuse.size != emission.size:
        print("Resizing emission mask to match diffuse size...")
        emission = emission.resize(diffuse.size, Image.LANCZOS)

    r, g, b, _ = diffuse.split()

    result = Image.merge("RGBA", (r, g, b, emission))

    result.save(diffuse_path)

    print(f"SUCCESS: file mixed as: {diffuse_path} + {emission_path}")


if __name__ == "__main__":

    diffuse_input = input("Put here diffuse texture name (or full path to texture): ").strip().strip('"')
    emission_input = input("Put here emission mask texture name (or full path to texture): ").strip().strip('"')

    diffuse_path = Path(diffuse_input)
    emission_path = Path(emission_input)

    merge_emission_to_alpha(diffuse_path, emission_path)