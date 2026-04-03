import type { AppConfig } from "../types";

interface Props {
  config: AppConfig;
  updateConfig: (updater: (prev: AppConfig) => AppConfig) => void;
}

export default function ProfileBar({ config, updateConfig }: Props) {
  const profileNames = Object.keys(config.profiles).sort();
  const canDelete = profileNames.length > 1;

  const switchProfile = (name: string) => {
    updateConfig((prev) => ({ ...prev, active_profile: name }));
  };

  const deleteProfile = (name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!canDelete) return;

    updateConfig((prev) => {
      const next = { ...prev };
      const remaining = { ...next.profiles };
      delete remaining[name];
      const remainingNames = Object.keys(remaining).sort();
      const newActive =
        next.active_profile === name
          ? remainingNames[0]
          : next.active_profile;
      return {
        ...next,
        profiles: remaining,
        active_profile: newActive,
      };
    });
  };

  const addProfile = () => {
    const name = window.prompt("New profile name:");
    if (!name || !name.trim()) return;
    const trimmed = name.trim();

    if (config.profiles[trimmed]) {
      window.alert(`Profile "${trimmed}" already exists.`);
      return;
    }

    updateConfig((prev) => {
      // Clone current active profile as starting point
      const currentProfile = prev.profiles[prev.active_profile];
      const cloned = JSON.parse(JSON.stringify(currentProfile));
      return {
        ...prev,
        profiles: {
          ...prev.profiles,
          [trimmed]: cloned,
        },
        active_profile: trimmed,
      };
    });
  };

  return (
    <div className="profile-bar">
      {profileNames.map((name) => {
        const isActive = name === config.active_profile;
        return (
          <button
            key={name}
            className={`profile-tab${isActive ? " active" : ""}`}
            onClick={() => switchProfile(name)}
          >
            <span>{name}</span>
            {canDelete && (
              <span
                className={
                  isActive
                    ? "profile-delete-btn"
                    : "profile-delete-btn-inactive"
                }
                onClick={(e) => deleteProfile(name, e)}
                title={`Delete "${name}"`}
              >
                ×
              </span>
            )}
          </button>
        );
      })}
      <button className="profile-add-btn" onClick={addProfile} title="Add profile">
        +
      </button>
    </div>
  );
}
