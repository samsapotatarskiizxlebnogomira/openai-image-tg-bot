# generator.py
import os
import base64
import json
import re
from io import BytesIO
from typing import Optional, List, Tuple

# ───── конфиг
try:
    import config  # type: ignore
    OPENAI_API_KEY = getattr(config, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")
    OPENAI_ORG_ID  = getattr(config, "OPENAI_ORG_ID", None)  or os.getenv("OPENAI_ORG_ID")
    OPENAI_HTTPS_PROXY = getattr(config, "OPENAI_HTTPS_PROXY", None) or os.getenv("OPENAI_HTTPS_PROXY") or os.getenv("HTTPS_PROXY")
except Exception:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_ORG_ID  = os.getenv("OPENAI_ORG_ID")
    OPENAI_HTTPS_PROXY = os.getenv("OPENAI_HTTPS_PROXY") or os.getenv("HTTPS_PROXY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY не найден. Укажи его в .env или config.py")

# ───── исключение для модерации
class ModerationError(Exception):
    def __init__(self, categories: List[str], raw: str = ""):
        super().__init__("moderation_blocked")
        self.categories = categories
        self.raw = raw

# ───── клиент OpenAI (SDK v1+ c httpx-прокси при необходимости)
def _get_client() -> Tuple[str, object]:
    try:
        from openai import OpenAI
        if OPENAI_HTTPS_PROXY:
            import httpx
            http_client = httpx.Client(proxies=OPENAI_HTTPS_PROXY, timeout=60)
            return "new", OpenAI(api_key=OPENAI_API_KEY, organization=OPENAI_ORG_ID, http_client=http_client)
        return "new", OpenAI(api_key=OPENAI_API_KEY, organization=OPENAI_ORG_ID)
    except Exception:
        import openai  # fallback для старого интерфейса
        openai.api_key = OPENAI_API_KEY
        if OPENAI_ORG_ID:
            openai.organization = OPENAI_ORG_ID
        # старый клиент читает HTTPS_PROXY из окружения автоматически
        return "fallback", openai

def _handle_moderation_and_reraise(e: Exception):
    s = str(e)
    if ("moderation_blocked" in s
        or "safety_violations" in s
        or "Your request was rejected by the safety system" in s):
        cats: List[str] = []
        try:
            body = getattr(e, "body", None)
            if body and isinstance(body, (str, bytes)):
                data = json.loads(body if isinstance(body, str) else body.decode("utf-8", "ignore"))
                cats = data.get("error", {}).get("safety_violations", []) or cats
        except Exception:
            pass
        if not cats:
            m = re.search(r"safety_violations=\[([^\]]+)\]", s)
            if m:
                cats = [c.strip().strip("'\"") for c in m.group(1).split(",")]
        raise ModerationError(categories=cats or [], raw=s)
    raise e

# ───── генерация с нуля
def generate_image_bytes(prompt: str, size: str = "1024x1024") -> Optional[bytes]:
    mode, cli = _get_client()
    try:
        resp = (cli.images.generate if mode == "new" else cli.images.generate)(
            model="gpt-image-1",
            prompt=prompt,
            size=size
        )
        b64 = resp.data[0].b64_json
        return base64.b64decode(b64)
    except Exception as e:
        _handle_moderation_and_reraise(e)

# ───── редактирование
def edit_image_bytes(
    image_bytes: bytes,
    prompt: str,
    size: str = "1024x1024",
    mask_bytes: Optional[bytes] = None
) -> Optional[bytes]:
    mode, cli = _get_client()
    img_bio = BytesIO(image_bytes); img_bio.name = "image.png"
    mask_bio = None
    if mask_bytes:
        mask_bio = BytesIO(mask_bytes); mask_bio.name = "mask.png"
    try:
        if mode == "new":
            if mask_bio:
                resp = cli.images.edit(model="gpt-image-1", image=img_bio, mask=mask_bio, prompt=prompt, size=size)
            else:
                resp = cli.images.edit(model="gpt-image-1", image=img_bio, prompt=prompt, size=size)
        else:
            if mask_bio:
                resp = cli.images.edit(model="gpt-image-1", image=img_bio, mask=mask_bio, prompt=prompt, size=size)
            else:
                resp = cli.images.edit(model="gpt-image-1", image=img_bio, prompt=prompt, size=size)
        b64 = resp.data[0].b64_json
        return base64.b64decode(b64)
    except Exception as e:
        _handle_moderation_and_reraise(e)