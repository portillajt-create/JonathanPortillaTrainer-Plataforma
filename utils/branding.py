"""
Rutas a los assets de marca (logo de Jonathan Portilla Trainer).

Los PNG originales viven fuera del proyecto ("Logo Trainer/"); las
versiones recortadas y listas para la app (favicon, logo de sidebar,
hero de login) se generaron una sola vez con scripts/prepare_assets.py y
quedan versionadas en assets/.
"""

from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

FAVICON = _ASSETS_DIR / "favicon.png"
LOGO_FULL = _ASSETS_DIR / "logo_full.png"
ICON = _ASSETS_DIR / "icon.png"
LOGIN_HERO = _ASSETS_DIR / "login_hero.png"
NOMBRE = _ASSETS_DIR / "nombre.png"
