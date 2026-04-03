import {
  readTextFile,
  writeTextFile,
  createDir,
  exists,
} from "@tauri-apps/api/fs";
import { homeDir, join } from "@tauri-apps/api/path";
import type { AppConfig } from "./types";

export const DEFAULT_CONFIG: AppConfig = {
  serial_port: "COM3",
  active_profile: "Default",
  display: {
    grid_rows: 2,
    grid_cols: 6,
    num_pots: 4,
  },
  hardware: {
    row_pins: [2, 3, 4, 5, 6, 7],
    col_pins: [8, 9, 10, 11],
    pot_pins: [0, 1, 2, 3],
  },
  profile_toggle: {
    button_id: -1,
    mode: "hold",
    hold_ms: 500,
  },
  profiles: {
    Default: {
      buttons: {
        "0": { label: "Mute Mic", action: "ctrl+alt+m" },
        "1": { label: "Screenshot", action: "ctrl+shift+s" },
        "2": { label: "Alt+Tab", action: "alt+tab" },
        "3": { label: "Copy", action: "ctrl+c" },
        "4": { label: "Paste", action: "ctrl+v" },
        "5": { label: "Vol Up", action: "volume up" },
        "6": { label: "Vol Down", action: "volume down" },
        "7": { label: "Play/Pause", action: "play/pause media" },
        "8": { label: "Next", action: "next track" },
        "9": { label: "Prev", action: "previous track" },
        "10": { label: "Desktop", action: "win+d" },
        "11": { label: "Explorer", action: "win+e" },
      },
      pots: {
        "0": { label: "HW Input 1", strip: 0 },
        "1": { label: "HW Input 2", strip: 1 },
        "2": { label: "Virtual 1", strip: 3 },
        "3": { label: "Virtual 2", strip: 4 },
      },
    },
  },
};

async function getStreamdeckDir(): Promise<string> {
  const home = await homeDir();
  return await join(home, ".streamdeck");
}

export async function getConfigPath(): Promise<string> {
  const dir = await getStreamdeckDir();
  return await join(dir, "config.json");
}

export async function loadConfig(): Promise<AppConfig> {
  const dir = await getStreamdeckDir();
  const configPath = await join(dir, "config.json");

  // Ensure directory exists
  const dirExists = await exists(dir);
  if (!dirExists) {
    await createDir(dir, { recursive: true });
  }

  // Create default config if not exists
  const fileExists = await exists(configPath);
  if (!fileExists) {
    await writeTextFile(configPath, JSON.stringify(DEFAULT_CONFIG, null, 2));
    return structuredClone(DEFAULT_CONFIG);
  }

  const raw = await readTextFile(configPath);
  const parsed = JSON.parse(raw) as AppConfig;
  return parsed;
}

export async function saveConfig(config: AppConfig): Promise<void> {
  const configPath = await getConfigPath();
  await writeTextFile(configPath, JSON.stringify(config, null, 2));
}
