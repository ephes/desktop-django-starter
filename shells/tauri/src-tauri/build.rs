fn main() {
    // Declaring the app command in an ACL manifest makes Tauri check it
    // against capabilities. Django pages are a remote origin to Tauri, so
    // capabilities/django-pages.json grants this one command to them.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["open_app_data_directory"]),
    ))
    .expect("failed to run tauri-build");
}
