use serde::{Deserialize, Serialize};
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{
    webview::PageLoadEvent, AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};
use url::Url;

const HOST: &str = "127.0.0.1";
const STARTUP_TIMEOUT_MS: u64 = 15_000;
const POLL_INTERVAL_MS: u64 = 250;
const PACKAGED_RUNTIME_SECRET_KEY: &str = "desktop-django-starter-packaged-runtime-secret";
const RUNTIME_MANIFEST_FILENAME: &str = "runtime-manifest.json";

type ManagedChild = Arc<Mutex<Option<Child>>>;

#[derive(Default)]
struct ProcessState {
    django: Option<ManagedChild>,
    worker: Option<ManagedChild>,
}

#[derive(Default)]
struct AppState {
    processes: Mutex<ProcessState>,
    quitting: AtomicBool,
}

#[derive(Clone, Copy, Eq, PartialEq)]
enum RuntimeMode {
    Development,
    Packaged,
}

#[derive(Serialize)]
struct OpenPathResponse {
    path: String,
}

#[derive(Deserialize)]
struct RuntimeManifest {
    python: RuntimeManifestPython,
}

#[derive(Deserialize)]
struct RuntimeManifestPython {
    executable: String,
}

#[tauri::command]
fn open_app_data_directory(app: AppHandle) -> Result<OpenPathResponse, String> {
    let app_data_dir = resolve_app_data_dir(&app).map_err(|error| error.to_string())?;
    open_path(&app_data_dir).map_err(|error| error.to_string())?;

    Ok(OpenPathResponse {
        path: app_data_dir.display().to_string(),
    })
}

fn get_runtime_mode() -> RuntimeMode {
    match env::var("DESKTOP_DJANGO_RUNTIME_MODE").ok().as_deref() {
        Some("packaged") => RuntimeMode::Packaged,
        Some("development") => RuntimeMode::Development,
        _ if tauri::is_dev() => RuntimeMode::Development,
        _ => RuntimeMode::Packaged,
    }
}

fn is_smoke_test() -> bool {
    env::var("DESKTOP_DJANGO_SMOKE_TEST").ok().as_deref() == Some("1")
}

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .expect("tauri crate should live under repo/shells/tauri/src-tauri")
        .to_path_buf()
}

fn get_backend_root(app: &AppHandle, runtime_mode: RuntimeMode) -> Result<PathBuf, String> {
    if let Ok(path) = env::var("DESKTOP_DJANGO_BACKEND_ROOT") {
        return Ok(PathBuf::from(path));
    }

    if runtime_mode == RuntimeMode::Packaged {
        if tauri::is_dev() {
            return Ok(repo_root().join(".stage").join("backend"));
        }

        return app
            .path()
            .resource_dir()
            .map(|path| path.join("backend"))
            .map_err(|error| error.to_string());
    }

    Ok(repo_root())
}

fn mark_quitting(app: &AppHandle) {
    app.state::<AppState>()
        .quitting
        .store(true, Ordering::SeqCst);
}

fn is_quitting(app: &AppHandle) -> bool {
    app.state::<AppState>().quitting.load(Ordering::SeqCst)
}

fn show_runtime_error_and_exit(
    app: AppHandle,
    title: &'static str,
    message: String,
    exit_code: i32,
) {
    if is_quitting(&app) {
        return;
    }

    mark_quitting(&app);

    std::thread::spawn(move || {
        app.dialog()
            .message(message)
            .title(title)
            .kind(MessageDialogKind::Error)
            .blocking_show();
        app.exit(exit_code);
    });
}

fn focus_existing_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_minimized().unwrap_or(false) {
            let _ = window.unminimize();
        }
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn get_open_port() -> Result<u16, String> {
    let listener = TcpListener::bind((HOST, 0)).map_err(|error| error.to_string())?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| error.to_string())
}

fn health_status(port: u16) -> Option<u16> {
    let mut stream = TcpStream::connect((HOST, port)).ok()?;
    let request =
        format!("GET /health/ HTTP/1.1\r\nHost: {HOST}:{port}\r\nConnection: close\r\n\r\n");
    stream.write_all(request.as_bytes()).ok()?;

    let mut response = String::new();
    stream.read_to_string(&mut response).ok()?;
    let status_line = response.lines().next()?;
    let mut parts = status_line.split_whitespace();
    let _http_version = parts.next()?;
    parts.next()?.parse::<u16>().ok()
}

fn wait_for_django(port: u16) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_millis(STARTUP_TIMEOUT_MS);

    while Instant::now() < deadline {
        if health_status(port) == Some(200) {
            return Ok(());
        }

        thread::sleep(Duration::from_millis(POLL_INTERVAL_MS));
    }

    Err(format!(
        "Django did not become ready within {}ms.",
        STARTUP_TIMEOUT_MS
    ))
}

fn resolve_app_data_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?;
    fs::create_dir_all(&app_data_dir).map_err(|error| error.to_string())?;
    Ok(app_data_dir)
}

fn resolve_bundled_python_executable(backend_root: &Path) -> Result<PathBuf, String> {
    let manifest_path = backend_root.join(RUNTIME_MANIFEST_FILENAME);
    if manifest_path.exists() {
        let manifest = serde_json::from_str::<RuntimeManifest>(
            &fs::read_to_string(&manifest_path).map_err(|error| error.to_string())?,
        )
        .map_err(|error| error.to_string())?;
        let executable = backend_root.join(manifest.python.executable);
        if executable.exists() {
            return Ok(executable);
        }

        return Err(format!(
            "Bundled Python manifest points to a missing interpreter: {}",
            executable.display()
        ));
    }

    let candidates = if cfg!(target_os = "windows") {
        vec![
            backend_root.join("python").join("python.exe"),
            backend_root
                .join("python")
                .join("Scripts")
                .join("python.exe"),
        ]
    } else {
        vec![
            backend_root.join("python").join("bin").join("python3"),
            backend_root.join("python").join("bin").join("python"),
        ]
    };

    candidates
        .into_iter()
        .find(|candidate| candidate.exists())
        .ok_or_else(|| {
            format!(
                "No bundled Python runtime found under {}.",
                backend_root.join("python").display()
            )
        })
}

fn validate_packaged_backend_root(backend_root: &Path) -> Result<(), String> {
    let required_paths = [
        backend_root.join("manage.py"),
        backend_root.join("src").join("desktop_django_starter"),
        backend_root.join("src").join("example_app"),
        backend_root.join("src").join("tasks_demo"),
        backend_root.join("staticfiles"),
        backend_root.join("python"),
        backend_root.join(RUNTIME_MANIFEST_FILENAME),
    ];

    let missing_paths = required_paths
        .iter()
        .filter(|path| !path.exists())
        .map(|path| path.display().to_string())
        .collect::<Vec<_>>();

    if missing_paths.is_empty() {
        return Ok(());
    }

    let hint = if tauri::is_dev() {
        "Run `npm --prefix shells/tauri run stage-backend` first."
    } else {
        "The bundled app resources are missing the staged backend payload."
    };

    Err(format!(
        "Packaged backend bundle is incomplete at {}.\nMissing:\n{}\n\n{}",
        backend_root.display(),
        missing_paths.join("\n"),
        hint
    ))
}

fn base_command(runtime_mode: RuntimeMode, backend_root: &Path) -> Result<Command, String> {
    if let Ok(path) = env::var("DESKTOP_DJANGO_PYTHON") {
        return Ok(Command::new(path));
    }

    if runtime_mode == RuntimeMode::Packaged {
        return Ok(Command::new(resolve_bundled_python_executable(
            backend_root,
        )?));
    }

    let mut command = Command::new(if cfg!(target_os = "windows") {
        "uv.exe"
    } else {
        "uv"
    });
    command.arg("run").arg("python");
    Ok(command)
}

fn configure_manage_command(
    app: &AppHandle,
    runtime_mode: RuntimeMode,
    backend_root: &Path,
    port: u16,
    manage_args: &[&str],
) -> Result<Command, String> {
    let mut command = base_command(runtime_mode, backend_root)?;
    let app_data_dir = resolve_app_data_dir(app)?;
    let settings_module = if runtime_mode == RuntimeMode::Packaged {
        "desktop_django_starter.settings.packaged"
    } else {
        "desktop_django_starter.settings.local"
    };

    command
        .current_dir(backend_root)
        .env("DJANGO_SETTINGS_MODULE", settings_module)
        .env("DESKTOP_DJANGO_APP_DATA_DIR", &app_data_dir)
        .env("DESKTOP_DJANGO_BUNDLE_DIR", backend_root)
        .env("DESKTOP_DJANGO_HOST", HOST)
        .env("DESKTOP_DJANGO_PORT", port.to_string())
        .env("PYTHONUNBUFFERED", "1")
        .arg("manage.py");

    if runtime_mode == RuntimeMode::Packaged && env::var("DJANGO_SECRET_KEY").is_err() {
        command.env("DJANGO_SECRET_KEY", PACKAGED_RUNTIME_SECRET_KEY);
    }

    for argument in manage_args {
        command.arg(argument);
    }

    Ok(command)
}

fn run_manage_command(
    app: &AppHandle,
    runtime_mode: RuntimeMode,
    backend_root: &Path,
    port: u16,
    manage_args: &[&str],
) -> Result<(), String> {
    let output = configure_manage_command(app, runtime_mode, backend_root, port, manage_args)?
        .output()
        .map_err(|error| error.to_string())?;

    if output.status.success() {
        return Ok(());
    }

    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    Err(if stderr.is_empty() {
        format!("manage.py {} failed.", manage_args.join(" "))
    } else {
        stderr
    })
}

fn start_managed_process(
    app: &AppHandle,
    runtime_mode: RuntimeMode,
    backend_root: &Path,
    port: u16,
    manage_args: &[&str],
) -> Result<Child, String> {
    configure_manage_command(app, runtime_mode, backend_root, port, manage_args)?
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| error.to_string())
}

fn register_managed_process(
    app: &AppHandle,
    process_name: &'static str,
    exit_title: &'static str,
    exit_summary: &'static str,
    child: Child,
) -> ManagedChild {
    let child = Arc::new(Mutex::new(Some(child)));

    {
        let state = app.state::<AppState>();
        let mut processes = state.processes.lock().unwrap();
        if process_name == "django" {
            processes.django = Some(child.clone());
        } else {
            processes.worker = Some(child.clone());
        }
    }

    start_process_monitor(
        app.clone(),
        process_name,
        exit_title,
        exit_summary,
        child.clone(),
    );
    child
}

fn start_process_monitor(
    app: AppHandle,
    process_name: &'static str,
    exit_title: &'static str,
    exit_summary: &'static str,
    child: ManagedChild,
) {
    thread::spawn(move || loop {
        if is_quitting(&app) {
            return;
        }

        let exit_message = {
            let mut child = child.lock().unwrap();
            let Some(process) = child.as_mut() else {
                return;
            };

            match process.try_wait() {
                Ok(Some(status)) => {
                    *child = None;
                    Some(format!(
                        "{exit_summary}\n\nProcess: {process_name}\nStatus: {status}"
                    ))
                }
                Ok(None) => None,
                Err(error) => {
                    *child = None;
                    Some(format!(
                        "{exit_summary}\n\nProcess: {process_name}\nMonitor error: {error}"
                    ))
                }
            }
        };

        if let Some(message) = exit_message {
            show_runtime_error_and_exit(app.clone(), exit_title, message, 1);
            return;
        }

        thread::sleep(Duration::from_millis(POLL_INTERVAL_MS));
    });
}

fn inject_desktop_bridge() -> &'static str {
    r#"
window.desktop = window.desktop || {};
window.desktop.openAppDataDirectory = () => window.__TAURI__.core.invoke("open_app_data_directory");
"#
}

fn create_main_window(app: &AppHandle, url: &str) -> Result<WebviewWindow, String> {
    let external_url = Url::parse(url).map_err(|error| error.to_string())?;
    let smoke_test = is_smoke_test();

    WebviewWindowBuilder::new(app, "main", WebviewUrl::External(external_url))
        .title("Desktop Django Starter")
        .inner_size(1200.0, 840.0)
        .initialization_script(inject_desktop_bridge())
        .on_page_load(move |window, payload| {
            if smoke_test && matches!(payload.event(), PageLoadEvent::Finished) {
                let handle = window.app_handle().clone();
                thread::spawn(move || {
                    thread::sleep(Duration::from_millis(750));
                    mark_quitting(&handle);
                    handle.exit(0);
                });
            }
        })
        .build()
        .map_err(|error| error.to_string())
}

fn open_path(path: &Path) -> Result<(), String> {
    let status = if cfg!(target_os = "macos") {
        Command::new("open")
            .arg(path)
            .status()
            .map_err(|error| error.to_string())?
    } else if cfg!(target_os = "windows") {
        Command::new("explorer")
            .arg(path)
            .status()
            .map_err(|error| error.to_string())?
    } else {
        Command::new("xdg-open")
            .arg(path)
            .status()
            .map_err(|error| error.to_string())?
    };

    if status.success() {
        Ok(())
    } else {
        Err(format!("Failed to open {}.", path.display()))
    }
}

fn bootstrap(app: &AppHandle) -> Result<(), String> {
    let runtime_mode = get_runtime_mode();
    let backend_root = get_backend_root(app, runtime_mode)?;
    let port = get_open_port()?;
    let base_url = format!("http://{HOST}:{port}");

    if runtime_mode == RuntimeMode::Packaged {
        validate_packaged_backend_root(&backend_root)?;
    }

    run_manage_command(
        app,
        runtime_mode,
        &backend_root,
        port,
        &["migrate", "--noinput"],
    )?;

    let django = start_managed_process(
        app,
        runtime_mode,
        &backend_root,
        port,
        &["runserver", &format!("{HOST}:{port}"), "--noreload"],
    )?;
    register_managed_process(
        app,
        "django",
        "Django exited",
        "The Django process stopped before the desktop app finished.",
        django,
    );

    if let Err(error) = wait_for_django(port) {
        stop_managed_processes(app);
        return Err(error);
    }

    let worker = start_managed_process(
        app,
        runtime_mode,
        &backend_root,
        port,
        &[
            "db_worker",
            "--queue-name",
            "default",
            "--worker-id",
            "desktop-django-starter-tauri",
        ],
    )?;
    register_managed_process(
        app,
        "worker",
        "Task worker exited",
        "The background task worker stopped before the desktop app finished.",
        worker,
    );

    let _window = create_main_window(app, &base_url)?;
    Ok(())
}

fn stop_child(child: ManagedChild) {
    let mut child = child.lock().unwrap();
    let Some(process) = child.as_mut() else {
        return;
    };

    if cfg!(target_os = "windows") {
        let _ = Command::new("taskkill")
            .args(["/pid", &process.id().to_string(), "/t", "/f"])
            .status();
    } else {
        let _ = process.kill();
    }

    let _ = process.wait();
    *child = None;
}

fn stop_managed_processes(app: &AppHandle) {
    mark_quitting(app);

    let state = app.state::<AppState>();
    let mut state = state.processes.lock().unwrap();

    if let Some(worker) = state.worker.take() {
        stop_child(worker);
    }

    if let Some(django) = state.django.take() {
        stop_child(django);
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            focus_existing_window(app);
        }))
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![open_app_data_directory])
        .setup(|app| {
            if let Err(error) = bootstrap(&app.handle()) {
                show_runtime_error_and_exit(app.handle().clone(), "Startup failed", error, 1);
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app, event| {
        if matches!(
            event,
            tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }
        ) {
            stop_managed_processes(app);
        }
    });
}
