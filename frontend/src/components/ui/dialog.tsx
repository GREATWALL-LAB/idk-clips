"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Accessible modal built on the native <dialog> element (focus trap and Escape handled by the browser). */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal?.();
    if (!open && dialog.open) dialog.close?.();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === ref.current) onClose(); // click on the backdrop
      }}
      aria-label={title}
      className={`m-auto w-[calc(100%-2rem)] ${wide ? "max-w-3xl" : "max-w-md"} rounded-3xl border border-line bg-surface p-0 text-ink shadow-lift backdrop:bg-ink/40 backdrop:backdrop-blur-[2px]`}
    >
      {open ? (
        <div className="p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-ink">{title}</h2>
              {description ? <div className="mt-1 text-sm text-muted">{description}</div> : null}
            </div>
            <button type="button" onClick={onClose} className="grid size-8 place-items-center rounded-lg text-subtle hover:bg-mist hover:text-ink" aria-label="Close">
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
          {children ? <div className="mt-5">{children}</div> : null}
          {footer ? <div className="mt-6 flex flex-wrap justify-end gap-2">{footer}</div> : null}
        </div>
      ) : null}
    </dialog>
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Delete",
  busy = false,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  busy?: boolean;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} loading={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}
