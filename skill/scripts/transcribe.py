#!/usr/bin/env python3
"""
小宇宙播客转录脚本
将小宇宙播客链接转录为逐字稿 .txt 文件

用法:
    python transcribe.py <url1> [url2] [url3] ... --api-key <QWEN_API_KEY> --output-dir <DIR>

示例:
    python transcribe.py https://www.xiaoyuzhou.fm/episode/xxx --api-key sk-xxx --output-dir ./transcripts
"""

import argparse
import http.client
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request


# ──────────────────────────────────────────────
# 1. 从小宇宙获取节目信息
# ──────────────────────────────────────────────

def get_xiaoyuzhou_info(episode_url: str) -> dict:
    """
    从小宇宙播客页面解析节目元数据（标题、音频URL等）。
    通过解析页面 HTML 中的 __NEXT_DATA__ JSON 实现。

    返回 dict：
        title         节目标题
        podcast_name  播客节目名称
        enclosure_url 音频文件下载地址
        description   节目描述（可能较长）
        pub_date      发布时间
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    req = urllib.request.Request(episode_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        raise RuntimeError(f"无法访问小宇宙页面 {episode_url}: {e}")

    # 提取 __NEXT_DATA__
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError(
            f"页面中未找到 __NEXT_DATA__，小宇宙可能更改了页面结构。URL: {episode_url}"
        )

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"__NEXT_DATA__ JSON 解析失败: {e}")

    # 在 pageProps 中查找 episode 对象
    props = data.get("props", {}).get("pageProps", {})

    episode = props.get("episode") or props.get("episodeDetail", {}).get("episode")
    if not episode:
        # 尝试更深层的嵌套
        for key, val in props.items():
            if isinstance(val, dict) and "enclosureUrl" in val:
                episode = val
                break

    if not episode:
        raise RuntimeError(
            "在 __NEXT_DATA__ 中未找到 episode 对象，请检查页面结构。"
        )

    enclosure_url = episode.get("enclosureUrl") or episode.get("media", {}).get("url")
    if not enclosure_url:
        raise RuntimeError("未找到音频下载地址 (enclosureUrl)")

    title = episode.get("title", "未知节目")
    podcast_name = (
        episode.get("podcast", {}).get("title")
        or props.get("podcast", {}).get("title")
        or "未知播客"
    )
    pub_date = episode.get("pubDate", "")
    description = episode.get("description", "")

    return {
        "title": title,
        "podcast_name": podcast_name,
        "enclosure_url": enclosure_url,
        "description": description[:500],  # 截断过长描述
        "pub_date": pub_date,
    }


# ──────────────────────────────────────────────
# 2. 下载音频
# ──────────────────────────────────────────────

def download_audio(audio_url: str, dest_path: str, chunk_size: int = 1024 * 1024) -> str:
    """
    将音频文件下载到 dest_path。
    支持带 Content-Disposition 的重定向。
    返回实际写入的文件路径。
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    print(f"  下载音频: {audio_url[:80]}...")
    req = urllib.request.Request(audio_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = resp.headers.get("Content-Length")
            total_mb = f"{int(total) / 1e6:.1f} MB" if total else "未知大小"
            print(f"  文件大小: {total_mb}")

            with open(dest_path, "wb") as f:
                downloaded = 0
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / int(total) * 100
                        print(f"\r  进度: {pct:.1f}%", end="", flush=True)
            print()  # 换行
    except Exception as e:
        raise RuntimeError(f"音频下载失败: {e}")

    return dest_path


# ──────────────────────────────────────────────
# 3. 用 ffmpeg 切分长音频
# ──────────────────────────────────────────────

def get_audio_duration_seconds(audio_path: str) -> float:
    """用 ffprobe 获取音频时长（秒）。"""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {result.stderr}")
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def split_audio_ffmpeg(
    audio_path: str,
    chunk_seconds: int = 1500,  # 25 分钟
    output_dir: str | None = None,
) -> list[str]:
    """
    将音频文件切分为 ≤chunk_seconds 的片段。
    返回片段文件路径列表（顺序）。
    如果音频短于 chunk_seconds，返回 [audio_path]（原文件，不复制）。
    """
    duration = get_audio_duration_seconds(audio_path)
    print(f"  音频时长: {duration / 60:.1f} 分钟")

    if duration <= chunk_seconds:
        return [audio_path]

    n_chunks = math.ceil(duration / chunk_seconds)
    print(f"  需要切分为 {n_chunks} 段（每段 ≤{chunk_seconds // 60} 分钟）")

    if output_dir is None:
        output_dir = os.path.dirname(audio_path)

    base = os.path.splitext(os.path.basename(audio_path))[0]
    chunk_paths = []

    for i in range(n_chunks):
        start = i * chunk_seconds
        out_path = os.path.join(output_dir, f"{base}_chunk{i+1:02d}.mp3")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", audio_path,
            "-t", str(chunk_seconds),
            "-c", "copy",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 切分失败 (片段 {i+1}): {result.stderr[-500:]}")
        chunk_paths.append(out_path)
        print(f"  生成片段: {os.path.basename(out_path)}")

    return chunk_paths


# ──────────────────────────────────────────────
# 4. 调用千问 API 转录音频
# ──────────────────────────────────────────────

def transcribe_chunk_qwen(
    audio_path: str,
    api_key: str,
    episode_title: str = "",
    chunk_index: int = 0,
    total_chunks: int = 1,
    retry: int = 3,
) -> str:
    """
    将单个音频片段发送给千问 qwen-audio-turbo 进行转录。
    使用标准 OpenAI-compatible REST API（raw http.client，不依赖 openai 包）。

    千问音频 API 要求：
    - 音频通过 Base64 编码内联传入，或提供可公开访问的 URL
    - 这里使用 Base64 内联方式（无需文件托管服务器）
    - 模型: qwen-audio-turbo
    - endpoint: dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
    """
    import base64

    suffix = f"（第 {chunk_index+1}/{total_chunks} 段）" if total_chunks > 1 else ""
    print(f"  转录音频{suffix}: {os.path.basename(audio_path)}")

    # 读取并 Base64 编码
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    # 判断 MIME 类型
    ext = os.path.splitext(audio_path)[1].lower()
    mime_map = {".mp3": "audio/mp3", ".m4a": "audio/mp4", ".wav": "audio/wav", ".ogg": "audio/ogg"}
    mime_type = mime_map.get(ext, "audio/mp3")

    system_prompt = (
        "你是一个专业的播客转录助手。请将提供的音频内容转录为完整的中文逐字稿。"
        "保持原始说话风格，包括口语化表达。用换行区分不同说话者（如有多人）。"
        "不要总结，不要改写，直接转录原文。"
    )

    user_text = "请将以下音频转录为完整逐字稿。"
    if episode_title:
        user_text += f"本节目标题：《{episode_title}》。"
    if total_chunks > 1:
        user_text += f"这是第 {chunk_index+1}/{total_chunks} 段音频。"

    payload = {
        "model": "qwen-audio-turbo",
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": f"data:{mime_type};base64,{audio_b64}",
                            "format": ext.lstrip("."),
                        },
                    },
                    {"type": "text", "text": user_text},
                ],
            },
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    }

    body = json.dumps(payload).encode("utf-8")

    for attempt in range(retry):
        try:
            conn = http.client.HTTPSConnection("dashscope.aliyuncs.com", timeout=300)
            conn.request(
                "POST",
                "/compatible-mode/v1/chat/completions",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            resp = conn.getresponse()
            resp_body = resp.read().decode("utf-8")
            conn.close()

            if resp.status != 200:
                raise RuntimeError(f"API 返回 {resp.status}: {resp_body[:500]}")

            result = json.loads(resp_body)
            text = result["choices"][0]["message"]["content"]
            return text

        except Exception as e:
            if attempt < retry - 1:
                wait = 2 ** attempt * 5
                print(f"  转录失败（第 {attempt+1} 次）: {e}，{wait}s 后重试...")
                time.sleep(wait)
            else:
                raise RuntimeError(f"转录失败（已重试 {retry} 次）: {e}")

    return ""  # unreachable


# ──────────────────────────────────────────────
# 5. 主流程
# ──────────────────────────────────────────────

def transcribe_episode(
    episode_url: str,
    api_key: str,
    output_dir: str,
    keep_audio: bool = False,
) -> str:
    """
    完整处理一个小宇宙节目链接：
      1. 获取节目元数据和音频 URL
      2. 下载音频
      3. 切分（如需）
      4. 逐段转录
      5. 合并转录文本并保存为 .txt
    返回保存的 .txt 文件路径。
    """
    print(f"\n{'='*60}")
    print(f"处理: {episode_url}")

    # Step 1: 获取元数据
    print("  获取节目信息...")
    info = get_xiaoyuzhou_info(episode_url)
    title = info["title"]
    podcast_name = info["podcast_name"]
    audio_url = info["enclosure_url"]
    pub_date = info["pub_date"]

    print(f"  播客: 《{podcast_name}》")
    print(f"  标题: {title}")
    print(f"  发布: {pub_date}")

    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 2: 下载音频
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)[:60]
        audio_ext = ".mp3"
        parsed = urllib.parse.urlparse(audio_url)
        url_path = parsed.path.lower()
        for ext in [".mp3", ".m4a", ".wav", ".ogg"]:
            if url_path.endswith(ext):
                audio_ext = ext
                break

        audio_path = os.path.join(tmpdir, f"{safe_title}{audio_ext}")
        download_audio(audio_url, audio_path)

        # Step 3: 切分音频
        chunk_paths = split_audio_ffmpeg(audio_path, chunk_seconds=1500, output_dir=tmpdir)

        # Step 4: 逐段转录
        total_chunks = len(chunk_paths)
        transcript_parts = []
        for i, chunk_path in enumerate(chunk_paths):
            text = transcribe_chunk_qwen(
                chunk_path,
                api_key,
                episode_title=title,
                chunk_index=i,
                total_chunks=total_chunks,
            )
            transcript_parts.append(text)

        # Step 5: 合并并保存
        full_transcript = "\n\n".join(transcript_parts)

        header = (
            f"# 逐字稿：{title}\n\n"
            f"**播客**：{podcast_name}\n"
            f"**发布日期**：{pub_date}\n"
            f"**来源**：{episode_url}\n"
            f"**转录模型**：qwen-audio-turbo\n"
            f"**转录片段数**：{total_chunks}\n\n"
            f"---\n\n"
        )

        out_filename = f"{safe_title}.txt"
        out_path = os.path.join(output_dir, out_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(header + full_transcript)

        print(f"\n  ✓ 逐字稿已保存: {out_path}")
        print(f"  字数: {len(full_transcript):,} 字")

    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="将小宇宙播客链接转录为逐字稿 .txt 文件"
    )
    parser.add_argument(
        "urls",
        nargs="+",
        help="一个或多个小宇宙节目链接",
    )
    parser.add_argument(
        "--api-key",
        required=True,
        help="千问 API Key（dashscope）",
    )
    parser.add_argument(
        "--output-dir",
        default="./transcripts",
        help="逐字稿输出目录（默认: ./transcripts）",
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="保留下载的音频文件（默认删除）",
    )

    args = parser.parse_args()

    saved_paths = []
    errors = []

    for url in args.urls:
        try:
            path = transcribe_episode(
                url,
                api_key=args.api_key,
                output_dir=args.output_dir,
                keep_audio=args.keep_audio,
            )
            saved_paths.append(path)
        except Exception as e:
            print(f"\n  ✗ 处理失败 {url}: {e}", file=sys.stderr)
            errors.append((url, str(e)))

    print(f"\n{'='*60}")
    print(f"完成: 成功 {len(saved_paths)} 个，失败 {len(errors)} 个")
    for path in saved_paths:
        print(f"  ✓ {path}")
    for url, err in errors:
        print(f"  ✗ {url[:60]}... → {err[:100]}", file=sys.stderr)

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
