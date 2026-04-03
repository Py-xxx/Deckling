import type { AppConfig } from "../types";

interface Props {
  config: AppConfig;
  updateConfig: (updater: (prev: AppConfig) => AppConfig) => void;
  onButtonClick: (buttonId: number) => void;
}

export default function ButtonGrid({ config, onButtonClick }: Props) {
  const { grid_rows, grid_cols } = config.display;
  const total = grid_rows * grid_cols;
  const profile = config.profiles[config.active_profile];
  const toggleId = config.profile_toggle.button_id;

  const cells = Array.from({ length: total }, (_, i) => i);

  return (
    <div
      className="button-grid"
      style={{ gridTemplateColumns: `repeat(${grid_cols}, 88px)` }}
    >
      {cells.map((id) => {
        const binding = profile?.buttons[String(id)];
        const isToggle = id === toggleId;
        const isEmpty = !binding;

        let classes = "btn-cell";
        if (isToggle) classes += " is-toggle";
        else if (binding?.action) classes += " has-action";
        if (isEmpty && !isToggle) classes += " btn-empty";

        return (
          <div
            key={id}
            className={classes}
            onClick={() => onButtonClick(id)}
            title={binding ? `${binding.label} — ${binding.action}` : `Button ${id}`}
          >
            <span className="btn-id">{id}</span>

            {isToggle ? (
              <>
                <span className="btn-label" style={{ color: "var(--toggle-color)" }}>
                  {binding?.label || ""}
                </span>
                <span className="btn-toggle-indicator">PROFILE</span>
              </>
            ) : (
              <>
                <span className="btn-label">{binding?.label || "—"}</span>
                {binding?.action && (
                  <span className="btn-action">{binding.action}</span>
                )}
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
