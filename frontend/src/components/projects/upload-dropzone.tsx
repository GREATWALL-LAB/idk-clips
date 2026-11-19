"use client";

import { useId, useRef, useState, type DragEvent } from "react";
import { FileVideo, UploadCloud, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";

export function validateVideoFile(file: File, allowed: string[], maxMb: number): string | null {
  const dot = file.name.lastIndexOf(".");
  const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!allowed.includes(extension)) return `Unsupported file type. Use ${allowed.join(", ")}.`;
  if (file.size === 0) return "The file is empty.";
  if (file.size > maxMb * 1024 * 1024) return `The file is larger than the ${maxMb} MB limit.`;
  return null;
}

/** Drag-and-drop file picker for videos (keyboard accessible through the hidden file input). */
export function UploadDropzone({
  file,
  onFile,
  allowed,
  maxMb,
  disabled = false,
}: {
  file: File | null;
  onFile: (file: File | null) => void;
  allowed: string[];
  maxMb: number;
  disabled?: boolean;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) onFile(dropped);
  };

  if (file) {
    return (
      <div className="flex items-center gap-4 rounded-2xl border border-line-strong bg-canvas p-4">
        <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand">
          <FileVideo className="size-6" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{file.name}</p>
          <p className="text-xs text-subtle">{formatBytes(file.size)} · {file.type || "video"}</p>
        </div>
        {!disabled ? (
          <button
            type="button"
            onClick={() => onFile(null)}
            className="grid size-9 place-items-center rounded-lg text-muted hover:bg-mist hover:text-ink"
            aria-label="Remove file"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-colors",
        dragging ? "border-brand bg-brand-50" : "border-line-strong bg-canvas hover:border-ink/25",
      )}
    >
      <span className={cn("grid size-14 place-items-center rounded-2xl border border-line bg-canvas text-brand transition-transform", dragging && "scale-110")}>
        <UploadCloud className="size-7" aria-hidden="true" />
      </span>
      <p className="mt-4 text-sm font-medium text-ink">Drag and drop a video here</p>
      <p className="mt-1 text-xs text-subtle">
        {allowed.join(", ")} · up to {maxMb >= 1024 ? `${(maxMb / 1024).toFixed(maxMb % 1024 ? 1 : 0)} GB` : `${maxMb} MB`}
      </p>
      <label
        htmlFor={inputId}
        className="mt-5 inline-flex h-9 cursor-pointer items-center rounded-xl border border-line-strong bg-canvas px-4 text-sm font-medium text-ink transition-colors hover:bg-mist focus-within:outline focus-within:outline-2 focus-within:outline-brand"
      >
        Browse files
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={[...allowed, "video/*"].join(",")}
          className="sr-only"
          disabled={disabled}
          onChange={(event) => {
            const picked = event.target.files?.[0] ?? null;
            onFile(picked);
            if (inputRef.current) inputRef.current.value = "";
          }}
        />
      </label>
    </div>
  );
}
