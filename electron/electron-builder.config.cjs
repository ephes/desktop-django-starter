const WINDOWS_SIGNING_HASH_ALGORITHMS = ["sha256"];

function getTrimmedEnv(name, env = process.env) {
  const value = env[name];
  if (typeof value !== "string") {
    return undefined;
  }

  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function getEnvList(name, env = process.env) {
  const value = getTrimmedEnv(name, env);
  if (!value) {
    return undefined;
  }

  const items = value.split(",").map((item) => item.trim()).filter(Boolean);
  return items.length > 0 ? items : undefined;
}

function hasMacosNotarizationCredentials(env = process.env) {
  const hasApiKeyCredentials = Boolean(
    getTrimmedEnv("APPLE_API_KEY", env)
    && getTrimmedEnv("APPLE_API_KEY_ID", env)
    && getTrimmedEnv("APPLE_API_ISSUER", env)
  );
  const hasAppleIdCredentials = Boolean(
    getTrimmedEnv("APPLE_ID", env)
    && getTrimmedEnv("APPLE_APP_SPECIFIC_PASSWORD", env)
    && getTrimmedEnv("APPLE_TEAM_ID", env)
  );
  const hasKeychainCredentials = Boolean(getTrimmedEnv("APPLE_KEYCHAIN_PROFILE", env));

  return hasApiKeyCredentials || hasAppleIdCredentials || hasKeychainCredentials;
}

function hasWindowsSigningInputs(env = process.env) {
  return Boolean(
    getTrimmedEnv("WIN_CSC_LINK", env)
    || getTrimmedEnv("WIN_SIGN_CERT_SUBJECT_NAME", env)
    || getTrimmedEnv("WIN_SIGN_CERT_SHA1", env)
    || getTrimmedEnv("WINDOWS_SIGNING_PUBLISHER", env)
    || getTrimmedEnv("WIN_SIGN_TIMESTAMP_URL", env)
    || getTrimmedEnv("WIN_SIGN_TIMESTAMP_RFC3161_URL", env)
  );
}

function getWindowsSigntoolOptions(env = process.env) {
  if (!hasWindowsSigningInputs(env)) {
    return undefined;
  }

  const publisherNames = getEnvList("WINDOWS_SIGNING_PUBLISHER", env);
  const certificateSubjectName = getTrimmedEnv("WIN_SIGN_CERT_SUBJECT_NAME", env);
  const certificateSha1 = getTrimmedEnv("WIN_SIGN_CERT_SHA1", env);
  const timeStampServer = getTrimmedEnv("WIN_SIGN_TIMESTAMP_URL", env);
  const rfc3161TimeStampServer = getTrimmedEnv("WIN_SIGN_TIMESTAMP_RFC3161_URL", env);

  return {
    signingHashAlgorithms: WINDOWS_SIGNING_HASH_ALGORITHMS,
    ...(publisherNames
      ? { publisherName: publisherNames.length === 1 ? publisherNames[0] : publisherNames }
      : {}),
    ...(certificateSubjectName ? { certificateSubjectName } : {}),
    ...(certificateSha1 ? { certificateSha1 } : {}),
    ...(timeStampServer ? { timeStampServer } : {}),
    ...(rfc3161TimeStampServer ? { rfc3161TimeStampServer } : {})
  };
}

function buildConfig(env = process.env) {
  const windowsSigntoolOptions = getWindowsSigntoolOptions(env);

  return {
    appId: "io.github.joww12.desktop-django-starter",
    productName: "Desktop Django Starter",
    asar: true,
    npmRebuild: false,
    directories: {
      output: "dist"
    },
    files: [
      "main.js",
      "package.json",
      "preload.cjs",
      "scripts/bundled-python.cjs"
    ],
    extraResources: [
      {
        from: ".stage/backend",
        to: "backend",
        filter: ["**/*"]
      }
    ],
    mac: {
      category: "public.app-category.developer-tools",
      target: ["dmg"],
      artifactName: "desktop-django-starter-macos-${version}-${arch}.${ext}",
      hardenedRuntime: true,
      gatekeeperAssess: false,
      entitlements: "signing/entitlements.mac.plist",
      entitlementsInherit: "signing/entitlements.mac.inherit.plist",
      // electron-builder already supports notarytool credentials directly, so
      // keep notarization alongside the rest of the packaging config.
      notarize: hasMacosNotarizationCredentials(env)
    },
    dmg: {
      sign: false
    },
    win: {
      target: ["nsis"],
      artifactName: "desktop-django-starter-windows-${version}-${arch}.${ext}",
      ...(windowsSigntoolOptions ? { signtoolOptions: windowsSigntoolOptions } : {})
    },
    nsis: {
      oneClick: false,
      perMachine: false,
      allowToChangeInstallationDirectory: true
    },
    linux: {
      category: "Development",
      target: ["AppImage"],
      artifactName: "desktop-django-starter-linux-${version}-${arch}.${ext}"
    }
  };
}

const config = buildConfig();

module.exports = config;
module.exports.buildConfig = buildConfig;
module.exports.getEnvList = getEnvList;
module.exports.getWindowsSigntoolOptions = getWindowsSigntoolOptions;
module.exports.hasMacosNotarizationCredentials = hasMacosNotarizationCredentials;
