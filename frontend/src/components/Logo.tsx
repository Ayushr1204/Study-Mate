export function Logo({ className = 'size-8' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} role="img" aria-label="StudyMate logo">
      <rect width="32" height="32" rx="8" fill="#3b4bc8" />
      <path d="M6.5 11.8c3.2-1.1 6.4-.8 9.5 1v10.2c-3.1-1.7-6.3-2-9.5-.9z" fill="#fff" />
      <path d="M25.5 11.8c-3.2-1.1-6.4-.8-9.5 1v10.2c3.1-1.7 6.3-2 9.5-.9z" fill="#dfe4ff" />
      <path d="M23 3.5l1 2.6 2.6 1-2.6 1-1 2.6-1-2.6-2.6-1 2.6-1z" fill="#f5b942" />
    </svg>
  )
}
