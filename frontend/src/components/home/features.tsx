import { AudioLines, BrainCircuit, Captions, Clock, Download, LockKeyhole, Proportions, Scissors } from "lucide-react";
import { Marker, Reveal } from "@/components/home/motion";

const FEATURES = [
  { icon: AudioLines, title: "Local transcription", text: "faster-whisper with word timestamps, on your CPU or NVIDIA GPU. Download TXT, SRT or VTT." },
  { icon: BrainCircuit, title: "AI moment detection", text: "Local models through Ollama suggest 5–10 complete moments with a title and a reason. External providers are optional." },
  { icon: Clock, title: "Honest timestamps", text: "The AI picks transcript lines. Start and end times come from the speech itself, never from a guess." },
  { icon: Proportions, title: "Four real export shapes", text: "9:16, 4:5, 1:1 and 16:9, per clip, with subject-aware cropping or a whole-picture fit. Nothing is stretched." },
  { icon: Captions, title: "Captions that match", text: "Burned in from the transcript with the spoken word highlighted. Three fonts, colours, size, position and editable text." },
  { icon: Scissors, title: "A real editor", text: "Timeline with word snapping, precise start and end fields, titles, live preview, and clips you add by hand." },
  { icon: Download, title: "Clean MP4 files", text: "H.264 and AAC, ready for every platform. No watermark, no export limits beyond your own hardware." },
  { icon: LockKeyhole, title: "Private by design", text: "Locally, nothing leaves your computer. Online, your video goes to your own machine, not to our servers." },
];

export function Features() {
  return (
    <section id="features" className="scroll-mt-20 py-24 sm:py-32" aria-labelledby="features-title">
      <div className="mx-auto grid max-w-7xl gap-12 px-4 sm:px-6 lg:grid-cols-[0.9fr_1.1fr] lg:gap-20">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <Reveal>
            <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand">Features</p>
            <h2 id="features-title" className="mt-3 font-display text-4xl font-bold leading-[1.02] tracking-[-0.035em] text-ink sm:text-6xl">
              Everything a clip needs. <Marker>Nothing</Marker> you pay for.
            </h2>
            <p className="mt-6 max-w-md text-lg leading-relaxed text-ink-soft">
              IDK Clips is a complete workflow from long video to finished clip, and every feature is available to everyone.
            </p>
          </Reveal>
        </div>
        <dl className="grid gap-x-10 sm:grid-cols-2">
          {FEATURES.map(({ icon: Icon, title, text }, index) => (
            <Reveal key={title} delay={(index % 2) * 0.08} className="border-t border-line py-7">
              <dt className="flex items-center gap-3 text-base font-semibold text-ink">
                <span className="grid size-9 place-items-center rounded-xl bg-ink text-lime">
                  <Icon className="size-[18px]" aria-hidden="true" />
                </span>
                {title}
              </dt>
              <dd className="mt-3 text-[15px] leading-relaxed text-muted">{text}</dd>
            </Reveal>
          ))}
        </dl>
      </div>
    </section>
  );
}
