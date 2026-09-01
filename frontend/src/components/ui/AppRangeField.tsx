type Props = {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  hint?: string;
  disabled?: boolean;
  onChange: (value: number) => void;
};

export function AppRangeField({
  id,
  label,
  value,
  min,
  max,
  step = 1,
  hint,
  disabled,
  onChange,
}: Props) {
  return (
    <div className="app-field app-range-field">
      <div className="range-label-row">
        <label className="field-label" htmlFor={id}>{label}</label>
        <output htmlFor={id}>{value}%</output>
      </div>
      <input
        id={id}
        className="app-range"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      {hint && <p className="field-hint">{hint}</p>}
    </div>
  );
}
