//! Admission for the shared schema-v1 runtime manifest; keep aligned with scripts/bundled-python.cjs.
use serde_json::Value;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

const MAX_MANIFEST_BYTES: u64 = 65536;

// Deserialize through public Serde visitors so duplicate members are refused at
// every depth, including unknown extension objects and objects inside arrays.
struct ManifestValue(Value);
impl<'de> serde::Deserialize<'de> for ManifestValue {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct Visitor;
        impl<'de> serde::de::Visitor<'de> for Visitor {
            type Value = ManifestValue;
            fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                f.write_str("unambiguous runtime manifest JSON")
            }
            fn visit_unit<E: serde::de::Error>(self) -> Result<Self::Value, E> {
                Ok(ManifestValue(Value::Null))
            }
            fn visit_bool<E: serde::de::Error>(self, v: bool) -> Result<Self::Value, E> {
                Ok(ManifestValue(v.into()))
            }
            fn visit_i64<E: serde::de::Error>(self, v: i64) -> Result<Self::Value, E> {
                Ok(ManifestValue(v.into()))
            }
            fn visit_u64<E: serde::de::Error>(self, v: u64) -> Result<Self::Value, E> {
                Ok(ManifestValue(v.into()))
            }
            fn visit_f64<E: serde::de::Error>(self, v: f64) -> Result<Self::Value, E> {
                serde_json::Number::from_f64(v)
                    .map(|n| ManifestValue(Value::Number(n)))
                    .ok_or_else(|| E::custom("Invalid JSON number"))
            }
            fn visit_str<E: serde::de::Error>(self, v: &str) -> Result<Self::Value, E> {
                Ok(ManifestValue(v.into()))
            }
            fn visit_seq<A: serde::de::SeqAccess<'de>>(
                self,
                mut seq: A,
            ) -> Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(ManifestValue(value)) = seq.next_element()? {
                    values.push(value);
                }
                Ok(ManifestValue(Value::Array(values)))
            }
            fn visit_map<A: serde::de::MapAccess<'de>>(
                self,
                mut map: A,
            ) -> Result<Self::Value, A::Error> {
                let mut values = serde_json::Map::new();
                while let Some(key) = map.next_key::<String>()? {
                    if values.contains_key(&key) {
                        return Err(serde::de::Error::custom(
                            "Duplicate runtime manifest member",
                        ));
                    }
                    let ManifestValue(value) = map.next_value()?;
                    values.insert(key, value);
                }
                Ok(ManifestValue(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(Visitor)
    }
}

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

fn same_manifest_generation(before: &fs::Metadata, after: &fs::Metadata) -> bool {
    if !after.is_file() || before.len() != after.len() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        before.dev() == after.dev()
            && before.ino() == after.ino()
            && before.mtime() == after.mtime()
            && before.mtime_nsec() == after.mtime_nsec()
            && before.ctime() == after.ctime()
            && before.ctime_nsec() == after.ctime_nsec()
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
        (before.file_attributes() | after.file_attributes()) & FILE_ATTRIBUTE_REPARSE_POINT == 0
            && before.creation_time() == after.creation_time()
            && before.last_write_time() == after.last_write_time()
    }
    #[cfg(not(any(unix, windows)))]
    false
}

fn open_manifest(path: &Path, expected: &fs::Metadata) -> Result<(fs::File, fs::Metadata), String> {
    let mut options = fs::OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        const FILE_FLAG_OPEN_REPARSE_POINT: u32 = 0x0020_0000;
        const FILE_SHARE_READ: u32 = 1;
        // Inspect the entry itself and exclude writers and renames during the read.
        options
            .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)
            .share_mode(FILE_SHARE_READ);
    }
    #[cfg(not(any(unix, windows)))]
    return Err("Unsupported manifest descriptor policy".into());
    let file = options.open(path).map_err(|e| e.to_string())?;
    let opened = file.metadata().map_err(|e| e.to_string())?;
    if !same_manifest_generation(expected, &opened) {
        return Err("Runtime manifest changed or is not a direct regular file".into());
    }
    Ok((file, opened))
}

pub(super) fn resolve_bundled_python_executable(root: &Path) -> Result<PathBuf, String> {
    resolve_with_manifest_reader(root, |reader| {
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes)?;
        Ok(bytes)
    })
}

fn resolve_with_manifest_reader(
    root: &Path,
    read_bytes: impl FnOnce(&mut dyn Read) -> std::io::Result<Vec<u8>>,
) -> Result<PathBuf, String> {
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
            let (mut file, opened) = open_manifest(&manifest_path, &metadata)?;
            let bytes =
                read_bytes(&mut file.by_ref().take(opened.len() + 1)).map_err(|e| e.to_string())?;
            let finished = file.metadata().map_err(|e| e.to_string())?;
            let named = fs::symlink_metadata(&manifest_path).map_err(|e| e.to_string())?;
            if bytes.len() as u64 != opened.len()
                || !same_manifest_generation(&opened, &finished)
                || !same_manifest_generation(&opened, &named)
            {
                return Err("Runtime manifest changed during reading".into());
            }
            let ManifestValue(manifest) =
                serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
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

    #[cfg(unix)]
    #[test]
    fn replaced_manifest_symlink_is_refused_at_open() {
        use std::os::unix::fs::symlink;
        let root = std::env::temp_dir().join(format!("dds-open-symlink-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("runtime-manifest.json");
        fs::write(&path, manifest().to_string()).unwrap();
        let before = fs::symlink_metadata(&path).unwrap();
        fs::rename(&path, root.join("foreign")).unwrap();
        symlink(root.join("foreign"), &path).unwrap();
        assert!(open_manifest(&path, &before).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn replaced_manifest_fifo_is_refused_without_blocking() {
        let root = std::env::temp_dir().join(format!("dds-open-fifo-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("runtime-manifest.json");
        fs::write(&path, manifest().to_string()).unwrap();
        let before = fs::symlink_metadata(&path).unwrap();
        fs::remove_file(&path).unwrap();
        assert!(std::process::Command::new("mkfifo")
            .arg(&path)
            .status()
            .unwrap()
            .success());
        let started = std::time::Instant::now();
        assert!(open_manifest(&path, &before).is_err());
        assert!(started.elapsed() < std::time::Duration::from_secs(1));
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn replaced_regular_manifest_identity_is_refused() {
        let root = std::env::temp_dir().join(format!("dds-open-identity-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("runtime-manifest.json");
        fs::write(&path, manifest().to_string()).unwrap();
        let before = fs::symlink_metadata(&path).unwrap();
        fs::rename(&path, root.join("previous")).unwrap();
        fs::write(&path, manifest().to_string()).unwrap();
        assert!(open_manifest(&path, &before).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn changed_manifest_during_read_refuses_runtime_resolution() {
        use std::io::{Seek, SeekFrom, Write};
        use std::os::unix::fs::PermissionsExt;

        let root = std::env::temp_dir().join(format!("dds-read-manifest-{}", std::process::id()));
        fs::create_dir_all(root.join("python/bin")).unwrap();
        let python = root.join("python/bin/python3");
        fs::write(&python, b"synthetic interpreter").unwrap();
        fs::set_permissions(&python, fs::Permissions::from_mode(0o755)).unwrap();
        assert_eq!(resolve_bundled_python_executable(&root).unwrap(), python);

        let path = root.join("runtime-manifest.json");
        let original = manifest().to_string() + " ";
        for change in ["rewrite", "truncate", "replace"] {
            fs::write(&path, &original).unwrap();
            assert_eq!(resolve_bundled_python_executable(&root).unwrap(), python);
            let result = resolve_with_manifest_reader(&root, |reader| {
                let mut first_byte = [0];
                reader.read_exact(&mut first_byte)?;
                match change {
                    "rewrite" => {
                        let mut writer = fs::OpenOptions::new().write(true).open(&path)?;
                        writer.seek(SeekFrom::End(-1))?;
                        writer.write_all(b"\n")?;
                        writer.set_modified(std::time::SystemTime::UNIX_EPOCH)?;
                    }
                    "truncate" => fs::OpenOptions::new()
                        .write(true)
                        .open(&path)?
                        .set_len(original.len() as u64 - 1)?,
                    "replace" => {
                        let replacement = root.join("replacement.json");
                        fs::write(&replacement, &original)?;
                        fs::rename(replacement, &path)?;
                    }
                    _ => unreachable!(),
                }
                let mut bytes = first_byte.to_vec();
                reader.read_to_end(&mut bytes)?;
                Ok(bytes)
            });
            assert!(
                matches!(&result, Err(error) if error.contains("Invalid runtime manifest")
                    && error.contains("changed during reading")),
                "{change}: {result:?}",
            );
        }
        fs::remove_dir_all(root).unwrap();
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
            manifest()
                .to_string()
                .replacen("{", "{\"schemaVersion\":2,", 1),
            manifest().to_string().replace(
                "\"python\":{",
                "\"python\":{\"executable\":\"python/bin/other\",",
            ),
            manifest()
                .to_string()
                .replacen("{", "{\"extra\":[{\"k\":1,\"k\":2}],", 1),
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
