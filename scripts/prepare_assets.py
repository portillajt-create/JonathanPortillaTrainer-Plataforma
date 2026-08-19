"""
Script de un solo uso: prepara los assets de marca (logo) para la app a
partir de los archivos originales en "Logo Trainer/". Recorta el exceso
de espacio transparente/negro alrededor del arte y genera un favicon
cuadrado. No forma parte de la app en tiempo de ejecución.
"""

from pathlib import Path

from PIL import Image

ORIGEN = Path(__file__).resolve().parents[3] / "Logo Trainer"
DESTINO = Path(__file__).resolve().parents[1] / "assets"
DESTINO.mkdir(exist_ok=True)


def trim_por_alpha(img: Image.Image, padding: int = 40) -> Image.Image:
    """Recorta al bounding box del contenido no transparente, con margen."""
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if not bbox:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(img.width, right + padding)
    bottom = min(img.height, bottom + padding)
    return img.crop((left, top, right, bottom))


def trim_por_no_negro(img: Image.Image, umbral: int = 25, padding: int = 60) -> Image.Image:
    """Recorta al bounding box del contenido que NO es negro puro, con margen."""
    rgb = img.convert("RGB")
    mask = rgb.point(lambda p: 255 if p > umbral else 0)
    mask_l = mask.convert("L")
    bbox = mask_l.getbbox()
    if not bbox:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(img.width, right + padding)
    bottom = min(img.height, bottom + padding)
    return img.crop((left, top, right, bottom))


# 1) Icono solo (para favicon e icono colapsado del sidebar)
icono = Image.open(ORIGEN / "Logo fondo transparente.png").convert("RGBA")
icono = trim_por_alpha(icono)
icono.save(DESTINO / "icon.png")

# 2) Logo completo (icono + nombre), fondo transparente, para el sidebar
logo_full = Image.open(ORIGEN / "Fondo transparente.png").convert("RGBA")
logo_full = trim_por_alpha(logo_full)
logo_full.save(DESTINO / "logo_full.png")

# 3) Favicon cuadrado: icono blanco compuesto sobre fondo negro
lado = max(icono.width, icono.height)
lado = int(lado * 1.35)  # margen alrededor del icono
favicon = Image.new("RGBA", (lado, lado), (0, 0, 0, 255))
pos = ((lado - icono.width) // 2, (lado - icono.height) // 2)
favicon.alpha_composite(icono, pos)
favicon.save(DESTINO / "favicon.png")

# 4) Hero para la pantalla de login (arte completo ya compuesto en negro)
portada = Image.open(ORIGEN / "Portada.png").convert("RGB")
portada_recortada = trim_por_no_negro(portada)
portada_recortada.save(DESTINO / "login_hero.png")

# 5) Solo el nombre (sin el icono), para el pie de página de cada sección
nombre = Image.open(ORIGEN / "Nombre fondo transparente.png").convert("RGBA")
nombre = trim_por_alpha(nombre)
nombre.save(DESTINO / "nombre.png")

print("Assets generados en", DESTINO)
for f in sorted(DESTINO.glob("*.png")):
    with Image.open(f) as im:
        print(f" -", f.name, im.size, im.mode)
