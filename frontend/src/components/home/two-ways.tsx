import { ArrowRight, Check, Globe, Laptop } from "lucide-react";
import { Reveal } from "@/components/home/motion";
import { ButtonLink } from "@/components/ui/button";
import { routes } from "@/lib/routes";

function Steps({ items, dark = false }: { items: string[]; dark?: boolean }) {
  return (
    <ol className="space-y-3">
      {items.map((item, index) => (
        <li key={item} className="flex gap-3 text-[15px] leading-relaxed">
          <span className={`grid size-6 shrink-0 place-items-center rounded-full font-mono text-xs font-bold ${dark ? "bg-lime text-ink" : "bg-brand text-white"}`}>
            {index + 1}
          </span>
          <span className={dark ? "text-white/85" : "text-ink-soft"}>{item}</span>
        </li>
      ))}
    </ol>
  );
}

function Command({ children }: { children: string }) {
  return <code className="block overflow-x-auto whitespace-nowrap rounded-xl bg-white/10 px-3 py-2 font-mono text-[12.5px] text-lime">{children}</code>;
}

export function TwoWays() {
  return (
    <section className="py-24 sm:py-32" aria-labelledby="two-ways-title">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <Reveal className="max-w-3xl">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-brand">Two ways to use it</p>
          <h2 id="two-ways-title" className="mt-3 font-display text-4xl font-bold leading-[1.02] tracking-[-0.035em] text-ink sm:text-6xl">
            Your computer does the work, either way.
          </h2>
          <p className="mt-6 text-lg leading-relaxed text-ink-soft">
            Video AI is heavy. Instead of renting GPU servers and charging for them, IDK Clips runs the processing on hardware you already own.
          </p>
        </Reveal>

        <div className="mt-14 grid gap-5 lg:grid-cols-2">
          <Reveal>
            <article id="run-locally" className="flex h-full scroll-mt-24 flex-col rounded-[32px] bg-ink p-7 text-white sm:p-10">
              <span className="grid size-12 place-items-center rounded-2xl bg-lime text-ink">
                <Laptop className="size-6" aria-hidden="true" />
              </span>
              <h3 className="mt-6 font-display text-3xl font-bold tracking-tight">Run locally</h3>
              <p className="mt-3 text-white/75">No account and no website. Download IDK Clips, start it, and open it in your browser. Videos, transcripts and clips stay on your computer.</p>
              <div className="mt-7">
                <Steps
                  dark
                  items={[
                    "Install Python 3.11+, Node.js 20+ and FFmpeg. Add Ollama for AI clip suggestions.",
                    "Run the setup script once. It creates a private environment; nothing is installed system-wide.",
                    "Start IDK Clips and open http://localhost:8000.",
                  ]}
                />
              </div>
              <div className="mt-7 space-y-2">
                <Command>scripts\windows\setup.cmd</Command>
                <Command>scripts\windows\start.cmd</Command>
              </div>
              <ul className="mt-7 space-y-1.5 text-sm text-white/70">
                {["Tested on Windows 11 with an NVIDIA GPU", "Linux and macOS scripts included (community testing welcome)", "Docker files for self-hosting"].map((item) => (
                  <li key={item} className="flex gap-2">
                    <Check className="mt-0.5 size-4 shrink-0 text-lime" aria-hidden="true" /> {item}
                  </li>
                ))}
              </ul>
              <div className="mt-auto pt-8">
                <ButtonLink href={routes.doc("installation")} variant="lime" icon={<ArrowRight className="size-4" aria-hidden="true" />}>
                  Installation guide
                </ButtonLink>
              </div>
            </article>
          </Reveal>

          <Reveal delay={0.1}>
            <article id="use-online" className="flex h-full scroll-mt-24 flex-col rounded-[32px] border border-line bg-surface p-7 shadow-card sm:p-10">
              <span className="grid size-12 place-items-center rounded-2xl bg-brand text-white">
                <Globe className="size-6" aria-hidden="true" />
              </span>
              <h3 className="mt-6 font-display text-3xl font-bold tracking-tight text-ink">Use online</h3>
              <p className="mt-3 text-ink-soft">
                Log in on the website to manage projects from anywhere. Connect your own computer once, and it processes your videos. The website only keeps
                text: titles, transcripts and clip timings.
              </p>
              <div className="mt-7">
                <Steps
                  items={[
                    "Create a free account. There are no plans to choose from.",
                    "Connect your computer as a worker with a one-time code. It only connects outwards; no ports to open.",
                    "Add a video. It goes from your browser straight to your worker, which transcribes, finds clips and exports them.",
                  ]}
                />
              </div>
              <ul className="mt-7 space-y-1.5 text-sm text-muted">
                {["Pairing codes expire in minutes and work once", "Disconnect a worker at any time", "Delete projects and set automatic deletion"].map((item) => (
                  <li key={item} className="flex gap-2">
                    <Check className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" /> {item}
                  </li>
                ))}
              </ul>
              <div className="mt-auto flex flex-wrap gap-2 pt-8">
                <ButtonLink href={routes.register} variant="primary" icon={<ArrowRight className="size-4" aria-hidden="true" />}>
                  Start creating
                </ButtonLink>
                <ButtonLink href={routes.doc("workers")}>How workers work</ButtonLink>
              </div>
            </article>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
