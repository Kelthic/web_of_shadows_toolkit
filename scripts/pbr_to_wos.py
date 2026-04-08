from pathlib import Path
from PIL import Image


def process_texture(path: str) -> None:
    img_path = Path(path)

    if not img_path.exists():
        raise FileNotFoundError(f"ERROR: file didn't found: {img_path}")

    img = Image.open(img_path).convert("RGBA")
    r, g, b, a = img.split()

    # Инвертируем Red → Alpha
    inverted_r = r.point(lambda px: 255 - px)

    # Green → Red и Blue
    new_img = Image.merge("RGBA", (g, g, g, inverted_r))

    new_img.save(img_path)
    print(f"SUCCESS: file converted: {img_path}")


def main() -> None:
    texture_name = input("Put here texture name (or full path to texture): ").strip()

    if not texture_name:
        print("File name cannot be empty.")
        return

    try:
        process_texture(texture_name)
    except FileNotFoundError as e:
        print(f"Ошибка: {e}")
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}")


if __name__ == "__main__":
    main()