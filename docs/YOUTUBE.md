# YouTube videos

You can start a project from a **YouTube link**. IDK Clips uses only methods YouTube
permits, so it works like this:

1. Paste the link (watch, Shorts, live or `youtu.be` links).
2. IDK Clips asks YouTube's public **oEmbed** service for the title, channel and
   thumbnail. This is an official, documented endpoint that needs no sign-in. Only the
   video ID from your link is sent, and only to `www.youtube.com`.
3. You add **your own copy of the video**: for your own uploads, download the original
   from **YouTube Studio → Content → ⋮ → Download**, or export it with **Google Takeout**.
4. The project keeps the YouTube link and its public details for reference, and is
   processed like any other upload.

Private and unlisted videos have no public details; you can still reference them and
add the file.

## Why IDK Clips does not download from YouTube

YouTube's Terms of Service only allow downloading through features YouTube provides
(such as the YouTube Studio download for your own videos) or with permission. Tools that
pull video streams directly work by getting around YouTube's technical protections.
IDK Clips will not do that, and does not include or depend on such tools. The same
applies to TikTok, Instagram, Facebook, X, Twitch, Vimeo and streaming services: links to
those platforms are refused by the "direct link" import.

If you have the rights to a video from another source, download it there and upload the
file, or use a **direct link** to a video file you are allowed to use (for example from
your own server or a public-domain archive).

## Settings

`OPENCLIP_YOUTUBE_LOOKUP_ENABLED=false` turns the oEmbed lookup off. Links are then
still accepted as references, without title and thumbnail.

## For contributors

Please do not add code that downloads YouTube streams, uses YouTube cookies or accounts,
or bypasses age, region or membership restrictions. If YouTube offers an official API for
creators to fetch their own uploads, a source adapter for it is welcome.
