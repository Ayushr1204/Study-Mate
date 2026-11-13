export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ')

export const inputClass =
  'w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-fg placeholder:text-faint focus:border-accent focus:outline-none'
