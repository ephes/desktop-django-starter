// Release builds on Windows use the GUI subsystem, so no console window opens
// next to the app.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    desktop_django_starter_tauri_lib::run();
}
