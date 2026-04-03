import { useEffect, useRef, useState } from "react";
import type { AppConfig } from "../types";

interface Props {
  buttonId: number;
  config: AppConfig;
  updateConfig: (updater: (prev: AppConfig) => AppConfig) => void;
  onClose: () => void;
}

const KEY_MAP: Record<string, string> = {
  ArrowLeft: "left",
  ArrowRight: "right",
  ArrowUp: "up",
  ArrowDown: "down",
  " ": "space",
  Enter: "enter",
  Escape: "esc",
  Tab: "tab",
  Backspace: "backspace",
  Delete: "delete",
  Insert: "insert",
  Home: "home",
  End: "end",
  PageUp: "page up",
  PageDown: "page down",
  MediaPlayPause: "play/pause media",
  MediaTrackNext: "next track",
  MediaTrackPrevious: "previous track",
  AudioVolumeUp: "volume up",
  AudioVolumeDown: "volume down",
  AudioVolumeMute: "volume mute",
};

// Generate F1–F24 entries
for (let i = 1; i <= 24; i++) {
  KEY_MAP[`F${i}`] = `f${i}`;
}

const MODIFIER_KEYS = new Set(["Control", "Alt", "Shift", "Meta"]);

function normalizeKey(key: string): string {
  if (KEY_MAP[key]) return KEY_MAP[key];
  return key.toLowerCase();
}

export default function KeybindModal({ buttonId, config, updateConfig, onClose }: Props) {
  const profile = config.profiles[config.active_profile];
  const existing = profile?.buttons[String(buttonId)];

  const [labelText, setLabelText] = useState(existing?.label ?? "");
  const [capturedAction, setCapturedAction] = useState(existing?.action ?? "");
  const [isCapturing, setIsCapturing] = useState(false);

  const overlayRef = useRef<HTMLDivElement>(null);

  // Key capture listener
  useEffect(() => {
    if (!isCapturing) return;

    const handler = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();

      const key = e.key;

      // Pressing Escape cancels capture without updating
      if (key === "Escape") {
        setIsCapturing(false);
        return;
      }

      // Ignore lone modifiers
      if (MODIFIER_KEYS.has(key)) return;

      const parts: string[] = [];
      if (e.ctrlKey) parts.push("ctrl");
      if (e.altKey) parts.push("alt");
      if (e.shiftKey) parts.push("shift");
      if (e.metaKey) parts.push("win");

      parts.push(normalizeKey(key));

      const combo = parts.join("+");
      setCapturedAction(combo);
      setIsCapturing(false);
    };

    window.addEventListener("keydown", handler, true);
    return () => window.removeEventListener("keydown", handler, true);
  }, [isCapturing]);

  // Close on overlay click
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose();
  };

  const handleSave = () => {
    const finalLabel = labelText.trim() || capturedAction;
    const finalAction = capturedAction.trim();

    updateConfig((prev) => {
      const p = prev.profiles[prev.active_profile];
      return {
        ...prev,
        profiles: {
          ...prev.profiles,
          [prev.active_profile]: {
            ...p,
            buttons: {
              ...p?.buttons,
              [String(buttonId)]: {
                label: finalLabel,
                action: finalAction,
              },
            },
          },
        },
      };
    });
    onClose();
  };

  const handleClear = () => {
    setLabelText("");
    setCapturedAction("");

    updateConfig((prev) => {
      const p = prev.profiles[prev.active_profile];
      if (!p) return prev;
      const nextButtons = { ...p.buttons };
      delete nextButtons[String(buttonId)];
      return {
        ...prev,
        profiles: {
          ...prev.profiles,
          [prev.active_profile]: {
            ...p,
            buttons: nextButtons,
          },
        },
      };
    });
    onClose();
  };

  const captureAreaClass =
    "modal-capture-area" +
    (isCapturing ? " active" : capturedAction ? " has-binding" : "");

  return (
    <div className="modal-overlay" ref={overlayRef} onClick={handleOverlayClick}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">Button {buttonId}</div>

        {/* Label section */}
        <div>
          <div className="modal-section-label">Label</div>
          <input
            className="modal-label-input"
            type="text"
            value={labelText}
            placeholder="Button label (optional)"
            onChange={(e) => setLabelText(e.target.value)}
            autoFocus
          />
        </div>

        {/* Action section */}
        <div>
          <div className="modal-section-label">Action</div>

          {/* Capture area */}
          <div
            className={captureAreaClass}
            onClick={() => setIsCapturing(true)}
          >
            {isCapturing ? (
              <span style={{ color: "var(--accent)", fontSize: 13 }}>
                Press keys now…
              </span>
            ) : capturedAction ? (
              capturedAction
            ) : (
              <span className="capture-placeholder">
                Click here, then press keys…
              </span>
            )}
          </div>

          {/* OR divider */}
          <div className="modal-or-divider" style={{ margin: "10px 0" }}>
            or type manually
          </div>

          {/* Manual text input */}
          <input
            className="modal-input"
            type="text"
            value={capturedAction}
            placeholder="e.g. ctrl+shift+s"
            onChange={(e) => {
              setCapturedAction(e.target.value);
              setIsCapturing(false);
            }}
          />
        </div>

        {/* Actions */}
        <div className="modal-actions">
          <button className="btn-danger" onClick={handleClear}>
            Clear
          </button>
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" onClick={handleSave}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
