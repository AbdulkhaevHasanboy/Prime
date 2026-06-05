"""
Quantum VRM - Python Backend (FastAPI)
======================================

Exact Python port of the VRM_1 Node/Vite server layer. It serves the SAME
prebuilt frontend (in ./dist) and reimplements every backend endpoint the
browser app calls, byte-for-byte compatible with the original:

    GET  /api/get-token              -> Gemini Live ephemeral auth token (+ per-IP rate limit)
    GET  /api/search-image?q=...     -> multi-strategy image search (DDG -> Unsplash -> Wikimedia -> LoremFlickr)
    GET  /api/proxy-image?url=...    -> image proxy (streams upstream image bytes)
    GET|POST /api/telegram/<method>  -> Telegram Bot API relay (sendMessage/sendPhoto/sendVideo/sendDocument/getUpdates)

The 3D VRM rendering, Gemini Live WebRTC voice chat and glassmorphic UI all
run in the browser exactly as before (served from ./dist). Only the Node server
has been replaced with this Python (FastAPI/uvicorn) server.

Run:
    pip install -r requirements.txt
    python server.py            # http://localhost:5173
    python server.py --ssl      # https://localhost:5173 (self-signed; needed for LAN camera/mic)
"""

import argparse
import os
import mimetypes
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlencode

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"   # original Vue build — kept only for VRM assets (models/animations)
WEB_DIR = BASE_DIR / "web"     # PyScript (Python-in-browser) frontend — the served app

# Load .env (same variables the Node/Vite server consumed)
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="Quantum VRM - Python Backend")
# Compress text assets (JS, CSS, JSON, Python source) in transit; skip already-compressed
# formats like .wasm and .whl (gzip overhead would increase their size).
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Browser-like UA strings, copied verbatim from the original server for parity.
UA_CHROME_119 = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
)
UA_CHROME_122 = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

TELEGRAM_API_BASE = "https://api.telegram.org"
ALLOWED_TELEGRAM_METHODS = {
    "sendMessage",
    "sendPhoto",
    "sendVideo",
    "sendDocument",
    "getUpdates",
}

# Fixed "Report Bot" credentials, mirrored from the original relay middleware.
REPORT_TOKEN = "7496849798:AAGv1q5BZslsaP_EMJstgYZoCMAXqpyj6f8"
REPORT_CHAT_ID = "7019597244"


# ---------------------------------------------------------------------------
# /api/get-token  -- Gemini Live ephemeral token + per-IP rate limiting
# ---------------------------------------------------------------------------

# In-memory IP rate-limit cache: { ip: {"count": int, "reset_time": epoch_seconds} }
_rate_limit_cache: dict[str, dict] = {}
_RL_WINDOW_S = 60          # 1 minute window
_RL_MAX_REQUESTS = 5       # max 5 token generations / minute / IP


def _client_ip(request: Request) -> str:
    return (
        request.headers.get("x-real-ip")
        or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        or (request.client.host if request.client else "")
        or "unknown-ip"
    )


@app.get("/api/get-token")
async def get_token(request: Request):
    client_ip = _client_ip(request)
    now = time.time()

    ip_data = _rate_limit_cache.get(client_ip)
    if not ip_data or now > ip_data["reset_time"]:
        ip_data = {"count": 0, "reset_time": now + _RL_WINDOW_S}

    ip_data["count"] += 1
    _rate_limit_cache[client_ip] = ip_data

    # Opportunistic cleanup of expired entries (replaces the Node setInterval sweep)
    for ip in [k for k, v in _rate_limit_cache.items() if now > v["reset_time"]]:
        _rate_limit_cache.pop(ip, None)

    if ip_data["count"] > _RL_MAX_REQUESTS:
        retry_after = max(0, int(round(ip_data["reset_time"] - now)))
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={
                "error": "Too many requests. Quota protection active. Please try again in a minute."
            },
        )

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("VITE_API_KEY")
    if not api_key:
        return JSONResponse(
            status_code=500,
            content={"error": "GEMINI_API_KEY is not configured on server env."},
        )

    rl_headers = {
        "X-RateLimit-Limit": str(_RL_MAX_REQUESTS),
        "X-RateLimit-Remaining": str(max(0, _RL_MAX_REQUESTS - ip_data["count"])),
        "X-RateLimit-Reset": str(int(round(ip_data["reset_time"]))),
    }

    try:
        token_name = await _create_ephemeral_token(api_key)
        return JSONResponse(status_code=200, headers=rl_headers, content={"token": token_name})
    except Exception as error:  # noqa: BLE001 - mirror original broad catch
        print(f"Server failed to generate token: {error}")
        return JSONResponse(status_code=500, content={"error": str(error) or "Token generation failed."})


async def _create_ephemeral_token(api_key: str) -> str:
    """
    Create a single-use Gemini Live ephemeral token, matching the original:
        uses=1, expireTime=+30min, newSessionExpireTime=+1min, apiVersion=v1alpha
    Uses the official google-genai SDK; falls back to the v1alpha REST endpoint.
    """
    now = datetime.now(timezone.utc)
    expire_time = now + timedelta(minutes=30)
    new_session_expire_time = now + timedelta(minutes=1)

    # Preferred path: official SDK (kept in sync with the JS @google/genai client).
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(api_version="v1alpha"),
        )
        token = await client.aio.auth_tokens.create(
            config=types.CreateAuthTokenConfig(
                uses=1,
                expire_time=expire_time,
                new_session_expire_time=new_session_expire_time,
            )
        )
        return token.name
    except Exception as sdk_error:  # noqa: BLE001
        # Fallback: direct REST call to the v1alpha auth token endpoint.
        try:
            payload = {
                "uses": 1,
                "expireTime": expire_time.isoformat().replace("+00:00", "Z"),
                "newSessionExpireTime": new_session_expire_time.isoformat().replace("+00:00", "Z"),
            }
            url = "https://generativelanguage.googleapis.com/v1alpha/auth_tokens"
            async with httpx.AsyncClient(timeout=30) as hc:
                resp = await hc.post(
                    url,
                    params={"key": api_key},
                    json=payload,
                    headers={"content-type": "application/json"},
                )
            resp.raise_for_status()
            data = resp.json()
            name = data.get("name")
            if not name:
                raise RuntimeError(f"Unexpected token response: {data}")
            return name
        except Exception as rest_error:  # noqa: BLE001
            raise RuntimeError(
                f"Token creation failed (sdk: {sdk_error}; rest: {rest_error})"
            ) from rest_error


# ---------------------------------------------------------------------------
# /api/search-image  -- multi-strategy keyless image search
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "a", "an", "the", "and", "with", "for", "from", "under", "above", "near", "beside", "in", "on", "at", "of",
    "photo", "image", "picture", "stock", "dramatic", "scenic", "sunset", "sunrise", "sunny", "landscape",
    "view", "background", "beautiful", "gorgeous", "hd", "4k", "taking", "off", "shot", "action", "illustration",
    "generative", "ai", "realistic", "wallpaper", "art",
}


@app.get("/api/search-image")
async def search_image(request: Request):
    query = request.query_params.get("q")
    if not query:
        return JSONResponse(status_code=400, content={"error": "Query parameter q is required"})

    # 1. Clean and extract key descriptive nouns from the query
    cleaned = re.sub(r"[^a-z0-9\s]", "", query.strip().lower())
    words = [w for w in re.split(r"\s+", cleaned) if len(w) > 2 and w not in _STOPWORDS]

    ddg_query = " ".join(words[:4]) or query.strip()
    wikimedia_query = " ".join(words[:2]) or "landscape"
    lorem_flickr_tag = words[0] if words else "landscape"

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as hc:
        vqd = None

        # Strategy 1: fetch DuckDuckGo VQD token
        try:
            r = await hc.get(
                "https://duckduckgo.com/",
                params={"q": ddg_query},
                headers={
                    "User-Agent": UA_CHROME_122,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Cache-Control": "no-cache",
                    "Referer": "https://duckduckgo.com/",
                },
            )
            html = r.text
            m = (
                re.search(r"vqd\s*=\s*['\"]?([^'&\"<>]+)['\"]?", html)
                or re.search(r"vqd\s*:\s*['\"]?([^'&\"<>]+)['\"]?", html)
                or re.search(r"vqd=([^&'\"]+)", html)
            )
            if m:
                vqd = m.group(1)
        except Exception as e:  # noqa: BLE001
            print(f"DuckDuckGo VQD fetch failed, trying fallbacks: {e}")

        # Strategy 2: DuckDuckGo image search using VQD
        if vqd:
            try:
                r = await hc.get(
                    "https://duckduckgo.com/i.js",
                    params={"q": ddg_query, "o": "json", "vqd": vqd},
                    headers={"User-Agent": UA_CHROME_122, "Referer": "https://duckduckgo.com/"},
                )
                data = r.json()
                if data and data.get("results"):
                    return JSONResponse(status_code=200, content=data)
            except Exception as e:  # noqa: BLE001
                print(f"DuckDuckGo image search query failed, trying fallback: {e}")

        # Strategy 3: Unsplash public napi search
        try:
            r = await hc.get(
                "https://unsplash.com/napi/search/photos",
                params={"query": ddg_query, "per_page": 15},
                headers={"User-Agent": UA_CHROME_122, "Referer": "https://unsplash.com/"},
            )
            if r.status_code == 200:
                data = r.json()
                if data and data.get("results"):
                    results = [
                        {
                            "title": (rr.get("alt_description") or rr.get("description") or "Unsplash Image"),
                            "image": rr["urls"]["regular"],
                        }
                        for rr in data["results"]
                    ]
                    return JSONResponse(status_code=200, content={"results": results})
        except Exception as e:  # noqa: BLE001
            print(f"Unsplash public search failed, trying next fallback: {e}")

        # Strategy 4: Wikimedia Commons API
        try:
            r = await hc.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "generator": "search",
                    "gsrsearch": wikimedia_query,
                    "gsrnamespace": "6",  # File namespace
                    "prop": "imageinfo",
                    "iiprop": "url|mime",
                    "gsrlimit": "15",
                    "origin": "*",
                },
            )
            data = r.json()
            pages = (data.get("query") or {}).get("pages")
            if pages:
                results = []
                for p in pages.values():
                    info = p.get("imageinfo")
                    if not info:
                        continue
                    mime = info[0].get("mime") or ""
                    if mime in ("image/jpeg", "image/png"):
                        results.append(
                            {"title": p.get("title") or "Wikimedia Commons Image", "image": info[0]["url"]}
                        )
                if results:
                    return JSONResponse(status_code=200, content={"results": results})
        except Exception as e:  # noqa: BLE001
            print(f"Wikimedia fallback search failed: {e}")

    # Strategy 5: LoremFlickr single-tag guaranteed fallback
    random_seed = random.randint(0, 999999)
    fallback_image = f"https://loremflickr.com/1024/576/{lorem_flickr_tag}?random={random_seed}"
    return JSONResponse(
        status_code=200,
        content={
            "results": [
                {"title": f"Fallback background matching: {lorem_flickr_tag}", "image": fallback_image}
            ]
        },
    )


# ---------------------------------------------------------------------------
# /api/proxy-image  -- stream an upstream image through, with a spoofed UA/Referer
# ---------------------------------------------------------------------------

@app.get("/api/proxy-image")
async def proxy_image(request: Request):
    image_url = request.query_params.get("url")
    if not image_url:
        return JSONResponse(status_code=400, content={"error": "url parameter is required"})

    referer_header = ""
    try:
        parsed = urlparse(image_url)
        if parsed.scheme and parsed.netloc:
            referer_header = f"{parsed.scheme}://{parsed.netloc}/"
    except Exception as e:  # noqa: BLE001
        print(f"Failed to parse proxy image url origin: {e}")

    headers = {"User-Agent": UA_CHROME_119, "Accept": "image/*,*/*"}
    if referer_header:
        headers["Referer"] = referer_header

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as hc:
            resp = await hc.get(image_url, headers=headers)
            if resp.status_code != 200:
                return JSONResponse(
                    status_code=resp.status_code,
                    content={"error": f"Upstream returned {resp.status_code}"},
                )
            content_type = resp.headers.get("content-type") or "image/jpeg"
            return Response(
                content=resp.content,
                status_code=200,
                media_type=content_type,
                headers={"cache-control": "public, max-age=86400"},
            )
    except Exception as error:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(error) or "Proxy failed."})


# ---------------------------------------------------------------------------
# /api/telegram/<method>  -- Telegram Bot API relay (GET + POST)
# ---------------------------------------------------------------------------

async def _relay_telegram(request: Request, method_name: str) -> Response:
    if not method_name or method_name not in ALLOWED_TELEGRAM_METHODS:
        return JSONResponse(status_code=404, content={"ok": False, "error": "Unknown Telegram method."})

    is_report = request.headers.get("x-telegram-bot-type") == "report"

    if is_report:
        token = REPORT_TOKEN
        target_chat_id = REPORT_CHAT_ID
    else:
        token = str(os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        target_chat_id = str(os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

    if not token:
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": (
                    "Report Bot Token Missing"
                    if is_report
                    else "Telegram relay is not configured. Set TELEGRAM_BOT_TOKEN on server env."
                ),
            },
        )

    method = request.method.upper()
    if method not in ("GET", "POST"):
        return JSONResponse(
            status_code=405,
            headers={"allow": "GET, POST"},
            content={"ok": False, "error": "Method not allowed."},
        )

    # Build query params; override/inject chat_id when configured.
    query_obj = dict(request.query_params)
    if target_chat_id:
        query_obj["chat_id"] = target_chat_id

    query_string = f"?{urlencode(query_obj)}" if query_obj else ""
    upstream_url = f"{TELEGRAM_API_BASE}/bot{token}/{method_name}{query_string}"

    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as hc:
            if method == "GET":
                upstream = await hc.get(upstream_url)
            else:
                body = await request.body()
                fwd_headers = {}
                ct = request.headers.get("content-type")
                if ct:
                    fwd_headers["content-type"] = ct
                upstream = await hc.post(upstream_url, content=body, headers=fwd_headers or None)

        upstream_type = upstream.headers.get("content-type") or "application/json; charset=utf-8"
        return Response(content=upstream.content, status_code=upstream.status_code, media_type=upstream_type)
    except Exception as error:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"ok": False, "error": str(error) or "Telegram relay failed."})


@app.api_route("/api/telegram/{method_name}", methods=["GET", "POST"])
async def telegram_relay(request: Request, method_name: str):
    return await _relay_telegram(request, method_name)


# ---------------------------------------------------------------------------
# /api/config -- expose server-side VITE_* env to the Python frontend
# (replaces Vite's build-time import.meta.env injection)
# ---------------------------------------------------------------------------

@app.get("/api/config")
async def get_config():
    env = {k: v for k, v in os.environ.items() if k.startswith("VITE_")}
    # The frontend ConfigManager expects VITE_API_KEY; mirror it from server keys
    # if only the non-prefixed name is set (the browser never sees the real key —
    # live sessions use the ephemeral token from /api/get-token).
    if "VITE_API_KEY" not in env and os.environ.get("GEMINI_API_KEY"):
        env["VITE_API_KEY"] = ""  # intentionally blank in the browser
    return JSONResponse(content=env)


# ---------------------------------------------------------------------------
# Static frontend (the PyScript app in ./web) + VRM assets (./dist) + SPA fallback
# ---------------------------------------------------------------------------

# Long-lived immutable cache for hashed VRM assets (matches vercel.json rule).
_IMMUTABLE_PREFIXES = ("models/", "animations/")
# Paths that live in the original dist/ (VRM models, animations, favicon).
_DIST_PREFIXES = ("models/", "animations/")


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    rel = full_path or "index.html"

    # 1. VRM assets (models/, animations/, image.ico) come from dist/.
    if rel.startswith(_DIST_PREFIXES) or rel == "image.ico":
        dist_candidate = (DIST_DIR / rel).resolve()
        try:
            dist_candidate.relative_to(DIST_DIR.resolve())
            if dist_candidate.is_file():
                headers = {}
                if any(rel.startswith(p) for p in _IMMUTABLE_PREFIXES):
                    headers["Cache-Control"] = "public, max-age=31536000, immutable"
                return FileResponse(dist_candidate, headers=headers)
        except ValueError:
            pass

    # 2. Everything else is the PyScript frontend in web/.
    web_candidate = (WEB_DIR / rel).resolve()
    try:
        web_candidate.relative_to(WEB_DIR.resolve())
        if web_candidate.is_file():
            headers = {}
            if rel.startswith("libs/"):
                # Pinned versioned assets (Pyodide, numpy wheel, vendor bundle) never change —
                # tell the browser to cache them for a year so repeat visits skip all downloads.
                headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return FileResponse(web_candidate, headers=headers)
    except ValueError:
        pass

    # 3. A request for a concrete asset (has a file extension) that was not found
    #    must 404 — NOT fall through to index.html. Otherwise loaders (e.g. the
    #    .vrma animation loader) receive HTML and fail with a parse error instead
    #    of cleanly triggering their remote fallback.
    last_segment = rel.rsplit("/", 1)[-1]
    if "." in last_segment:
        return JSONResponse(status_code=404, content={"error": f"Not found: /{rel}"})

    # 4. SPA fallback -> index.html (extensionless route paths only)
    return FileResponse(WEB_DIR / "index.html")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="VRM - Python backend server")
    parser.add_argument("--host", default="localhost", help="bind host (default: 0.0.0.0, like Vite host:true)")
    parser.add_argument("--port", type=int, default=5173, help="bind port (default: 5173)")
    parser.add_argument(
        "--ssl",
        action="store_true",
        help="serve over HTTPS with an auto-generated self-signed cert (needed for camera/mic over LAN IP)",
    )
    args = parser.parse_args()

    import uvicorn

    ssl_kwargs = {}
    if args.ssl:
        cert_file = BASE_DIR / "_selfsigned_cert.pem"
        key_file = BASE_DIR / "_selfsigned_key.pem"
        if not (cert_file.exists() and key_file.exists()):
            _generate_self_signed_cert(cert_file, key_file)
        ssl_kwargs = {"ssl_certfile": str(cert_file), "ssl_keyfile": str(key_file)}

    scheme = "https" if args.ssl else "http"
    print(f"Quantum VRM (Python) serving on {scheme}://localhost:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, **ssl_kwargs)


def _generate_self_signed_cert(cert_file: Path, key_file: Path):
    """Generate a self-signed cert (mirrors @vitejs/plugin-basic-ssl) using cryptography."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_file.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Generated self-signed cert: {cert_file.name}, {key_file.name}")


if __name__ == "__main__":
    main()
