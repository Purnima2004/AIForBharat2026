import os
import uuid
import json
import time
import threading
import requests
import base64
import shutil
from io import BytesIO
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/ai-video")
CALLBACK_URL = os.getenv("CALLBACK_URL", "http://localhost:5000/callback")
FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))
OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), "outputs")

os.makedirs(OUTPUTS_DIR, exist_ok=True)

# In-memory job store
jobs = {}

# ───────────────────────────── ROUTES ──────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/generate", methods=["POST"])
def generate():
    """Receive user prompt, create job, trigger n8n webhook or direct pipeline."""
    data = request.get_json()
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "step": "starting",
        "enhancedPrompt": "",
        "images": [],
        "videoUrl": None,
        "error": None,
        "created_at": time.time()
    }

    # Run the pipeline in background thread
    t = threading.Thread(target=run_pipeline, args=(job_id, prompt), daemon=True)
    t.start()

    return jsonify({"jobId": job_id})

@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    """Poll job status."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)

@app.route("/callback", methods=["POST"])
def callback():
    """n8n webhook posts result here (optional path if using n8n)."""
    data = request.get_json()
    job_id = data.get("jobId")
    if job_id and job_id in jobs:
        jobs[job_id].update(data)
    return jsonify({"ok": True})

@app.route("/outputs/<path:filename>")
def serve_output(filename):
    """Serve generated video / image files."""
    return send_from_directory(OUTPUTS_DIR, filename)

@app.route("/download/<path:filename>")
def download_file(filename):
    """Force-download a file."""
    path = os.path.join(OUTPUTS_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True)

# ───────────────────────────── PIPELINE ──────────────────────────────

def run_pipeline(job_id: str, raw_prompt: str):
    """Full AI pipeline: enhance → generate images → image-to-video."""
    try:
        # ── STEP 1: Enhance the prompt with Gemini Flash ──
        update_job(job_id, step="enhancing", status="processing")
        enhanced = enhance_prompt(raw_prompt)
        update_job(job_id, enhancedPrompt=enhanced, step="enhanced")

        # ── STEP 2: Skip Image Generation (Direct to Video) ──
        update_job(job_id, step="generating_images") # Keep step name for UI compatibility, but skip
        image_urls = []
        image_paths = []
        update_job(job_id, images=image_urls, step="images_done")

        # ── STEP 3: Create Video ──
        update_job(job_id, step="creating_video")
        video_path = generate_video(job_id, enhanced, image_paths)
        video_url = f"/outputs/{os.path.basename(video_path)}"

        update_job(job_id, videoUrl=video_url, step="done", status="done")

    except Exception as e:
        error_msg = sanitize_error_message(str(e))
        # Provide user-friendly error messages
        if "rate limit" in error_msg.lower() or "429" in error_msg:
            user_error = "Rate limit exceeded. The API is temporarily unavailable. Please wait a few minutes and try again."
        elif "timeout" in error_msg.lower():
            user_error = "Request timed out. Please try again with a shorter prompt or wait a moment."
        else:
            user_error = f"An error occurred: {error_msg}"
        
        update_job(job_id, status="error", error=user_error, step="error")
        print(f"[Pipeline Error] job={job_id}: {error_msg}")


def update_job(job_id: str, **kwargs):
    if job_id in jobs:
        jobs[job_id].update(kwargs)


# ───────────────────────────── GEMINI PROMPT ENHANCEMENT ──────────────────────────────

def local_fallback_enhance(raw_prompt: str) -> str:
    """Offline cinematic prompt enhancer — used when Gemini is rate-limited."""
    styles = [
        "cinematic lighting, golden hour, shallow depth of field, 4K ultra-detailed",
        "dramatic shadows, volumetric light rays, photorealistic, anamorphic lens flare",
        "soft diffused natural light, rich color grading, atmospheric haze, film grain",
    ]
    motions = [
        "slow dolly zoom, camera tracks forward, smooth handheld motion",
        "sweeping crane shot, slow pan left, subtle push-in",
        "orbital camera movement, gentle tilt up, cinematic rack focus",
    ]
    import random
    style  = random.choice(styles)
    motion = random.choice(motions)
    enhanced = (
        f"{raw_prompt}. {style}. {motion}. "
        "Hyper-realistic textures, emotionally evocative scene, "
        "professional color palette with deep blacks and vibrant highlights."
    )
    print(f"[Enhance] Using local fallback for: '{raw_prompt[:60]}'")
    return enhanced


def sanitize_error_message(error_msg: str) -> str:
    """Remove API keys and sensitive URLs from error messages."""
    import re
    # Remove API key from URLs
    error_msg = re.sub(r'key=[A-Za-z0-9_-]+', 'key=***', error_msg)
    # Remove full URLs with keys
    error_msg = re.sub(r'https://[^\s]+key=[^\s]+', 'https://***', error_msg)
    return error_msg


def gemini_post_with_retry(url: str, body: dict, timeout: int = 30,
                           max_retries: int = 5, base_wait: float = 20.0) -> dict:
    """POST to Gemini API with exponential backoff on 429 / 5xx errors."""
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, json=body, timeout=timeout)
            if resp.status_code == 429:
                if attempt < max_retries - 1:
                    wait = base_wait * (2 ** attempt)
                    print(f"[Gemini] 429 rate-limited. Waiting {wait:.0f}s (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue
                else:
                    raise RuntimeError("Rate limit exceeded. Please wait a few minutes and try again.")
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            last_error = e
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                if attempt < max_retries - 1:
                    wait = base_wait * (2 ** attempt)
                    print(f"[Gemini] 429 rate-limited. Waiting {wait:.0f}s (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue
                else:
                    raise RuntimeError("Rate limit exceeded. Please wait a few minutes and try again.")
            if attempt == max_retries - 1:
                break
            wait = base_wait * (2 ** attempt)
            print(f"[Gemini] HTTP error: {sanitize_error_message(str(e))}. Retrying in {wait:.0f}s")
            time.sleep(wait)
        except Exception as e:
            last_error = e
            if attempt == max_retries - 1:
                break
            wait = base_wait * (2 ** attempt)
            print(f"[Gemini] Error: {sanitize_error_message(str(e))}. Retrying in {wait:.0f}s")
            time.sleep(wait)
    
    # Return a user-friendly error message
    if last_error and hasattr(last_error, 'response') and hasattr(last_error.response, 'status_code') and last_error.response.status_code == 429:
        raise RuntimeError("Rate limit exceeded. Please wait a few minutes and try again.")
    raise RuntimeError(f"API request failed after {max_retries} attempts. Please try again later.")


def enhance_prompt(raw_prompt: str) -> str:
    """Use Gemini Flash to enhance raw prompt into a detailed cinematic one.
    Falls back to local enhancement if API is rate-limited."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    system_instruction = (
        "You are a world-class AI video director and prompt engineer. "
        "Transform the user's simple idea into a rich, detailed, cinematic video prompt. "
        "Include: vivid scene description, lighting, mood, camera movement, color palette, "
        "textures, emotional tone, and any dialogue or narration if relevant. "
        "Output only the enhanced prompt text — no explanations, no preamble."
    )
    body = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"parts": [{"text": raw_prompt}]}]
    }
    try:
        result = gemini_post_with_retry(url, body, timeout=30, max_retries=5, base_wait=20.0)
        enhanced = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"[Enhance] '{raw_prompt[:60]}' → '{enhanced[:80]}...'")
        return enhanced
    except Exception as e:
        error_msg = sanitize_error_message(str(e))
        print(f"[Enhance] Gemini failed ({error_msg}) — using local fallback")
        return local_fallback_enhance(raw_prompt)


# ───────────────────────────── IMAGE GENERATION (FREE TIER) ──────────────────────────────

def _save_image_bytes(job_id: str, img_bytes: bytes, index: int) -> str:
    """Save raw image bytes to the outputs directory and return the file path."""
    fname = f"{job_id}_img_{index}.png"
    fpath = os.path.join(OUTPUTS_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(img_bytes)
    print(f"[Image] Saved image {index}: {fname}")
    return fpath


def _gemini_flash_generate_image(prompt: str, seed: int = 0) -> bytes:
    """Generate a single image via Gemini 2.0 Flash (free tier).
    Returns raw PNG bytes, or raises on failure."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.0-flash-exp-image-generation:generateContent"
        f"?key={GEMINI_API_KEY}"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
            "seed": seed
        }
    }
    resp = requests.post(url, json=body, timeout=120)
    if resp.status_code == 429:
        raise RuntimeError(f"429 rate-limited")
    resp.raise_for_status()
    data = resp.json()
    # Walk the parts looking for inlineData image
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData", {})
            if inline.get("mimeType", "").startswith("image/"):
                return base64.b64decode(inline["data"])
    raise RuntimeError("Gemini Flash returned no image data")


def _pollinations_generate_image(prompt: str, width: int = 576, height: int = 1024, seed: int = 0) -> bytes:
    """Generate a single image via Pollinations.ai (completely free, no key needed)."""
    import urllib.parse
    encoded = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&seed={seed}&nologo=true&model=flux"
    )
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    if not resp.headers.get("Content-Type", "").startswith("image/"):
        raise RuntimeError("Pollinations returned non-image response")
    return resp.content


def generate_images(job_id: str, prompt: str, count: int = 4) -> list:
    """Generate images using Gemini 2.0 Flash (free tier) with Pollinations.ai fallback.
    
    Strategy:
      1. Try Gemini 2.0 Flash image generation (free quota, same API key).
      2. If Gemini fails for any image, fall back to Pollinations.ai (no key, always free).
    """
    image_paths = []
    use_pollinations = False  # flip to True if Gemini fails on first attempt

    for i in range(1, count + 1):
        seed = i * 42  # different seed per image for variety
        saved = False

        # ── Try Gemini 2.0 Flash first ──
        if not use_pollinations:
            for attempt in range(3):
                try:
                    print(f"[Gemini-Img] Generating image {i}/{count} (attempt {attempt+1})...")
                    img_bytes = _gemini_flash_generate_image(prompt, seed=seed)
                    fpath = _save_image_bytes(job_id, img_bytes, i)
                    image_paths.append(fpath)
                    saved = True
                    break
                except RuntimeError as e:
                    err = str(e)
                    if "429" in err:
                        wait = 15 * (2 ** attempt)
                        print(f"[Gemini-Img] Rate-limited. Waiting {wait}s...")
                        time.sleep(wait)
                    else:
                        print(f"[Gemini-Img] Failed: {sanitize_error_message(err)}. Switching to Pollinations fallback.")
                        use_pollinations = True
                        break
                except Exception as e:
                    print(f"[Gemini-Img] Unexpected error: {sanitize_error_message(str(e))}. Switching to Pollinations.")
                    use_pollinations = True
                    break

        # ── Pollinations.ai fallback ──
        if not saved:
            for attempt in range(3):
                try:
                    print(f"[Pollinations] Generating image {i}/{count} (attempt {attempt+1})...")
                    img_bytes = _pollinations_generate_image(prompt, seed=seed)
                    fpath = _save_image_bytes(job_id, img_bytes, i)
                    image_paths.append(fpath)
                    saved = True
                    break
                except Exception as e:
                    wait = 10 * (attempt + 1)
                    print(f"[Pollinations] Error: {sanitize_error_message(str(e))}. Retrying in {wait}s...")
                    time.sleep(wait)

        if not saved:
            print(f"[Image] WARNING: Could not generate image {i} after all retries. Skipping.")

    if not image_paths:
        raise RuntimeError("Image generation failed: all providers returned errors. Please try again.")

    print(f"[Image] Generated {len(image_paths)}/{count} images successfully.")
    return image_paths


# ───────────────────────────── VIDEO GENERATION ──────────────────────────────

def generate_video(job_id: str, prompt: str, image_paths: list) -> str:
    """Strategy: Free Text-to-Video Fallback -> FFmpeg Slideshow (if applicable)"""
    try:
        return generate_video_free_fallback(job_id, prompt)
    except Exception as e:
        error_msg = sanitize_error_message(str(e))
        print(f"[Fallback Video] Failed ({error_msg}).")
        if image_paths:
            print("Using FFmpeg slideshow fallback.")
            return generate_video_ffmpeg(job_id, image_paths)
        else:
            raise RuntimeError("Free text-to-video generation failed and no images are available for fallback.")


def generate_video_free_fallback(job_id: str, prompt: str) -> str:
    """Generates an MP4 video from text using Pollinations API (completely free)."""
    import urllib.parse
    print("[Pollinations] Starting free text-to-video generation...")
    # Add cinematic keywords to help the text-to-video model
    enhanced = f"masterpiece video, {prompt}, highly detailed, smooth motion"
    encoded = urllib.parse.quote(enhanced)
    url = f"https://image.pollinations.ai/prompt/{encoded}?model=video"

    resp = requests.get(url, timeout=120)
    resp.raise_for_status()

    # The result may be a direct MP4 file
    if not resp.headers.get("Content-Type", "").startswith("video/"):
        raise RuntimeError("Received non-video response from Pollinations")

    fname = f"{job_id}_video.mp4"
    fpath = os.path.join(OUTPUTS_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(resp.content)
    print(f"[Pollinations] Saved free AI video: {fname}")
    return fpath
    """Generate high-quality video using Gemini Veo 2 API (Image-to-Video)."""
    # Read and encode the first image
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    # Submit the video generation job
    submit_url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/veo-2.0-generate-001:predictLongRunning?key={GEMINI_API_KEY}"
    )
    body = {
        "instances": [{
            "prompt": prompt,
            "image": {
                "bytesBase64Encoded": img_b64,
                "mimeType": "image/png"
            }
        }],
        "parameters": {
            "aspectRatio": "16:9",
            "durationSeconds": 8,
            "sampleCount": 1
        }
    }
    
    # Retry submission with backoff for rate limits
    max_submit_retries = 3
    base_wait = 15.0
    resp = None
    for attempt in range(max_submit_retries):
        try:
            resp = requests.post(submit_url, json=body, timeout=60)
            if resp.status_code == 429:
                if attempt < max_submit_retries - 1:
                    wait = base_wait * (2 ** attempt)
                    print(f"[Veo 2] 429 rate-limited on submit. Waiting {wait:.0f}s")
                    time.sleep(wait)
                    continue
                else:
                    raise RuntimeError("Rate limit exceeded for Gemini Veo 2 generation")
            resp.raise_for_status()
            break
        except requests.exceptions.HTTPError as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                if attempt < max_submit_retries - 1:
                    wait = base_wait * (2 ** attempt)
                    print(f"[Veo 2] 429 rate-limited on submit. Waiting {wait:.0f}s")
                    time.sleep(wait)
                    continue
                else:
                    raise RuntimeError("Rate limit exceeded for Gemini Veo 2 generation")
            if attempt == max_submit_retries - 1:
                raise
            wait = base_wait * (2 ** attempt)
            print(f"[Veo 2] Submit error: {sanitize_error_message(str(e))}. Retrying...")
            time.sleep(wait)
    
    if resp is None:
        raise RuntimeError("Failed to submit Gemini Veo video job")
    
    operation = resp.json()
    operation_name = operation.get("name", "")
    print(f"[Veo 2] Operation started: {operation_name}")

    # Poll until complete (up to 5 minutes)
    poll_url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"{operation_name}?key={GEMINI_API_KEY}"
    )
    for attempt in range(60):
        time.sleep(5)
        try:
            poll_resp = requests.get(poll_url, timeout=30)
            if poll_resp.status_code == 429:
                print(f"[Veo 2] 429 rate-limited on poll. Waiting 30s...")
                time.sleep(30)
                continue
            poll_resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                print(f"[Veo 2] 429 rate-limited on poll. Waiting 30s...")
                time.sleep(30)
                continue
            raise
        
        poll_data = poll_resp.json()

        if poll_data.get("done"):
            # Extract video bytes
            predictions = poll_data.get("response", {}).get("predictions", [])
            if predictions:
                video_b64 = predictions[0].get("bytesBase64Encoded", "")
                if video_b64:
                    video_data = base64.b64decode(video_b64)
                    fname = f"{job_id}_video.mp4"
                    fpath = os.path.join(OUTPUTS_DIR, fname)
                    with open(fpath, "wb") as f:
                        f.write(video_data)
                    print(f"[Veo 2] Video saved: {fname}")
                    return fpath
            raise RuntimeError("Veo 2 returned done but no video data")

        print(f"[Veo 2] Polling attempt {attempt+1}/60...")
        
    raise RuntimeError("Gemini Veo generation timed out after 5 minutes.")


def generate_video_ffmpeg(job_id: str, image_paths: list) -> str:
    """Create a slideshow MP4 from images using FFmpeg."""
    import subprocess

    # Build a file list for FFmpeg concat
    list_path = os.path.join(OUTPUTS_DIR, f"{job_id}_filelist.txt")
    with open(list_path, "w") as f:
        for img in image_paths:
            # Each image shown for 2 seconds
            f.write(f"file '{img.replace(chr(92), '/')}'\n")
            f.write(f"duration 2\n")
        # Repeat last frame at end
        f.write(f"file '{image_paths[-1].replace(chr(92), '/')}'\n")

    out_path = os.path.join(OUTPUTS_DIR, f"{job_id}_video.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_path,
        "-vf", "fps=30,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "fast", "-crf", "23",
        out_path
    ]
    print(f"[FFmpeg] Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"[FFmpeg] Non-zero exit ({result.returncode}): {result.stderr[:300]}")
            return generate_gif_fallback(job_id, image_paths)
        os.remove(list_path)
        print(f"[FFmpeg] Slideshow saved: {out_path}")
        return out_path
    except FileNotFoundError:
        # FFmpeg is not installed on this system → use PIL GIF fallback
        print("[FFmpeg] Not installed (FileNotFoundError). Using GIF fallback.")
        return generate_gif_fallback(job_id, image_paths)
    except Exception as e:
        print(f"[FFmpeg] Unexpected error: {e}. Using GIF fallback.")
        return generate_gif_fallback(job_id, image_paths)


def generate_gif_fallback(job_id: str, image_paths: list) -> str:
    """Pure Python: stitch images into animated GIF (no FFmpeg needed)."""
    from PIL import Image as PILImage

    frames = []
    target_size = (1280, 720)

    for p in image_paths:
        img = PILImage.open(p).convert("RGB")
        img.thumbnail(target_size, PILImage.LANCZOS)
        # Pad to exact size
        background = PILImage.new("RGB", target_size, (0, 0, 0))
        x = (target_size[0] - img.width) // 2
        y = (target_size[1] - img.height) // 2
        background.paste(img, (x, y))
        frames.append(background)

    out_path = os.path.join(OUTPUTS_DIR, f"{job_id}_video.gif")
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=2000,   # 2 seconds per frame
        loop=0
    )
    print(f"[GIF Fallback] Saved: {out_path}")
    return out_path


# ───────────────────────────── MAIN ──────────────────────────────

if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  🎬  AI Video Generation Studio")
    print(f"  API Key: {'✅ Set' if GEMINI_API_KEY and GEMINI_API_KEY != 'your_gemini_api_key_here' else '❌ NOT SET — edit .env!'}")
    print(f"  Backend: http://localhost:{FLASK_PORT}")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=False)
