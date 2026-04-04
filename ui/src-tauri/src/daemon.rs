//! Background daemon that processes Arduino messages.
//!
//! Handles:
//! - Potentiometer values → Voicemeeter strip gain
//! - Button presses → Keyboard shortcuts
//! - Profile toggle button

use crate::config::{load_config, AppConfig};
use crate::keyboard::execute_action;
use crate::serial::{ArduinoMessage, ConnectionState, SerialManager};
#[cfg(windows)]
use crate::voicemeeter;
use parking_lot::Mutex;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

/// Daemon state
pub struct Daemon {
    serial: Arc<SerialManager>,
    config: Arc<Mutex<AppConfig>>,
    last_pot_values: Arc<Mutex<HashMap<u8, i16>>>,
    last_raw_pot_values: Arc<Mutex<HashMap<u8, u16>>>, // For calibration
    button_press_times: Arc<Mutex<HashMap<u8, Instant>>>,
    vm_available: Arc<Mutex<bool>>,
}

impl Daemon {
    /// Create a new daemon instance
    pub fn new() -> Self {
        let config = load_config().unwrap_or_default();
        
        Self {
            serial: Arc::new(SerialManager::new()),
            config: Arc::new(Mutex::new(config)),
            last_pot_values: Arc::new(Mutex::new(HashMap::new())),
            last_raw_pot_values: Arc::new(Mutex::new(HashMap::new())),
            button_press_times: Arc::new(Mutex::new(HashMap::new())),
            vm_available: Arc::new(Mutex::new(false)),
        }
    }

    /// Get the last raw value for a potentiometer (for calibration)
    pub fn get_raw_pot_value(&self, pot_id: u8) -> Option<u16> {
        self.last_raw_pot_values.lock().get(&pot_id).copied()
    }

    /// Initialize Voicemeeter connection
    #[cfg(windows)]
    pub fn init_voicemeeter(&self) -> bool {
        match voicemeeter::init() {
            Ok(()) => {
                *self.vm_available.lock() = true;
                true
            }
            Err(e) => {
                eprintln!("Voicemeeter init failed: {}", e);
                *self.vm_available.lock() = false;
                false
            }
        }
    }

    /// Initialize Voicemeeter connection (non-Windows stub)
    #[cfg(not(windows))]
    pub fn init_voicemeeter(&self) -> bool {
        false
    }

    /// Check if Voicemeeter is available
    pub fn is_voicemeeter_available(&self) -> bool {
        *self.vm_available.lock()
    }

    /// Get serial manager reference
    pub fn serial(&self) -> Arc<SerialManager> {
        Arc::clone(&self.serial)
    }

    /// Get current connection state
    pub fn connection_state(&self) -> ConnectionState {
        self.serial.state()
    }

    /// Update config (called when UI saves)
    pub fn update_config(&self, config: AppConfig) {
        *self.config.lock() = config;
        // Clear cached pot values to force resync
        self.last_pot_values.lock().clear();
    }

    /// Reload config from disk
    pub fn reload_config(&self) {
        if let Ok(config) = load_config() {
            self.update_config(config);
        }
    }

    /// Connect to serial port and start processing
    pub fn connect(&self, port: &str) -> Result<(), String> {
        let config = Arc::clone(&self.config);
        let last_pot_values = Arc::clone(&self.last_pot_values);
        let last_raw_pot_values = Arc::clone(&self.last_raw_pot_values);
        let button_press_times = Arc::clone(&self.button_press_times);
        let vm_available = Arc::clone(&self.vm_available);

        // Set up message callback
        self.serial.set_callback(move |msg| {
            let config = config.lock().clone();
            Self::handle_message(
                msg,
                &config,
                &last_pot_values,
                &last_raw_pot_values,
                &button_press_times,
                *vm_available.lock(),
            );
        });

        // Connect to port
        self.serial.connect(port)
    }

    /// Disconnect from serial port
    pub fn disconnect(&self) {
        self.serial.disconnect();
    }

    /// Handle an incoming Arduino message
    fn handle_message(
        msg: ArduinoMessage,
        config: &AppConfig,
        last_pot_values: &Mutex<HashMap<u8, i16>>,
        last_raw_pot_values: &Mutex<HashMap<u8, u16>>,
        button_press_times: &Mutex<HashMap<u8, Instant>>,
        vm_available: bool,
    ) {
        match msg {
            ArduinoMessage::Pot { id, value } => {
                // Store raw value for calibration
                last_raw_pot_values.lock().insert(id, value);
                Self::handle_pot(id, value, config, last_pot_values, vm_available);
            }
            ArduinoMessage::Button { id, pressed } => {
                Self::handle_button(id, pressed, config, button_press_times);
            }
        }
    }

    /// Handle potentiometer value change (Windows with Voicemeeter)
    #[cfg(windows)]
    fn handle_pot(
        id: u8,
        raw: u16,
        config: &AppConfig,
        last_pot_values: &Mutex<HashMap<u8, i16>>,
        vm_available: bool,
    ) {
        if !vm_available {
            return;
        }

        // Get active profile
        let profile = match config.profiles.get(&config.active_profile) {
            Some(p) => p,
            None => return,
        };

        // Get pot config
        let pot_cfg = match profile.pots.get(&id.to_string()) {
            Some(p) => p,
            None => return,
        };

        // Check if this pot is assigned to a strip
        let strip = pot_cfg.strip;
        if strip < 0 {
            return;
        }

        // Convert to dB - use calibration if enabled, otherwise use default curve
        // Note: When calibration is enabled, we use the raw value directly since
        // calibration captures the actual pot range. invert_pots only applies
        // to non-calibrated pots.
        let gain_db = if let Some(ref cal) = pot_cfg.calibration {
            if cal.enabled {
                // Calibration uses raw values directly - it already knows the pot's direction
                voicemeeter::raw_to_gain_db_calibrated(raw, cal.raw_min, cal.raw_max)
            } else {
                // Apply invert only for non-calibrated pots
                let adjusted = if config.hardware.invert_pots { 1023 - raw } else { raw };
                voicemeeter::raw_to_gain_db_with_curve(adjusted, config.hardware.pot_ohms)
            }
        } else {
            // Apply invert only for non-calibrated pots
            let adjusted = if config.hardware.invert_pots { 1023 - raw } else { raw };
            voicemeeter::raw_to_gain_db_with_curve(adjusted, config.hardware.pot_ohms)
        };
        let gain_int = gain_db.round() as i16;

        // Check if changed (integer comparison to reduce jitter)
        let mut last_values = last_pot_values.lock();
        if last_values.get(&id) == Some(&gain_int) {
            return;
        }
        last_values.insert(id, gain_int);

        // Set Voicemeeter strip gain
        if let Err(e) = voicemeeter::set_strip_gain(strip as u8, gain_db) {
            eprintln!("Voicemeeter error: {}", e);
        }
    }

    /// Handle potentiometer value change (non-Windows stub)
    #[cfg(not(windows))]
    fn handle_pot(
        _id: u8,
        _raw: u16,
        _config: &AppConfig,
        _last_pot_values: &Mutex<HashMap<u8, i16>>,
        _vm_available: bool,
    ) {
        // No-op on non-Windows
    }

    /// Handle button press/release
    fn handle_button(
        id: u8,
        pressed: bool,
        config: &AppConfig,
        button_press_times: &Mutex<HashMap<u8, Instant>>,
    ) {
        // Convert Arduino button ID to (row_pin, col_pin)
        // Arduino calculates: id = row_index * num_cols + col_index
        let num_cols = config.hardware.col_pins.len();
        if num_cols == 0 {
            return;
        }
        
        let row_index = (id as usize) / num_cols;
        let col_index = (id as usize) % num_cols;
        
        let row_pin = config.hardware.row_pins.get(row_index).copied();
        let col_pin = config.hardware.col_pins.get(col_index).copied();
        
        let (row_pin, col_pin) = match (row_pin, col_pin) {
            (Some(r), Some(c)) => (r, c),
            _ => return, // Invalid button ID
        };
        
        // Find UI button position that maps to this pin pair
        let ui_button_id = config.hardware.button_pins.iter()
            .find(|(_, mapping)| mapping.row_pin == row_pin && mapping.col_pin == col_pin)
            .map(|(id, _)| id.clone());
        
        let ui_button_id = match ui_button_id {
            Some(id) => id,
            None => {
                // No mapping found, fall back to raw ID
                id.to_string()
            }
        };
        
        // Parse UI button ID to u8 for toggle check
        let ui_button_num: u8 = ui_button_id.parse().unwrap_or(id);
        
        let toggle = &config.profile_toggle;

        // Check if this is the profile toggle button
        if toggle.button_id >= 0 && ui_button_num == toggle.button_id as u8 {
            Self::handle_profile_toggle(pressed, config, button_press_times, ui_button_num);
            return;
        }

        // Normal button - only act on press
        if !pressed {
            return;
        }

        // Get active profile
        let profile = match config.profiles.get(&config.active_profile) {
            Some(p) => p,
            None => return,
        };

        // Get button config using UI button ID
        let btn_cfg = match profile.buttons.get(&ui_button_id) {
            Some(b) => b,
            None => return,
        };

        // Execute action
        if !btn_cfg.action.is_empty() {
            execute_action(&btn_cfg.action);
        }
    }

    /// Handle profile toggle button
    fn handle_profile_toggle(
        pressed: bool,
        config: &AppConfig,
        button_press_times: &Mutex<HashMap<u8, Instant>>,
        btn_id: u8,
    ) {
        let toggle = &config.profile_toggle;

        match toggle.mode.as_str() {
            "tap" => {
                if pressed {
                    Self::cycle_profile(config);
                }
            }
            "hold" => {
                if pressed {
                    button_press_times.lock().insert(btn_id, Instant::now());
                } else {
                    // Release
                    if let Some(press_time) = button_press_times.lock().remove(&btn_id) {
                        let elapsed_ms = press_time.elapsed().as_millis() as u32;
                        if elapsed_ms >= toggle.hold_ms {
                            Self::cycle_profile(config);
                        }
                    }
                }
            }
            _ => {}
        }
    }

    /// Cycle to the next profile
    fn cycle_profile(config: &AppConfig) {
        let cycle_profiles = &config.profile_toggle.cycle_profiles;
        
        // Get profiles to cycle through
        let profiles: Vec<&String> = if cycle_profiles.is_empty() {
            // Cycle through all profiles
            let mut all: Vec<&String> = config.profiles.keys().collect();
            all.sort();
            all
        } else {
            // Cycle through selected profiles only
            let mut selected: Vec<&String> = config.profiles.keys()
                .filter(|k| cycle_profiles.contains(k))
                .collect();
            selected.sort();
            selected
        };

        if profiles.is_empty() {
            return;
        }

        let current = &config.active_profile;
        let idx = profiles.iter().position(|p| *p == current).unwrap_or(0);
        let next_idx = (idx + 1) % profiles.len();
        let next_profile = profiles[next_idx].clone();

        // Update config file
        if let Ok(mut new_config) = load_config() {
            new_config.active_profile = next_profile;
            if let Err(e) = crate::config::save_config(&new_config) {
                eprintln!("Failed to save config: {}", e);
            }
        }
    }
}

impl Default for Daemon {
    fn default() -> Self {
        Self::new()
    }
}
