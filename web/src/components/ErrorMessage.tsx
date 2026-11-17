// A message about what went wrong, or nothing.
export function ErrorMessage({ text }: { text: string | null }) {
  return text ? <p className="error" role="alert">{text}</p> : null;
}
