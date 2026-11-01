use serde::{Deserialize, Serialize};
use std::env;
use std::ffi::OsString;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{
    webview::PageLoadEvent, AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_updater::UpdaterExt;
use url::Url;

const HOST: &str = "127.0.0.1";
const STARTUP_TIMEOUT_MS: u64 = 15_000;
const HEALTH_REQUEST_TIMEOUT_MS: u64 = 1_000;
const POLL_INTERVAL_MS: u64 = 250;
const MINIMUM_SPLASH_DURATION_MS: u64 = 2_400;
const SHUTDOWN_GRACE_PERIOD_MS: u64 = 2_000;
const RUNTIME_MANIFEST_FILENAME: &str = "runtime-manifest.json";
const SPLASH_WINDOW_LABEL: &str = "splash";
const DESKTOP_AUTH_HEADER: &str = "X-Desktop-Django-Token";
const DESKTOP_AUTH_BOOTSTRAP_PATH: &str = "/desktop-auth/bootstrap/";
const TAURI_UPDATE_ENDPOINTS_ENV: &str = "DESKTOP_DJANGO_TAURI_UPDATE_ENDPOINTS";
const TAURI_UPDATE_PUBLIC_KEY_ENV: &str = "DESKTOP_DJANGO_TAURI_UPDATE_PUBLIC_KEY";
const DESKTOP_ACTIVITY_PATH: &str = "/desktop/activity/";
const PROCESS_GUARD_FILENAME: &str = "desktop_process_guard.py";
const SHELL_SESSION_FILENAME: &str = "desktop-shell-session.json";
const STATE_DIRNAME: &str = "state";
const UNVERSIONED_STATE_DIRNAME: &str = "unversioned";
#[cfg(target_os = "macos")]
const QUIT_MENU_ID: &str = "desktop-django-starter-quit";

type ManagedChild = Arc<Mutex<Option<Child>>>;

#[derive(Default)]
struct ProcessState {
    django: Option<ManagedChild>,
    worker: Option<ManagedChild>,
}

/// Identifies this shell's backend processes on their command line, so a
/// later launch can find leftovers of a crashed run (see `stop_orphaned_processes`).
#[derive(Clone)]
struct GuardIdentity {
    app_key: String,
    instance_id: String,
}

/// `<app-data>/desktop-shell-session.json`: records whether the previous run
/// shut down cleanly and keeps the per-install app key.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
struct ShellSession {
    app_key: String,
    running: bool,
    shell_pid: u32,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
struct ActivityCounts {
    running_tasks: u64,
    queued_tasks: u64,
}

#[derive(Default)]
struct AppState {
    processes: Mutex<ProcessState>,
    quitting: AtomicBool,
    update_check_started: AtomicBool,
    django_origin: Mutex<Option<String>>,
    guard_identity: Mutex<Option<GuardIdentity>>,
    /// Session file path; taken when the clean shutdown is recorded.
    session_path: Mutex<Option<PathBuf>>,
    /// Django port and auth token, set once Django and the worker are up.
    activity_endpoint: Mutex<Option<(u16, String)>>,
    exit_confirmed: AtomicBool,
    exit_check_in_progress: AtomicBool,
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

struct UpdaterConfig {
    endpoints: Vec<Url>,
    pubkey: String,
}

#[tauri::command]
fn open_app_data_directory(
    app: AppHandle,
    webview: tauri::Webview,
) -> Result<OpenPathResponse, String> {
    // The capability allows any 127.0.0.1 port; only the exact Django origin
    // of this session may use the bridge.
    let expected_origin = app.state::<AppState>().django_origin.lock().unwrap().clone();
    let caller_url = webview.url().map_err(|error| error.to_string())?;
    if !is_trusted_bridge_caller(&caller_url, expected_origin.as_deref()) {
        return Err("The desktop bridge is only available to the local Django app.".to_string());
    }

    let app_data_dir = resolve_app_data_dir(&app).map_err(|error| error.to_string())?;
    open_path(&app_data_dir).map_err(|error| error.to_string())?;

    Ok(OpenPathResponse {
        path: app_data_dir.display().to_string(),
    })
}

fn is_trusted_bridge_caller(caller_url: &Url, expected_origin: Option<&str>) -> bool {
    match expected_origin.and_then(|origin| Url::parse(origin).ok()) {
        Some(expected) => caller_url.origin() == expected.origin(),
        None => false,
    }
}

fn get_runtime_mode() -> RuntimeMode {
    match env::var("DESKTOP_DJANGO_RUNTIME_MODE").ok().as_deref() {
        Some("packaged") => RuntimeMode::Packaged,
        Some("development") => RuntimeMode::Development,
        _ if tauri::is_dev() => RuntimeMode::Development,
        _ => RuntimeMode::Packaged,
    }
}

fn configured_updater_value(runtime_name: &str, build_time_value: Option<&str>) -> Option<String> {
    env::var(runtime_name)
        .ok()
        .or_else(|| build_time_value.map(str::to_string))
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn parse_updater_endpoints(raw: &str) -> Result<Vec<Url>, String> {
    let endpoints = raw
        .split([',', '\n'])
        .map(str::trim)
        .filter(|entry| !entry.is_empty())
        .map(|entry| Url::parse(entry).map_err(|error| error.to_string()))
        .collect::<Result<Vec<_>, _>>()?;

    if endpoints.is_empty() {
        return Err("No updater endpoints were configured.".to_string());
    }

    Ok(endpoints)
}

fn resolve_updater_config() -> Result<Option<UpdaterConfig>, String> {
    let endpoints = configured_updater_value(
        TAURI_UPDATE_ENDPOINTS_ENV,
        option_env!("DESKTOP_DJANGO_TAURI_UPDATE_ENDPOINTS"),
    );
    let pubkey = configured_updater_value(
        TAURI_UPDATE_PUBLIC_KEY_ENV,
        option_env!("DESKTOP_DJANGO_TAURI_UPDATE_PUBLIC_KEY"),
    );

    match (endpoints, pubkey) {
        (None, None) => Ok(None),
        (Some(_), None) => Err(format!(
            "{TAURI_UPDATE_PUBLIC_KEY_ENV} must be configured when updater endpoints are enabled."
        )),
        (None, Some(_)) => Err(format!(
            "{TAURI_UPDATE_ENDPOINTS_ENV} must be configured when the Tauri updater public key is set."
        )),
        (Some(endpoints), Some(pubkey)) => Ok(Some(UpdaterConfig {
            endpoints: parse_updater_endpoints(&endpoints)?,
            pubkey,
        })),
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
    close_splash_window(&app);

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

fn local_get(port: u16, path: &str, auth_token: &str) -> Option<String> {
    // Bounded timeouts keep a listener that accepts but never answers from
    // blocking past the startup deadline (or a quit).
    let address = std::net::SocketAddr::from(([127, 0, 0, 1], port));
    let timeout = Duration::from_millis(HEALTH_REQUEST_TIMEOUT_MS);
    let mut stream = TcpStream::connect_timeout(&address, timeout).ok()?;
    stream.set_read_timeout(Some(timeout)).ok()?;
    stream.set_write_timeout(Some(timeout)).ok()?;
    let auth_header = if auth_token.is_empty() {
        String::new()
    } else {
        format!("{DESKTOP_AUTH_HEADER}: {auth_token}\r\n")
    };
    let request = format!(
        "GET {path} HTTP/1.1\r\nHost: {HOST}:{port}\r\n{auth_header}Connection: close\r\n\r\n"
    );
    stream.write_all(request.as_bytes()).ok()?;

    let mut response = String::new();
    stream.read_to_string(&mut response).ok()?;
    Some(response)
}

fn response_status(response: &str) -> Option<u16> {
    let status_line = response.lines().next()?;
    let mut parts = status_line.split_whitespace();
    let _http_version = parts.next()?;
    parts.next()?.parse::<u16>().ok()
}

fn health_status(port: u16, auth_token: &str) -> Option<u16> {
    response_status(&local_get(port, "/health/", auth_token)?)
}

fn parse_activity_response(response: &str) -> Option<ActivityCounts> {
    if response_status(response)? != 200 {
        return None;
    }
    let (_headers, body) = response.split_once("\r\n\r\n")?;
    serde_json::from_str(body.trim()).ok()
}

fn fetch_activity(port: u16, auth_token: &str) -> Option<ActivityCounts> {
    parse_activity_response(&local_get(port, DESKTOP_ACTIVITY_PATH, auth_token)?)
}

fn exit_confirmation_message(counts: ActivityCounts) -> Option<String> {
    if counts.running_tasks + counts.queued_tasks == 0 {
        return None;
    }
    // Running tasks are interrupted by quitting; queued tasks stay in the
    // database and start when the app runs again.
    let plural = |count: u64, noun: &str| {
        format!("{count} {noun}{}", if count == 1 { "" } else { "s" })
    };
    let mut parts = Vec::new();
    if counts.running_tasks > 0 {
        parts.push(format!(
            "Quitting now stops {}.",
            plural(counts.running_tasks, "running background task")
        ));
    }
    if counts.queued_tasks > 0 {
        parts.push(format!(
            "{} will start the next time the app runs.",
            plural(counts.queued_tasks, "queued task")
        ));
    }
    Some(parts.join(" "))
}

fn wait_for_django(port: u16, auth_token: &str) -> Result<(), String> {
    let deadline = Instant::now() + Duration::from_millis(STARTUP_TIMEOUT_MS);

    while Instant::now() < deadline {
        if health_status(port, auth_token) == Some(200) {
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

fn packaged_database_path(
    app: &AppHandle,
    runtime_mode: RuntimeMode,
) -> Result<Option<PathBuf>, String> {
    if runtime_mode != RuntimeMode::Packaged {
        return Ok(None);
    }

    // Mirrors desktop_django_starter.app_state: packaged settings keep the
    // database under <app-data>/state/<version>/.
    Ok(Some(
        resolve_app_data_dir(app)?
            .join(STATE_DIRNAME)
            .join(state_dir_name(&app_version(app)))
            .join("app.sqlite3"),
    ))
}

fn app_version(app: &AppHandle) -> String {
    app.package_info().version.to_string()
}

/// Port of `desktop_django_starter.app_state.state_dir_name`; both must agree.
fn state_dir_name(version: &str) -> String {
    let cleaned: String = version
        .trim()
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || matches!(character, '.' | '+' | '_' | '-') {
                character
            } else {
                '_'
            }
        })
        .collect();
    let cleaned = cleaned.trim_matches('.');
    if cleaned.is_empty() {
        UNVERSIONED_STATE_DIRNAME.to_string()
    } else {
        cleaned.to_string()
    }
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

/// Creates a command for a console program without a visible console window.
///
/// python.exe and taskkill.exe are console programs; from a GUI-subsystem
/// parent on Windows each would otherwise open its own console window.
fn background_command(program: impl AsRef<std::ffi::OsStr>) -> Command {
    #[allow(unused_mut)]
    let mut command = Command::new(program);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    command
}

fn base_command(runtime_mode: RuntimeMode, backend_root: &Path) -> Result<Command, String> {
    if let Ok(path) = env::var("DESKTOP_DJANGO_PYTHON") {
        return Ok(background_command(path));
    }

    if runtime_mode == RuntimeMode::Packaged {
        return Ok(background_command(resolve_bundled_python_executable(
            backend_root,
        )?));
    }

    let mut command = background_command(if cfg!(target_os = "windows") {
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
    auth_token: &str,
    manage_args: &[&str],
) -> Result<Command, String> {
    let mut command = base_command(runtime_mode, backend_root)?;
    let app_data_dir = resolve_app_data_dir(app)?;
    let guard = resolve_process_guard(backend_root);
    let identity = app.state::<AppState>().guard_identity.lock().unwrap().clone();
    let settings_module = if runtime_mode == RuntimeMode::Packaged {
        "desktop_django_starter.settings.packaged"
    } else {
        "desktop_django_starter.settings.local"
    };

    command
        .current_dir(backend_root)
        .env("DJANGO_SETTINGS_MODULE", settings_module)
        .env("DESKTOP_DJANGO_APP_DATA_DIR", &app_data_dir)
        .env("DESKTOP_DJANGO_APP_VERSION", app_version(app))
        .env("DESKTOP_DJANGO_AUTH_TOKEN", auth_token)
        .env("DESKTOP_DJANGO_BUNDLE_DIR", backend_root)
        .env("DESKTOP_DJANGO_HOST", HOST)
        .env("DESKTOP_DJANGO_PORT", port.to_string())
        .env("PYTHONUNBUFFERED", "1")
        .args(manage_command_args(
            guard.as_deref(),
            identity.as_ref(),
            manage_args,
        ));

    Ok(command)
}

/// The guard is staged next to manage.py in packaged backends and lives under
/// scripts/ in the repo. Wrapped apps without it run manage.py directly.
fn resolve_process_guard(backend_root: &Path) -> Option<PathBuf> {
    [
        backend_root.join(PROCESS_GUARD_FILENAME),
        backend_root.join("scripts").join(PROCESS_GUARD_FILENAME),
    ]
    .into_iter()
    .find(|candidate| candidate.is_file())
}

fn manage_command_args(
    guard: Option<&Path>,
    identity: Option<&GuardIdentity>,
    manage_args: &[&str],
) -> Vec<OsString> {
    let mut args = Vec::new();
    if let (Some(guard), Some(identity)) = (guard, identity) {
        args.push(guard.as_os_str().to_os_string());
        for argument in [
            "--app-key",
            identity.app_key.as_str(),
            "--instance",
            identity.instance_id.as_str(),
            "--watch-stdin",
            "--",
        ] {
            args.push(argument.into());
        }
    }
    args.push("manage.py".into());
    args.extend(manage_args.iter().map(OsString::from));
    args
}

fn run_manage_command(
    app: &AppHandle,
    runtime_mode: RuntimeMode,
    backend_root: &Path,
    port: u16,
    auth_token: &str,
    manage_args: &[&str],
) -> Result<(), String> {
    let mut child = configure_manage_command(
        app,
        runtime_mode,
        backend_root,
        port,
        auth_token,
        manage_args,
    )?
    .stdin(Stdio::piped())
    .stdout(Stdio::piped())
    .stderr(Stdio::piped())
    .spawn()
    .map_err(|error| error.to_string())?;

    // Held, not written, until the command finished: the guard exits when
    // this pipe closes, which happens early only if the shell dies.
    let stdin_guard: Option<ChildStdin> = child.stdin.take();
    let stdout_reader = child.stdout.take().map(read_pipe_in_background);
    let stderr_reader = child.stderr.take().map(read_pipe_in_background);
    let status = child.wait().map_err(|error| error.to_string())?;
    drop(stdin_guard);
    let _stdout = stdout_reader.and_then(|reader| reader.join().ok());
    let stderr = stderr_reader
        .and_then(|reader| reader.join().ok())
        .unwrap_or_default();

    if status.success() {
        return Ok(());
    }

    let stderr = String::from_utf8_lossy(&stderr).trim().to_string();
    Err(if stderr.is_empty() {
        format!("manage.py {} failed.", manage_args.join(" "))
    } else {
        stderr
    })
}

fn read_pipe_in_background(
    mut pipe: impl Read + Send + 'static,
) -> thread::JoinHandle<Vec<u8>> {
    thread::spawn(move || {
        let mut buffer = Vec::new();
        let _ = pipe.read_to_end(&mut buffer);
        buffer
    })
}

fn start_managed_process(
    app: &AppHandle,
    runtime_mode: RuntimeMode,
    backend_root: &Path,
    port: u16,
    auth_token: &str,
    manage_args: &[&str],
) -> Result<Child, String> {
    configure_manage_command(
        app,
        runtime_mode,
        backend_root,
        port,
        auth_token,
        manage_args,
    )?
    // The ChildStdin stays inside the Child, which the ManagedChild keeps
    // until the process is stopped, so the pipe closes only when the child is
    // stopped or this shell process ends (including a crash).
    .stdin(Stdio::piped())
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

fn prompt_to_install_update(app: &AppHandle, current_version: &str, next_version: &str) -> bool {
    let message = format!(
        "Version {next_version} is available.\n\nCurrent version: {current_version}\nThe app may close to apply the update."
    );

    app.dialog()
        .message(message)
        .title("Update Available")
        .kind(MessageDialogKind::Info)
        .buttons(MessageDialogButtons::OkCancelCustom(
            "Install".into(),
            "Later".into(),
        ))
        .blocking_show()
}

fn show_update_error(app: AppHandle, message: String) {
    thread::spawn(move || {
        app.dialog()
            .message(message)
            .title("Update Failed")
            .kind(MessageDialogKind::Error)
            .blocking_show();
    });
}

fn start_update_check(app: AppHandle) {
    if get_runtime_mode() != RuntimeMode::Packaged || is_smoke_test() {
        return;
    }

    if app
        .state::<AppState>()
        .update_check_started
        .swap(true, Ordering::SeqCst)
    {
        return;
    }

    tauri::async_runtime::spawn(async move {
        let Some(config) = (match resolve_updater_config() {
            Ok(config) => config,
            Err(error) => {
                eprintln!("Tauri updater disabled: {error}");
                return;
            }
        }) else {
            return;
        };

        let updater_builder = match app
            .updater_builder()
            .pubkey(config.pubkey)
            .endpoints(config.endpoints)
        {
            Ok(builder) => builder,
            Err(error) => {
                eprintln!("Tauri updater disabled: {error}");
                return;
            }
        };

        let updater = match updater_builder.build() {
            Ok(updater) => updater,
            Err(error) => {
                eprintln!("Tauri updater disabled: {error}");
                return;
            }
        };

        let Some(update) = (match updater.check().await {
            Ok(update) => update,
            Err(error) => {
                eprintln!("Tauri updater check failed: {error}");
                return;
            }
        }) else {
            return;
        };

        if !prompt_to_install_update(&app, &update.current_version, &update.version) {
            return;
        }

        let app_for_exit = app.clone();
        if let Err(error) = update
            .download_and_install(
                |_, _| {},
                move || {
                    // The installer may end this process; no quit prompt.
                    app_for_exit
                        .state::<AppState>()
                        .exit_confirmed
                        .store(true, Ordering::SeqCst);
                    stop_managed_processes(&app_for_exit);
                },
            )
            .await
        {
            show_update_error(
                app.clone(),
                format!("Tauri could not download or install the update.\n\n{error}"),
            );
        }
    });
}

fn create_splash_window(app: &AppHandle) -> Result<WebviewWindow, String> {
    if let Some(window) = app.get_webview_window(SPLASH_WINDOW_LABEL) {
        return Ok(window);
    }

    WebviewWindowBuilder::new(
        app,
        SPLASH_WINDOW_LABEL,
        WebviewUrl::App("splash.html".into()),
    )
    .title("Flying Stable")
    .inner_size(480.0, 560.0)
    .resizable(false)
    .maximizable(false)
    .minimizable(false)
    .closable(false)
    .decorations(false)
    .center()
    .build()
    .map_err(|error| error.to_string())
}

fn close_splash_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window(SPLASH_WINDOW_LABEL) {
        let _ = window.close();
    }
}

fn create_main_window(app: &AppHandle, url: &str) -> Result<WebviewWindow, String> {
    let external_url = Url::parse(url).map_err(|error| error.to_string())?;
    let smoke_test = is_smoke_test();
    let first_page_load = Arc::new(AtomicBool::new(false));
    let first_page_load_for_handler = first_page_load.clone();

    WebviewWindowBuilder::new(app, "main", WebviewUrl::External(external_url))
        .title("Desktop Django Starter")
        .inner_size(1200.0, 840.0)
        .visible(false)
        .initialization_script(inject_desktop_bridge())
        .on_page_load(move |window, payload| {
            if matches!(payload.event(), PageLoadEvent::Finished)
                && !first_page_load_for_handler.swap(true, Ordering::SeqCst)
            {
                let handle = window.app_handle().clone();
                close_splash_window(&handle);
                let _ = window.show();
                let _ = window.set_focus();
                start_update_check(handle.clone());

                if smoke_test {
                    thread::spawn(move || {
                        thread::sleep(Duration::from_millis(750));
                        mark_quitting(&handle);
                        handle.exit(0);
                    });
                }
            }
        })
        .build()
        .map_err(|error| error.to_string())
}

fn random_hex(byte_count: usize) -> Result<String, String> {
    let mut bytes = vec![0_u8; byte_count];
    getrandom::fill(&mut bytes).map_err(|error| error.to_string())?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn generate_desktop_auth_token() -> Result<String, String> {
    random_hex(32)
}

fn is_valid_app_key(app_key: &str) -> bool {
    app_key.len() == 32 && app_key.chars().all(|character| character.is_ascii_hexdigit())
}

fn parse_shell_session(raw: &str) -> Option<ShellSession> {
    serde_json::from_str::<ShellSession>(raw)
        .ok()
        .filter(|session| is_valid_app_key(&session.app_key))
}

fn write_shell_session(path: &Path, session: &ShellSession) -> Result<(), String> {
    let serialized = serde_json::to_string_pretty(session).map_err(|error| error.to_string())?;
    let temporary = path.with_extension("json.tmp");
    fs::write(&temporary, format!("{serialized}\n")).map_err(|error| error.to_string())?;
    fs::rename(&temporary, path).map_err(|error| error.to_string())
}

/// Reads or creates the session file, stops leftovers of a previous run that
/// did not shut down cleanly, and records this run as running.
fn prepare_shell_session(app: &AppHandle) -> Result<(), String> {
    let session_path = resolve_app_data_dir(app)?.join(SHELL_SESSION_FILENAME);
    let previous = fs::read_to_string(&session_path)
        .ok()
        .and_then(|raw| parse_shell_session(&raw));
    let app_key = match &previous {
        Some(session) => session.app_key.clone(),
        None => random_hex(16)?,
    };

    if previous.as_ref().is_some_and(|session| session.running) {
        stop_orphaned_processes(&app_key);
    }

    write_shell_session(
        &session_path,
        &ShellSession {
            app_key: app_key.clone(),
            running: true,
            shell_pid: std::process::id(),
        },
    )?;

    let state = app.state::<AppState>();
    *state.guard_identity.lock().unwrap() = Some(GuardIdentity {
        app_key,
        instance_id: random_hex(8)?,
    });
    *state.session_path.lock().unwrap() = Some(session_path);
    Ok(())
}

fn record_clean_shutdown(app: &AppHandle) {
    let state = app.state::<AppState>();
    let Some(session_path) = state.session_path.lock().unwrap().take() else {
        return;
    };
    let Some(identity) = state.guard_identity.lock().unwrap().clone() else {
        return;
    };
    if let Err(error) = write_shell_session(
        &session_path,
        &ShellSession {
            app_key: identity.app_key,
            running: false,
            shell_pid: std::process::id(),
        },
    ) {
        eprintln!("Could not record the clean shutdown in {}: {error}", session_path.display());
    }
}

/// Parses `<pid> <command line>` lines (POSIX `ps -o pid=,command=` output and
/// the PowerShell listing below use the same shape).
fn parse_process_list(output: &str) -> Vec<(u32, String)> {
    output
        .lines()
        .filter_map(|line| {
            let (pid, command) = line.trim().split_once(char::is_whitespace)?;
            Some((pid.parse().ok()?, command.trim().to_string()))
        })
        .collect()
}

/// True for `... desktop_process_guard.py --app-key <app_key> ...`. Requiring
/// the guard script right before the key keeps, for example, a shell whose
/// command line merely mentions the key from matching.
fn command_line_has_app_key(command_line: &str, app_key: &str) -> bool {
    let tokens = command_line
        .split_whitespace()
        .map(|token| token.trim_matches('"'))
        .collect::<Vec<_>>();
    tokens.windows(3).any(|triple| {
        triple[0].ends_with(PROCESS_GUARD_FILENAME)
            && triple[1] == "--app-key"
            && triple[2] == app_key
    })
}

fn find_orphan_processes(
    processes: &[(u32, String)],
    app_key: &str,
    own_pid: u32,
) -> Vec<(u32, String)> {
    processes
        .iter()
        .filter(|(pid, command)| *pid != own_pid && command_line_has_app_key(command, app_key))
        .cloned()
        .collect()
}

#[cfg(not(windows))]
fn list_processes(_app_key: &str) -> Result<String, String> {
    let output = Command::new("ps")
        .args(["-axww", "-o", "pid=,command="])
        .output()
        .map_err(|error| error.to_string())?;
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

#[cfg(windows)]
fn list_processes(app_key: &str) -> Result<String, String> {
    // The pattern is split so this PowerShell command line does not itself
    // contain "--app-key <key>"; the Rust-side match is the authoritative one.
    let script = format!(
        "$pattern = '*--app-' + 'key {app_key}*'; \
         Get-CimInstance Win32_Process | \
         Where-Object {{ $_.CommandLine -like $pattern }} | \
         ForEach-Object {{ \"$($_.ProcessId) $($_.CommandLine)\" }}"
    );
    let output = background_command("powershell.exe")
        .args(["-NoProfile", "-NonInteractive", "-Command", &script])
        .output()
        .map_err(|error| error.to_string())?;
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

#[cfg(not(windows))]
fn terminate_processes(pids: &[u32]) {
    let pid_args = pids.iter().map(u32::to_string).collect::<Vec<_>>();
    let _ = Command::new("kill").arg("-TERM").args(&pid_args).status();

    let is_alive = |pid: &String| {
        Command::new("kill")
            .args(["-0", pid])
            .stderr(Stdio::null())
            .status()
            .map(|status| status.success())
            .unwrap_or(false)
    };
    let deadline = Instant::now() + Duration::from_millis(SHUTDOWN_GRACE_PERIOD_MS);
    let mut remaining = pid_args;
    while !remaining.is_empty() && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(POLL_INTERVAL_MS));
        remaining.retain(|pid| is_alive(pid));
    }
    if !remaining.is_empty() {
        let _ = Command::new("kill").arg("-KILL").args(&remaining).status();
    }
}

#[cfg(windows)]
fn terminate_processes(pids: &[u32]) {
    for pid in pids {
        let _ = background_command("taskkill")
            .args(["/pid", &pid.to_string(), "/t", "/f"])
            .status();
    }
}

/// Stops backend processes a crashed earlier run left behind. They carry this
/// install's app key on their command line (see `manage_command_args`).
fn stop_orphaned_processes(app_key: &str) {
    let listing = match list_processes(app_key) {
        Ok(listing) => listing,
        Err(error) => {
            eprintln!("Could not list processes to clean up a previous run: {error}");
            return;
        }
    };
    let orphans = find_orphan_processes(
        &parse_process_list(&listing),
        app_key,
        std::process::id(),
    );
    if orphans.is_empty() {
        eprintln!("The previous run did not shut down cleanly; no leftover backend processes found.");
        return;
    }
    for (pid, command) in &orphans {
        eprintln!("Stopping leftover backend process {pid} from a previous run: {command}");
    }
    let pids = orphans.iter().map(|(pid, _)| *pid).collect::<Vec<_>>();
    terminate_processes(&pids);
}

fn build_bootstrap_url(base_url: &str, auth_token: &str) -> Result<String, String> {
    let mut url = Url::parse(base_url).map_err(|error| error.to_string())?;
    url.set_path(DESKTOP_AUTH_BOOTSTRAP_PATH);
    url.query_pairs_mut()
        .append_pair("token", auth_token)
        .append_pair("next", "/");
    Ok(url.to_string())
}

fn open_path(path: &Path) -> Result<(), String> {
    let status = if cfg!(target_os = "macos") {
        Command::new("open")
            .arg(path)
            .status()
            .map_err(|error| error.to_string())?
    } else if cfg!(target_os = "windows") {
        // explorer.exe exits with status 1 even when it opened the folder, so
        // only a failure to launch it counts as an error.
        Command::new("explorer")
            .arg(path)
            .status()
            .map_err(|error| error.to_string())?;
        return Ok(());
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

fn wait_for_minimum_splash_duration(shown_at: Instant) {
    let elapsed = shown_at.elapsed();
    let minimum = Duration::from_millis(MINIMUM_SPLASH_DURATION_MS);
    if elapsed < minimum {
        thread::sleep(minimum - elapsed);
    }
}

fn bootstrap(app: &AppHandle, splash_shown_at: Instant) -> Result<(), String> {
    // The single-instance plugin has already let this launch through, so any
    // matching backend process belongs to an earlier, crashed run.
    prepare_shell_session(app)?;
    let runtime_mode = get_runtime_mode();
    let backend_root = get_backend_root(app, runtime_mode)?;
    let port = get_open_port()?;
    let base_url = format!("http://{HOST}:{port}");
    let auth_token = generate_desktop_auth_token()?;
    let bootstrap_url = build_bootstrap_url(&base_url, &auth_token)?;
    *app.state::<AppState>().django_origin.lock().unwrap() = Some(base_url.clone());
    let should_seed_demo_content = match packaged_database_path(app, runtime_mode)? {
        Some(database_path) => !database_path.exists(),
        None => false,
    };

    if runtime_mode == RuntimeMode::Packaged {
        validate_packaged_backend_root(&backend_root)?;
    }

    run_manage_command(
        app,
        runtime_mode,
        &backend_root,
        port,
        &auth_token,
        &["migrate", "--noinput"],
    )?;

    if should_seed_demo_content {
        run_manage_command(
            app,
            runtime_mode,
            &backend_root,
            port,
            &auth_token,
            &["seed_demo_content"],
        )?;
    }

    let django = start_managed_process(
        app,
        runtime_mode,
        &backend_root,
        port,
        &auth_token,
        &["runserver", &format!("{HOST}:{port}"), "--noreload"],
    )?;
    register_managed_process(
        app,
        "django",
        "Django exited",
        "The Django process stopped before the desktop app finished.",
        django,
    );

    if let Err(error) = wait_for_django(port, &auth_token) {
        stop_managed_processes(app);
        return Err(error);
    }

    let worker = start_managed_process(
        app,
        runtime_mode,
        &backend_root,
        port,
        &auth_token,
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
    *app.state::<AppState>().activity_endpoint.lock().unwrap() = Some((port, auth_token.clone()));

    wait_for_minimum_splash_duration(splash_shown_at);
    let app_handle = app.clone();
    app.run_on_main_thread(move || {
        if is_quitting(&app_handle) {
            return;
        }

        if let Err(error) = create_main_window(&app_handle, &bootstrap_url) {
            show_runtime_error_and_exit(app_handle.clone(), "Startup failed", error, 1);
        }
    })
    .map_err(|error| error.to_string())?;

    Ok(())
}

fn stop_child(child: ManagedChild) {
    let mut child = child.lock().unwrap();
    let Some(process) = child.as_mut() else {
        return;
    };

    if cfg!(target_os = "windows") {
        let _ = background_command("taskkill")
            .args(["/pid", &process.id().to_string(), "/t", "/f"])
            .status();
    } else {
        let _ = Command::new("kill")
            .args(["-TERM", &process.id().to_string()])
            .status();

        let deadline = Instant::now() + Duration::from_millis(SHUTDOWN_GRACE_PERIOD_MS);
        while Instant::now() < deadline {
            match process.try_wait() {
                Ok(Some(_status)) => {
                    *child = None;
                    return;
                }
                Ok(None) => thread::sleep(Duration::from_millis(POLL_INTERVAL_MS)),
                Err(_) => break,
            }
        }

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
    drop(state);

    record_clean_shutdown(app);
}

fn exit_needs_confirmation(app: &AppHandle) -> bool {
    let state = app.state::<AppState>();
    !state.exit_confirmed.load(Ordering::SeqCst)
        && !is_quitting(app)
        && !is_smoke_test()
        && state.activity_endpoint.lock().unwrap().is_some()
}

/// Asks before quitting while background tasks are running or queued. The
/// caller has already prevented the close or exit. Idle, a failed activity
/// request, or "Quit" all continue with the normal exit; only "Cancel" keeps
/// the app open.
fn begin_exit_check(app: AppHandle) {
    let state = app.state::<AppState>();
    if state.exit_check_in_progress.swap(true, Ordering::SeqCst) {
        return;
    }
    let endpoint = state.activity_endpoint.lock().unwrap().clone();

    thread::spawn(move || {
        let counts = endpoint.and_then(|(port, auth_token)| fetch_activity(port, &auth_token));
        if counts.is_none() {
            eprintln!("Could not read background task activity; quitting without asking.");
        }

        if let Some(message) = counts.and_then(exit_confirmation_message) {
            let quit = app
                .dialog()
                .message(message)
                .title("A background task is still running")
                .kind(MessageDialogKind::Warning)
                .buttons(MessageDialogButtons::OkCancelCustom(
                    "Quit".into(),
                    "Cancel".into(),
                ))
                .blocking_show();
            if !quit {
                app.state::<AppState>()
                    .exit_check_in_progress
                    .store(false, Ordering::SeqCst);
                return;
            }
        }

        app.state::<AppState>()
            .exit_confirmed
            .store(true, Ordering::SeqCst);
        app.exit(0);
    });
}

/// macOS' default Quit item calls `terminate:`, which Tauri reports only as
/// the unpreventable `RunEvent::Exit`. Replacing it with a custom item routes
/// Cmd+Q through `app.exit(0)` and the preventable `ExitRequested`.
#[cfg(target_os = "macos")]
fn build_app_menu(app: &AppHandle) -> tauri::Result<tauri::menu::Menu<tauri::Wry>> {
    use tauri::menu::{Menu, MenuItem, MenuItemKind};

    let menu = Menu::default(app)?;
    if let Some(MenuItemKind::Submenu(app_menu)) = menu.items()?.into_iter().next() {
        let item_count = app_menu.items()?.len();
        if item_count > 0 {
            // The default app menu ends with the predefined Quit item.
            app_menu.remove_at(item_count - 1)?;
        }
        app_menu.append(&MenuItem::with_id(
            app,
            QUIT_MENU_ID,
            format!("Quit {}", app.package_info().name),
            true,
            Some("CmdOrCtrl+Q"),
        )?)?;
    }
    Ok(menu)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default();
    #[cfg(target_os = "macos")]
    let builder = builder
        .menu(build_app_menu)
        .on_menu_event(|app, event| {
            if event.id() == QUIT_MENU_ID {
                app.exit(0);
            }
        });

    let app = builder
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            focus_existing_window(app);
        }))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![open_app_data_directory])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle();
                if window.label() == "main" && exit_needs_confirmation(app) {
                    api.prevent_close();
                    begin_exit_check(app.clone());
                }
            }
        })
        .setup(|app| {
            let app_handle = app.handle().clone();

            if let Err(error) = create_splash_window(&app_handle) {
                show_runtime_error_and_exit(app_handle, "Startup failed", error, 1);
                return Ok(());
            }
            let splash_shown_at = Instant::now();

            thread::spawn(move || {
                if let Err(error) = bootstrap(&app_handle, splash_shown_at) {
                    show_runtime_error_and_exit(app_handle.clone(), "Startup failed", error, 1);
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app, event| match event {
        tauri::RunEvent::ExitRequested { api, .. } => {
            if exit_needs_confirmation(app) {
                api.prevent_exit();
                begin_exit_check(app.clone());
            } else {
                stop_managed_processes(app);
            }
        }
        tauri::RunEvent::Exit => stop_managed_processes(app),
        _ => {}
    });
}

#[cfg(test)]
mod tests {
    use super::{
        command_line_has_app_key, exit_confirmation_message, find_orphan_processes,
        is_trusted_bridge_caller, manage_command_args, parse_activity_response,
        parse_process_list, parse_shell_session, parse_updater_endpoints, state_dir_name,
        ActivityCounts, GuardIdentity, ShellSession,
    };
    use std::ffi::OsString;
    use std::path::Path;
    use url::Url;

    const KEY: &str = "0123456789abcdef0123456789abcdef";

    #[test]
    fn state_dir_name_matches_the_python_sanitizer() {
        assert_eq!(state_dir_name("0.1.0"), "0.1.0");
        assert_eq!(state_dir_name(" 1.2.3+build_4-rc "), "1.2.3+build_4-rc");
        assert_eq!(state_dir_name("1.0/../evil"), "1.0_.._evil");
        assert_eq!(state_dir_name("..1.0.."), "1.0");
        assert_eq!(state_dir_name("v 2"), "v_2");
        assert_eq!(state_dir_name("ä1"), "_1");
        assert_eq!(state_dir_name("..."), "unversioned");
        assert_eq!(state_dir_name("   "), "unversioned");
    }

    #[test]
    fn manage_commands_run_through_the_guard_when_present() {
        let identity = GuardIdentity {
            app_key: KEY.to_string(),
            instance_id: "run1".to_string(),
        };
        let guarded = manage_command_args(
            Some(Path::new("/backend/desktop_process_guard.py")),
            Some(&identity),
            &["migrate", "--noinput"],
        );
        let expected: Vec<OsString> = [
            "/backend/desktop_process_guard.py",
            "--app-key",
            KEY,
            "--instance",
            "run1",
            "--watch-stdin",
            "--",
            "manage.py",
            "migrate",
            "--noinput",
        ]
        .into_iter()
        .map(OsString::from)
        .collect();
        assert_eq!(guarded, expected);

        let direct = manage_command_args(None, Some(&identity), &["migrate"]);
        assert_eq!(direct, vec![OsString::from("manage.py"), OsString::from("migrate")]);
    }

    #[test]
    fn process_listing_parser_and_app_key_match() {
        let listing = format!(
            "  101 /usr/bin/python3 desktop_process_guard.py --app-key {KEY} --instance a --watch-stdin -- manage.py runserver\n\
             202 /usr/bin/python3 desktop_process_guard.py --app-key {KEY}ff --instance b -- manage.py db_worker\n\
             303 \"C:\\py\\python.exe\" \"C:\\app\\desktop_process_guard.py\" \"--app-key\" \"{KEY}\" -- manage.py db_worker\r\n\
             404 ps -axww -o pid=,command=\n\
             garbage line\n\
             505\n"
        );
        let processes = parse_process_list(&listing);
        assert_eq!(processes.len(), 4);
        assert_eq!(processes[0].0, 101);
        assert!(processes[0].1.starts_with("/usr/bin/python3"));

        assert!(command_line_has_app_key(&processes[0].1, KEY));
        assert!(!command_line_has_app_key(&processes[1].1, KEY));
        assert!(command_line_has_app_key(&processes[2].1, KEY));
        assert!(!command_line_has_app_key("echo --app-key", KEY));
        assert!(!command_line_has_app_key(
            &format!("/bin/zsh -c 'echo --app-key {KEY}'"),
            KEY
        ));

        let orphans = find_orphan_processes(&processes, KEY, 303);
        assert_eq!(orphans.iter().map(|(pid, _)| *pid).collect::<Vec<_>>(), vec![101]);
    }

    #[test]
    fn shell_session_requires_a_valid_app_key() {
        let raw = format!(r#"{{"app_key": "{KEY}", "running": true, "shell_pid": 42}}"#);
        assert_eq!(
            parse_shell_session(&raw),
            Some(ShellSession {
                app_key: KEY.to_string(),
                running: true,
                shell_pid: 42
            })
        );
        assert_eq!(
            parse_shell_session(r#"{"app_key": "short", "running": true, "shell_pid": 1}"#),
            None
        );
        assert_eq!(parse_shell_session("not json"), None);
    }

    #[test]
    fn activity_response_and_exit_message() {
        let response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"running_tasks\": 1, \"queued_tasks\": 2}";
        let counts = parse_activity_response(response).expect("expected counts");
        assert_eq!(
            counts,
            ActivityCounts {
                running_tasks: 1,
                queued_tasks: 2
            }
        );
        assert_eq!(
            exit_confirmation_message(counts).as_deref(),
            Some(
                "Quitting now stops 1 running background task. \
                 2 queued tasks will start the next time the app runs."
            )
        );
        assert_eq!(
            exit_confirmation_message(ActivityCounts {
                running_tasks: 0,
                queued_tasks: 0
            }),
            None
        );
        assert_eq!(
            parse_activity_response("HTTP/1.1 403 Forbidden\r\n\r\n{}"),
            None
        );
    }

    #[test]
    fn bridge_caller_must_match_the_exact_django_origin() {
        let expected = Some("http://127.0.0.1:51234");
        let same = Url::parse("http://127.0.0.1:51234/items/?page=2").unwrap();
        let other_port = Url::parse("http://127.0.0.1:8000/").unwrap();
        let other_host = Url::parse("http://localhost:51234/").unwrap();

        assert!(is_trusted_bridge_caller(&same, expected));
        assert!(!is_trusted_bridge_caller(&other_port, expected));
        assert!(!is_trusted_bridge_caller(&other_host, expected));
        assert!(!is_trusted_bridge_caller(&same, None));
    }

    #[test]
    fn updater_endpoint_parser_accepts_commas_and_newlines() {
        let endpoints = parse_updater_endpoints(
            "https://updates.example.test/latest.json,\nhttps://updates.example.test/fallback.json",
        )
        .expect("expected valid updater endpoints");

        assert_eq!(endpoints.len(), 2);
        assert_eq!(
            endpoints[0].as_str(),
            "https://updates.example.test/latest.json"
        );
        assert_eq!(
            endpoints[1].as_str(),
            "https://updates.example.test/fallback.json"
        );
    }

    #[test]
    fn updater_endpoint_parser_rejects_invalid_urls() {
        let error = parse_updater_endpoints("not-a-url").expect_err("expected invalid URL");
        assert!(error.contains("relative URL without a base"));
    }
}
