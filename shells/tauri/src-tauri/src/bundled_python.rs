//! Admission for the shared schema-v1 runtime manifest; keep aligned with scripts/bundled-python.cjs.
use serde_json::Value;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

const MAX_MANIFEST_BYTES: u64 = 65536;

fn relative(root: &Path, value: &Value) -> Result<PathBuf, String> {
    let value = value.as_str().ok_or("Expected a relative path string")?;
    if value.split('/').any(|part| {
        part.is_empty()
            || part == "."
            || part == ".."
            || part.ends_with(['.', ' '])
            || part
                .chars()
                .any(|c| c.is_control() || "<>:\\|?*\"".contains(c))
    }) {
        return Err("Expected a portable relative path".into());
    }
    Ok(root.join(value))
}

fn validate(manifest: &Value, root: &Path) -> Result<PathBuf, String> {
    if !manifest.is_object()
        || manifest["schemaVersion"].as_f64() != Some(1.0)
        || !manifest["python"].is_object()
        || !manifest["launcher"].is_object()
    {
        return Err("Unsupported schema or missing objects".into());
    }
    let python = &manifest["python"];
    if python["root"] != "python"
        || python["version"]
            .as_str()
            .is_none_or(|s| s.trim().is_empty())
    {
        return Err("Expected Python version and python runtime root".into());
    }
    let runtime = root.join("python");
    for key in ["executable", "purelib", "scripts"] {
        let target = relative(root, &python[key])?;
        if target == runtime || !target.starts_with(&runtime) {
            return Err(format!("Python {key} must be inside python/"));
        }
    }
    let launcher = &manifest["launcher"];
    if launcher["cwd"] != "."
        || launcher["settingsModule"]
            .as_str()
            .is_none_or(str::is_empty)
        || !launcher["environment"]
            .as_array()
            .is_some_and(|a| a.iter().all(Value::is_string))
    {
        return Err("Invalid launcher fields".into());
    }
    for key in ["managePy", "sourceRoot"] {
        relative(root, &launcher[key])?;
    }
    relative(root, &python["executable"])
}

fn usable(root: &Path, executable: PathBuf) -> Result<PathBuf, String> {
    let backend = root.canonicalize().map_err(|e| e.to_string())?;
    let runtime = root
        .join("python")
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let real = executable.canonicalize().map_err(|e| e.to_string())?;
    let metadata = fs::metadata(&executable).map_err(|e| e.to_string())?;
    if runtime != backend.join("python")
        || real == runtime
        || !real.starts_with(runtime)
        || !metadata.is_file()
    {
        return Err("Interpreter must be a regular file contained in the bundled runtime".into());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if metadata.permissions().mode() & 0o111 == 0 {
            return Err("Interpreter is not executable".into());
        }
    }
    Ok(executable)
}

pub(super) fn resolve_bundled_python_executable(root: &Path) -> Result<PathBuf, String> {
    let manifest_path = root.join("runtime-manifest.json");
    let metadata = match fs::symlink_metadata(&manifest_path) {
        Ok(metadata) => Some(metadata),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
        Err(error) => return Err(format!("Invalid runtime manifest: {error}")),
    };
    if let Some(metadata) = metadata {
        let read = || -> Result<PathBuf, String> {
            if !metadata.is_file() || metadata.len() > MAX_MANIFEST_BYTES {
                return Err("Expected a regular file of at most 65536 bytes".into());
            }
            let file = fs::File::open(&manifest_path).map_err(|e| e.to_string())?;
            let opened = file.metadata().map_err(|e| e.to_string())?;
            if !opened.is_file() || opened.len() > MAX_MANIFEST_BYTES {
                return Err("Expected a bounded regular file".into());
            }
            let mut bytes = Vec::new();
            file.take(MAX_MANIFEST_BYTES + 1)
                .read_to_end(&mut bytes)
                .map_err(|e| e.to_string())?;
            if bytes.len() as u64 > MAX_MANIFEST_BYTES {
                return Err("Manifest exceeds 65536 bytes".into());
            }
            let manifest: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
            usable(root, validate(&manifest, root)?)
        };
        return read()
            .map_err(|e| format!("Invalid runtime manifest {}: {e}", manifest_path.display()));
    }
    let paths: &[&str] = if cfg!(windows) {
        &["python/python.exe", "python/Scripts/python.exe"]
    } else {
        &["python/bin/python3", "python/bin/python"]
    };
    paths
        .iter()
        .find_map(|path| usable(root, root.join(path)).ok())
        .ok_or_else(|| {
            format!(
                "No bundled Python runtime found under {}",
                root.join("python").display()
            )
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn manifest() -> Value {
        json!({"schemaVersion":1, "python":{"root":"python", "version":"3.14.3",
            "executable":"python/bin/python3", "purelib":"python/lib/site-packages", "scripts":"python/bin"},
            "launcher":{"cwd":".", "managePy":"manage.py", "sourceRoot":"src",
                "settingsModule":"desktop_django_starter.settings.packaged", "environment":[]}})
    }

    #[test]
    fn schema_and_portable_paths_match_shared_contract() {
        let root = Path::new("backend");
        assert!(validate(&manifest(), root).is_ok());
        for value in [
            Value::Null,
            json!([]),
            json!({}),
            json!({"schemaVersion":2}),
        ] {
            assert!(validate(&value, root).is_err());
        }
        for value in [
            "../outside",
            "/bin/python",
            "C:/python.exe",
            "python/../outside",
            "python\\bin\\python",
            "python//bin/python",
            "python/bin/python:stream",
        ] {
            let mut value_manifest = manifest();
            value_manifest["python"]["executable"] = json!(value);
            assert!(validate(&value_manifest, root).is_err(), "{value}");
        }
    }

    #[test]
    fn existing_invalid_manifest_never_uses_legacy_discovery() {
        let root = std::env::temp_dir().join(format!("dds-manifest-{}", std::process::id()));
        fs::create_dir_all(root.join("python/bin")).unwrap();
        fs::write(root.join("python/bin/python3"), b"legacy").unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(
                root.join("python/bin/python3"),
                fs::Permissions::from_mode(0o755),
            )
            .unwrap();
        }
        #[cfg(not(windows))]
        assert!(resolve_bundled_python_executable(&root).is_ok());
        for value in [
            "null".to_string(),
            "[]".into(),
            " ".repeat(65537),
            manifest()
                .to_string()
                .replace("python/bin/python3", "../outside"),
        ] {
            fs::write(root.join("runtime-manifest.json"), value).unwrap();
            assert!(resolve_bundled_python_executable(&root)
                .unwrap_err()
                .contains("Invalid runtime manifest"));
        }
        fs::remove_file(root.join("runtime-manifest.json")).unwrap();
        fs::create_dir(root.join("runtime-manifest.json")).unwrap();
        assert!(resolve_bundled_python_executable(&root).is_err());
        fs::remove_dir_all(root).unwrap();
    }
    #[cfg(unix)]
    #[test]
    fn relocated_runtime_checks_real_interpreter_containment_and_type() {
        use std::os::unix::fs::{symlink, PermissionsExt};
        let fixture = std::env::temp_dir().join(format!("dds-contained-{}", std::process::id()));
        let source = fixture.join("source");
        let moved = fixture.join("moved");
        fs::create_dir_all(source.join("python/bin")).unwrap();
        fs::write(
            source.join("python/bin/python3.14"),
            b"#!/bin/sh\nprintf relocated",
        )
        .unwrap();
        fs::set_permissions(
            source.join("python/bin/python3.14"),
            fs::Permissions::from_mode(0o755),
        )
        .unwrap();
        symlink("python3.14", source.join("python/bin/python3")).unwrap();
        fs::write(source.join("runtime-manifest.json"), manifest().to_string()).unwrap();
        fs::rename(source, &moved).unwrap();
        let executable = resolve_bundled_python_executable(&moved).unwrap();
        assert_eq!(
            std::process::Command::new(&executable)
                .output()
                .unwrap()
                .stdout,
            b"relocated"
        );
        fs::remove_file(&executable).unwrap();
        fs::write(moved.join("outside"), b"outside").unwrap();
        symlink(moved.join("outside"), &executable).unwrap();
        assert!(resolve_bundled_python_executable(&moved).is_err());
        fs::remove_file(&executable).unwrap();
        fs::create_dir(&executable).unwrap();
        assert!(resolve_bundled_python_executable(&moved).is_err());
        fs::remove_dir(&executable).unwrap();
        fs::write(&executable, b"not executable").unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(resolve_bundled_python_executable(&moved).is_err());
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o755)).unwrap();
        fs::rename(moved.join("python"), moved.join("external")).unwrap();
        symlink("external", moved.join("python")).unwrap();
        assert!(resolve_bundled_python_executable(&moved).is_err());
        fs::remove_dir_all(fixture).unwrap();
    }
}
