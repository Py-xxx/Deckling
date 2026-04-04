import { useState, useEffect, useRef } from "react";
import type { AppConfig } from "../types";
import { getRawPotValue } from "../configStore";

interface Props {
  potId: number;
  config: AppConfig;
  updateConfig: (updater: (prev: AppConfig) => AppConfig) => void;
  onClose: () => void;
}

type CalibrationStep = "intro" | "min" | "max" | "done";

export default function PotCalibrationModal({ potId, config, updateConfig, onClose }: Props) {
  const [step, setStep] = useState<CalibrationStep>("intro");
  const [currentValue, setCurrentValue] = useState<number | null>(null);
  const [minValue, setMinValue] = useState<number | null>(null);
  const [maxValue, setMaxValue] = useState<number | null>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

  const profile = config.profiles[config.active_profile];
  const potConfig = profile?.pots[String(potId)];
  const existingCal = potConfig?.calibration;

  // Poll for current pot value
  useEffect(() => {
    if (step === "min" || step === "max") {
      const interval = setInterval(async () => {
        const value = await getRawPotValue(potId);
        if (value !== null) {
          setCurrentValue(value);
        }
      }, 100);
      return () => clearInterval(interval);
    }
  }, [step, potId]);

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose();
  };

  const handleCaptureMin = () => {
    if (currentValue !== null) {
      setMinValue(currentValue);
      setStep("max");
    }
  };

  const handleCaptureMax = () => {
    if (currentValue !== null) {
      setMaxValue(currentValue);
      setStep("done");
    }
  };

  const handleSave = () => {
    if (minValue === null || maxValue === null) return;

    updateConfig((prev) => {
      const newProfiles = { ...prev.profiles };
      const profileName = prev.active_profile;
      const profile = newProfiles[profileName];
      
      if (!profile) return prev;

      const newPots = { ...profile.pots };
      const pot = newPots[String(potId)];
      
      if (!pot) return prev;

      newPots[String(potId)] = {
        ...pot,
        calibration: {
          enabled: true,
          raw_min: minValue,
          raw_max: maxValue,
        },
      };

      newProfiles[profileName] = {
        ...profile,
        pots: newPots,
      };

      return {
        ...prev,
        profiles: newProfiles,
      };
    });

    onClose();
  };

  const handleDisableCalibration = () => {
    updateConfig((prev) => {
      const newProfiles = { ...prev.profiles };
      const profileName = prev.active_profile;
      const profile = newProfiles[profileName];
      
      if (!profile) return prev;

      const newPots = { ...profile.pots };
      const pot = newPots[String(potId)];
      
      if (!pot) return prev;

      newPots[String(potId)] = {
        ...pot,
        calibration: {
          enabled: false,
          raw_min: existingCal?.raw_min ?? 0,
          raw_max: existingCal?.raw_max ?? 1023,
        },
      };

      newProfiles[profileName] = {
        ...profile,
        pots: newPots,
      };

      return {
        ...prev,
        profiles: newProfiles,
      };
    });

    onClose();
  };

  return (
    <div className="modal-overlay" ref={overlayRef} onClick={handleOverlayClick}>
      <div className="modal calibration-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">
          Calibrate Potentiometer {potId}
          {potConfig && <span className="pot-label"> — {potConfig.label}</span>}
        </div>

        {step === "intro" && (
          <>
            <div className="calibration-description">
              <p>Calibration lets you set the physical range of your potentiometer so it maps to the full volume range in Voicemeeter.</p>
              
              {existingCal?.enabled && (
                <div className="calibration-current">
                  <strong>Current calibration:</strong>
                  <div>Min: {existingCal.raw_min} → Max: {existingCal.raw_max}</div>
                </div>
              )}
              
              <p>You will:</p>
              <ol>
                <li>Turn the pot to its <strong>minimum</strong> position</li>
                <li>Turn the pot to its <strong>maximum</strong> position</li>
              </ol>
            </div>

            <div className="modal-actions">
              {existingCal?.enabled && (
                <button className="btn-secondary btn-danger" onClick={handleDisableCalibration}>
                  Disable Calibration
                </button>
              )}
              <button className="btn-secondary" onClick={onClose}>
                Cancel
              </button>
              <button className="btn-primary" onClick={() => setStep("min")}>
                Start Calibration
              </button>
            </div>
          </>
        )}

        {step === "min" && (
          <>
            <div className="calibration-step">
              <div className="step-number">Step 1 of 2</div>
              <p>Turn the potentiometer to its <strong>minimum</strong> position (lowest volume).</p>
              
              <div className="current-value-display">
                <span className="value-label">Current Raw Value:</span>
                <span className="value-number">{currentValue ?? "—"}</span>
              </div>
            </div>

            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setStep("intro")}>
                Back
              </button>
              <button 
                className="btn-primary" 
                onClick={handleCaptureMin}
                disabled={currentValue === null}
              >
                Capture Minimum
              </button>
            </div>
          </>
        )}

        {step === "max" && (
          <>
            <div className="calibration-step">
              <div className="step-number">Step 2 of 2</div>
              <p>Turn the potentiometer to its <strong>maximum</strong> position (highest volume).</p>
              
              <div className="calibration-captured">
                <span>Minimum captured:</span>
                <strong>{minValue}</strong>
              </div>
              
              <div className="current-value-display">
                <span className="value-label">Current Raw Value:</span>
                <span className="value-number">{currentValue ?? "—"}</span>
              </div>
            </div>

            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setStep("min")}>
                Back
              </button>
              <button 
                className="btn-primary" 
                onClick={handleCaptureMax}
                disabled={currentValue === null}
              >
                Capture Maximum
              </button>
            </div>
          </>
        )}

        {step === "done" && (
          <>
            <div className="calibration-step">
              <div className="step-number">Calibration Complete!</div>
              
              <div className="calibration-summary">
                <div className="calibration-value">
                  <span>Minimum (raw):</span>
                  <strong>{minValue}</strong>
                </div>
                <div className="calibration-value">
                  <span>Maximum (raw):</span>
                  <strong>{maxValue}</strong>
                </div>
                <div className="calibration-range">
                  Range: {Math.abs((maxValue ?? 0) - (minValue ?? 0))} steps
                  {Math.abs((maxValue ?? 0) - (minValue ?? 0)) < 100 && (
                    <span className="range-warning"> ⚠️ Small range detected</span>
                  )}
                </div>
              </div>
            </div>

            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setStep("min")}>
                Redo
              </button>
              <button className="btn-primary" onClick={handleSave}>
                Save Calibration
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
