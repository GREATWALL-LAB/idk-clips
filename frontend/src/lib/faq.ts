/**
 * Frequently asked questions, shown on the homepage and published as FAQPage structured
 * data. Every answer must stay true for the current release; update both together.
 */
export const FAQ = [
  {
    question: "What is IDK Clips?",
    answer:
      "IDK Clips is a free, open-source AI video clipping tool. It turns long videos such as podcasts, talks, lectures, interviews and streams into short clips: it transcribes the speech, lets an AI model pick the moments that stand on their own, adds captions and exports MP4 files for Shorts, Reels, TikTok and other platforms.",
  },
  {
    question: "Is IDK Clips really free?",
    answer:
      "Yes. IDK Clips is released under the MIT License. There are no subscriptions, credits, paid tiers or watermarks, and every feature is available to everyone. The only costs are your own computer's electricity or, if you host it yourself, your server.",
  },
  {
    question: "Do my videos get uploaded to a server?",
    answer:
      "When you run IDK Clips locally, your videos never leave your computer. When you use it online in hybrid mode, the video goes from your browser to your own computer (your paired worker), which does the processing; the website only stores text such as titles, transcripts and clip timings.",
  },
  {
    question: "What do I need to run it?",
    answer:
      "A Windows 11 or Linux computer (macOS scripts are provided but not yet verified), Python 3.11 or newer, Node.js to build the web interface, and FFmpeg. Ollama runs the AI model that finds clips. An NVIDIA GPU makes transcription faster but is optional; the CPU works too.",
  },
  {
    question: "Which AI models does IDK Clips use?",
    answer:
      "Speech is transcribed with faster-whisper (Whisper models). Moments are found by a language model you choose: by default a local model in Ollama, or an OpenAI-compatible service configured on a self-hosted server.",
  },
  {
    question: "Which formats and aspect ratios can I export?",
    answer:
      "MP4 files with H.264 video and AAC audio in four shapes: 9:16 (1080×1920), 4:5 (1080×1350), 1:1 (1080×1080) and 16:9 (1920×1080). Captions are burned in, and the picture is cropped around the speaker or fitted over a blurred background, never stretched.",
  },
  {
    question: "Can I make clips from YouTube videos?",
    answer:
      "Only from videos you have the rights to use. IDK Clips does not download from YouTube. If you are the creator, download your own upload from YouTube Studio and import the file; a YouTube link can be attached to the project for reference.",
  },
  {
    question: "Can I host IDK Clips for my team or community?",
    answer:
      "Yes. You can self-host it in server mode (the server processes videos) or hybrid mode (each user's own computer processes their videos, so the server needs very little). The documentation covers Docker, Linux services and low-cost hosting.",
  },
  {
    question: "Is there an admin account or admin panel?",
    answer:
      "No. IDK Clips has no administrator system. Every account is an ordinary user who can see and manage only their own projects, clips, workers and data. Server-wide settings come from the server's own configuration.",
  },
] as const;
