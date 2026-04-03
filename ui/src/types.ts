export interface ButtonConfig {
  label: string;
  action: string;
}

export interface PotConfig {
  label: string;
  strip: number;
}

export interface Profile {
  buttons: Record<string, ButtonConfig>;
  pots: Record<string, PotConfig>;
}

export interface ProfileToggle {
  button_id: number;
  mode: "hold" | "tap";
  hold_ms: number;
}

export interface Display {
  grid_rows: number;
  grid_cols: number;
  num_pots: number;
}

export interface Hardware {
  row_pins: number[];
  col_pins: number[];
  pot_pins: number[];
}

export interface AppConfig {
  serial_port: string;
  active_profile: string;
  display: Display;
  hardware: Hardware;
  profile_toggle: ProfileToggle;
  profiles: Record<string, Profile>;
}
