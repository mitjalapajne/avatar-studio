import { ButtonHTMLAttributes, forwardRef, InputHTMLAttributes, TextareaHTMLAttributes } from "react";

const cx = (...parts: (string | false | undefined | null)[]) => parts.filter(Boolean).join(" ");

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }
>(function Button({ variant = "primary", className, ...props }, ref) {
  const base =
    "inline-flex h-9 items-center justify-center gap-2 rounded-lg px-4 text-[13px] font-medium " +
    "transition-colors duration-150 select-none disabled:cursor-not-allowed disabled:opacity-40 " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-900/20";
  const variants = {
    primary: "bg-neutral-900 text-white hover:bg-neutral-800",
    secondary: "border border-neutral-200 bg-white text-neutral-900 hover:bg-neutral-50",
    ghost: "text-neutral-500 hover:bg-neutral-100 hover:text-neutral-900",
  };
  return <button ref={ref} className={cx(base, variants[variant], className)} {...props} />;
});

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cx(
        "h-10 w-full rounded-lg border border-neutral-200 bg-white px-3 text-[14px] text-neutral-900",
        "placeholder:text-neutral-400 transition-colors focus:border-neutral-400 focus:outline-none",
        "focus:ring-4 focus:ring-neutral-100",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cx(
        "w-full resize-none rounded-lg border border-neutral-200 bg-white px-3 py-2.5 text-[14px] leading-relaxed text-neutral-900",
        "placeholder:text-neutral-400 transition-colors focus:border-neutral-400 focus:outline-none",
        "focus:ring-4 focus:ring-neutral-100",
        className,
      )}
      {...props}
    />
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  disabled,
}: {
  value: T;
  options: { value: T; label: string; disabled?: boolean }[];
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex rounded-lg bg-neutral-100 p-0.5">
      {options.map((o) => {
        const active = o.value === value;
        const off = disabled || o.disabled;
        return (
          <button
            key={o.value}
            type="button"
            disabled={off}
            onClick={() => onChange(o.value)}
            className={cx(
              "h-8 rounded-[7px] px-3 text-[13px] transition-all duration-150 disabled:opacity-40",
              active ? "bg-white font-medium text-neutral-900 shadow-[0_0_0_1px_rgba(0,0,0,0.04)]" : "text-neutral-500 hover:text-neutral-900",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function Label({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="mb-2 flex items-baseline justify-between">
      <span className="text-[13px] font-medium text-neutral-900">{children}</span>
      {hint && <span className="text-[12px] text-neutral-400">{hint}</span>}
    </div>
  );
}
