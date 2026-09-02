type Props = {
  id: string;
  label: string;
  checked: boolean;
  description?: string;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
};

export function AppToggle({ id, label, checked, description, disabled, onChange }: Props) {
  return (
    <label className="app-toggle" htmlFor={id}>
      <span><strong>{label}</strong>{description && <small>{description}</small>}</span>
      <input id={id} type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <span className="toggle-control" aria-hidden="true"><span /></span>
    </label>
  );
}
