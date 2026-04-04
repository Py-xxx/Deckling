import { useRef } from "react";
import type { AppConfig } from "../types";

interface Props {
  config: AppConfig;
  updateConfig: (updater: (prev: AppConfig) => AppConfig) => void;
  onCalibrateClick?: (potId: number) => void;
}

const VM_STRIPS = [
  { value: -1, label: "None" },
  { value: 0, label: "HW Input 1" },
  { value: 1, label: "HW Input 2" },
  { value: 2, label: "HW Input 3" },
  { value: 3, label: "Virtual 1 (VAIO)" },
  { value: 4, label: "Virtual 2 (AUX)" },
];

function KnobSvg() {
  return (
    <svg width="60" height="60" viewBox="0 0 60 60" fill="none">
      {/* Outer ring */}
      <circle cx="30" cy="30" r="28" stroke="#3a3a3a" strokeWidth="2" fill="#111" />
      {/* Inner circle */}
      <circle cx="30" cy="30" r="20" stroke="#2a2a2a" strokeWidth="1.5" fill="#0d0d0d" />
      {/* Indicator line from center to 12 o'clock */}
      <line x1="30" y1="30" x2="30" y2="6" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
      {/* Center dot */}
      <circle cx="30" cy="30" r="3" fill="#444" />
    </svg>
  );
}

export default function PotRow({ config, updateConfig, onCalibrateClick }: Props) {
  const { num_pots } = config.display;
  const profile = config.profiles[config.active_profile];
  const labelTimers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

  const handleLabelChange = (potId: number, value: string) => {
    if (labelTimers.current[potId]) clearTimeout(labelTimers.current[potId]);
    labelTimers.current[potId] = setTimeout(() => {
      updateConfig((prev) => {
        const p = prev.profiles[prev.active_profile];
        const existing = p?.pots[String(potId)] ?? { label: "", strip: -1 };
        return {
          ...prev,
          profiles: {
            ...prev.profiles,
            [prev.active_profile]: {
              ...p,
              pots: {
                ...p?.pots,
                [String(potId)]: { ...existing, label: value },
              },
            },
          },
        };
      });
    }, 300);
  };

  const handleStripChange = (potId: number, strip: number) => {
    updateConfig((prev) => {
      const p = prev.profiles[prev.active_profile];
      const existing = p?.pots[String(potId)] ?? { label: "", strip: -1 };
      return {
        ...prev,
        profiles: {
          ...prev.profiles,
          [prev.active_profile]: {
            ...p,
            pots: {
              ...p?.pots,
              [String(potId)]: { ...existing, strip },
            },
          },
        },
      };
    });
  };

  const handleInvertToggle = (potId: number, inverted: boolean) => {
    updateConfig((prev) => {
      const p = prev.profiles[prev.active_profile];
      const existing = p?.pots[String(potId)] ?? { label: "", strip: -1 };
      return {
        ...prev,
        profiles: {
          ...prev.profiles,
          [prev.active_profile]: {
            ...p,
            pots: {
              ...p?.pots,
              [String(potId)]: { ...existing, inverted },
            },
          },
        },
      };
    });
  };

  const pots = Array.from({ length: num_pots }, (_, i) => i);

  return (
    <div className="pots-row">
      {pots.map((id) => {
        const pot = profile?.pots[String(id)];
        const currentLabel = pot?.label ?? "";
        const currentStrip = pot?.strip ?? -1;
        const isCalibrated = pot?.calibration?.enabled ?? false;
        const isInverted = pot?.inverted ?? false;

        return (
          <div key={id} className="pot-item">
            <span className="pot-pin-label">A{id}</span>
            <div className="pot-knob">
              <KnobSvg />
            </div>
            <input
              className="pot-label-input"
              type="text"
              defaultValue={currentLabel}
              placeholder="Label"
              onChange={(e) => handleLabelChange(id, e.target.value)}
            />
            <select
              className="pot-select"
              value={currentStrip}
              onChange={(e) => handleStripChange(id, parseInt(e.target.value, 10))}
            >
              {VM_STRIPS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
            <label className="pot-invert-toggle">
              <input
                type="checkbox"
                checked={isInverted}
                onChange={(e) => handleInvertToggle(id, e.target.checked)}
              />
              <span>Invert</span>
            </label>
            <button
              className={`pot-calibrate-btn ${isCalibrated ? "calibrated" : ""}`}
              onClick={() => onCalibrateClick?.(id)}
              title={isCalibrated ? "Calibration enabled — Click to edit" : "Calibrate this potentiometer"}
            >
              {isCalibrated ? "✓ Calibrated" : "Calibrate"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
