import asyncio
import os
import re
from typing import Union

import aiohttp
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch

import config
from SANYAMUSIC import LOGGER
from SANYAMUSIC.utils.formatters import time_to_seconds

API_URL = "https://shrutibots.site"


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    async def _saavn_download(self, title: str) -> str | None:
        """JioSaavn se audio file download karo — no watermark."""
        try:
            import re as _re
            import hashlib
            import urllib.request

            # Title clean karo
            clean = _re.sub(r'\([^)]*\)|\[[^\]]*\]', '', title)
            clean = _re.sub(r'\|.*', '', clean).strip()
            if not clean:
                return None

            # Search on JioSaavn
            params = {
                "__call": "search.getResults",
                "q": clean,
                "_format": "json",
                "_marker": "0",
                "api_version": "4",
                "cc": "in",
                "ctx": "web6dot0",
            }
            import aiohttp as _aiohttp
            async with _aiohttp.ClientSession() as session:
                async with session.get(
                    "https://www.jiosaavn.com/api.php",
                    params=params,
                    timeout=_aiohttp.ClientTimeout(total=8),
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json(content_type=None)
                    results = data.get("results", [])
                    if not results:
                        return None

                encrypted_url = results[0].get("more_info", {}).get("encrypted_media_url", "")
                if not encrypted_url:
                    return None

                # Get stream URL
                auth_params = {
                    "__call": "song.generateAuthToken",
                    "url": encrypted_url,
                    "bitrate": "320",
                    "api_version": "4",
                    "_format": "json",
                    "ctx": "web6dot0",
                    "_marker": "0",
                }
                async with session.get(
                    "https://www.jiosaavn.com/api.php",
                    params=auth_params,
                    timeout=_aiohttp.ClientTimeout(total=8),
                ) as r2:
                    if r2.status != 200:
                        return None
                    auth_data = await r2.json(content_type=None)
                    stream_url = auth_data.get("auth_url", "").replace("http://", "https://")
                    if not stream_url:
                        return None

            # Download file
            os.makedirs("downloads", exist_ok=True)
            fname = hashlib.md5(clean.encode()).hexdigest()
            fpath = f"downloads/{fname}.mp3"

            if os.path.exists(fpath) and os.path.getsize(fpath) > 10000:
                LOGGER(__name__).info(f"JioSaavn: Cache hit '{clean}'")
                return fpath

            def _dl():
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "*/*",
                    "Referer": "https://www.jiosaavn.com/",
                }
                req = urllib.request.Request(stream_url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as r, open(fpath, "wb") as f:
                    f.write(r.read())

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _dl)

            if os.path.exists(fpath) and os.path.getsize(fpath) > 10000:
                LOGGER(__name__).info(f"JioSaavn: Downloaded '{clean}' 320kbps")
                return fpath

            if os.path.exists(fpath):
                os.remove(fpath)
            return None

        except Exception as e:
            LOGGER(__name__).warning(f"JioSaavn download error: {e}")
            return None

    async def _api_download(self, video_id: str, video: bool = False) -> str | None:
        """ShrutiBots API se stream URL lo."""
        stream_type = "video" if video else "audio"
        try:
            async with aiohttp.ClientSession() as session:
                params = {"url": video_id, "type": stream_type}
                async with session.get(
                    f"{API_URL}/download", params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    token = data.get("download_token")
                    if not token:
                        return None
                    return f"{API_URL}/stream/{video_id}?type={stream_type}&token={token}"
        except Exception as e:
            LOGGER(__name__).warning(f"ShrutiBots API failed: {e}")
            return None

    def _ytdlp_stream(self, link: str, video: bool = False) -> str | None:
        """yt-dlp fallback."""
        fmt = (
            "(bestvideo[height<=?720]+bestaudio)/best"
            if video else "bestaudio/best"
        )
        cookie_path = "SANYAMUSIC/assets/cookies.txt"
        opts = {
            "format": fmt,
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "skip_download": True,
        }
        if os.path.exists(cookie_path):
            opts["cookiefile"] = cookie_path
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=False)
                if info and "entries" in info:
                    info = info["entries"][0]
                return info.get("url") if info else None
        except Exception as e:
            LOGGER(__name__).error(f"yt-dlp failed: {e}")
            return None

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset: entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            vidid = result["id"]
            duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        title, *_ = await self.details(link, videoid)
        return title

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        _, duration, *_ = await self.details(link, videoid)
        return duration

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        _, _, _, thumbnail, _ = await self.details(link, videoid)
        return thumbnail

    async def video(self, link: str, videoid: Union[bool, str] = None, stream: bool = True):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        video_id = link.split("v=")[-1].split("&")[0]

        # Primary: ShrutiBots API
        url = await self._api_download(video_id, video=stream)
        if url:
            return 1, url

        # Fallback: yt-dlp
        loop = asyncio.get_running_loop()
        url = await loop.run_in_executor(None, lambda: self._ytdlp_stream(link, video=stream))
        if url:
            return 1, url

        return 0, "All methods failed"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        proc = await asyncio.create_subprocess_shell(
            f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        output = out.decode("utf-8") if not err else (
            out.decode("utf-8") if "unavailable videos are hidden" in err.decode("utf-8").lower()
            else err.decode("utf-8")
        )
        return [x for x in output.split("\n") if x]

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            vidid = result["id"]
            yturl = result["link"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        return {
            "title": title, "link": yturl, "vidid": vidid,
            "duration_min": duration_min, "thumb": thumbnail,
        }, vidid

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        def get_fmt():
            opts = {"quiet": True, "no_warnings": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=False)
            return [
                {
                    "format": f.get("format"), "filesize": f.get("filesize"),
                    "format_id": f.get("format_id"), "ext": f.get("ext"),
                    "format_note": f.get("format_note"), "yturl": link,
                }
                for f in info.get("formats", [])
                if "dash" not in str(f.get("format", "")).lower()
            ]
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, get_fmt), link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = (await (VideosSearch(link, limit=10)).next()).get("result")
        r = results[query_type]
        return r["title"], r["duration"], r["thumbnails"][0]["url"].split("?")[0], r["id"]

    async def suggestions(self, keyword: str, limit: int = 2):
        try:
            results = VideosSearch(keyword, limit=limit + 5)
            data = (await results.next())["result"]
            return [
                {
                    "title": item["title"], "id": item["id"],
                    "duration": item["duration"],
                    "thumb": item["thumbnails"][0]["url"].split("?")[0],
                }
                for item in data
            ][1: limit + 1]
        except Exception:
            return []

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid:
            link = self.base + link
        loop = asyncio.get_running_loop()

        def song_video_dl():
            opts = {
                "format": f"{format_id}+140", "outtmpl": f"downloads/{title}",
                "geo_bypass": True, "nocheckcertificate": True,
                "quiet": True, "no_warnings": True,
                "prefer_ffmpeg": True, "merge_output_format": "mp4",
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([link])

        def song_audio_dl():
            opts = {
                "format": format_id, "outtmpl": f"downloads/{title}.%(ext)s",
                "geo_bypass": True, "nocheckcertificate": True,
                "quiet": True, "no_warnings": True, "prefer_ffmpeg": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3", "preferredquality": "192",
                }],
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([link])

        if songvideo:
            await loop.run_in_executor(None, song_video_dl)
            return f"downloads/{title}.mp4"

        if songaudio:
            await loop.run_in_executor(None, song_audio_dl)
            return f"downloads/{title}.mp3"

        # /play (audio) → JioSaavn primary (no watermark)
        # /vplay (video) → ShrutiBots API
        video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link.split("/")[-1]

        if not video:
            # Audio — JioSaavn se try karo
            try:
                saavn_path = await self._saavn_download(title or video_id)
                if saavn_path:
                    return saavn_path, True
            except Exception as e:
                LOGGER(__name__).warning(f"JioSaavn failed: {e}")

        # Video ya JioSaavn fail — ShrutiBots API
        api_url = await self._api_download(video_id, video=bool(video))
        if api_url:
            return api_url, None

        # Last resort — yt-dlp
        stream_url = await loop.run_in_executor(
            None, lambda: self._ytdlp_stream(link, video=bool(video))
        )
        if stream_url:
            return stream_url, None

        return None, None
