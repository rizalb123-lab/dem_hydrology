# -*- coding: utf-8 -*-
"""
Lightweight translation layer.

* The strings inside the code are the *source* texts (Bahasa Indonesia).
* ``translations/en.json`` maps every source text to English.
* Every other language file (``translations/<code>.json``) is keyed by the ENGLISH text, so
  translating the plugin into a new language only needs the English template:
      1. In the dialog press "Export translation template" (or copy ``translations/_template.json``).
      2. Fill in the values, set ``"_meta"`` -> ``"name"`` to the language name.
      3. Save it as ``<code>.json`` in the user folder opened by "Open language folder".
  The new language shows up in the language selector immediately.
Texts that are missing from a language file fall back to English.
"""
import json
import os

_HERE = os.path.dirname(__file__)
BUILTIN_DIR = os.path.join(_HERE, "translations")
SOURCE_LANG = "id"
DEFAULT_LANG = "en"

_EN = {}
_PACKS = {}
_lang = DEFAULT_LANG
_seen = set()
VERSION = 0
RECORD = False


def user_dir():
    try:
        from qgis.core import QgsApplication
        base = QgsApplication.qgisSettingsDirPath()
    except Exception:
        base = ""
    if not base:
        base = os.path.expanduser("~")
    d = os.path.join(base, "dem_hydrology_languages")
    return d


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def reload():
    """(Re)read all language files."""
    global _EN, _PACKS, VERSION
    VERSION += 1
    _EN, _PACKS = {}, {}
    p = os.path.join(BUILTIN_DIR, "en.json")
    if os.path.exists(p):
        _EN = {k: v for k, v in _load(p).items() if k != "_meta"}
    for d in (BUILTIN_DIR, user_dir()):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".json") or fn.startswith("_") or fn in ("en.json",):
                continue
            code = fn[:-5]
            try:
                data = _load(os.path.join(d, fn))
            except Exception:
                continue
            meta = data.pop("_meta", {}) if isinstance(data, dict) else {}
            _PACKS[code] = dict(name=meta.get("name", code), data=data, user=(d != BUILTIN_DIR))


def languages():
    """[(code, display name)] - English and Indonesian are always present."""
    out = [("en", "English"), ("id", "Bahasa Indonesia")]
    for c, p in sorted(_PACKS.items()):
        if c not in ("en", "id"):
            out.append((c, p["name"] + (" *" if p["user"] else "")))
    return out


def set_language(code):
    global _lang
    _lang = code if code in dict(languages()) else DEFAULT_LANG


def language():
    return _lang


def guess_language(locale_name):
    """Pick a supported language from a QGIS locale such as 'id_ID' or 'es'."""
    code = (locale_name or "").split("_")[0].lower()
    return code if code in dict(languages()) else DEFAULT_LANG


def tr(s):
    """Translate a source text. Unknown texts are returned unchanged."""
    if not isinstance(s, str) or not s:
        return s
    if RECORD:
        _seen.add(s)
    if _lang == SOURCE_LANG:
        return s
    en = _EN.get(s)
    if en is None:
        return s if _lang == "en" else _PACKS.get(_lang, {}).get("data", {}).get(s, s)
    if _lang == "en":
        return en
    return _PACKS.get(_lang, {}).get("data", {}).get(en) or en


def trf(s, *a):
    return tr(s) % a if a else tr(s)


def localize(obj, skip_keys=("key", "type", "default", "min", "max", "step", "refs", "id")):
    """Deep copy of a registry-like structure with every text translated."""
    if isinstance(obj, str):
        return tr(obj)
    if isinstance(obj, dict):
        return {k: (v if k in skip_keys else localize(v, skip_keys)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        t = [localize(x, skip_keys) for x in obj]
        return type(obj)(t) if isinstance(obj, tuple) else t
    return obj


def seen_texts():
    return set(_seen)


def export_template(path, lang_name="<language name>"):
    """Write a blank translation file keyed by the English texts."""
    keys = sorted({v for v in _EN.values() if v})
    data = {"_meta": {"name": lang_name, "note": "Translate the values. Keep %s, %d, %.1f etc. unchanged."}}
    data.update({k: "" for k in keys})
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return path


reload()
