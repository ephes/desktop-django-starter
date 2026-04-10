const test = require("node:test");
const assert = require("node:assert/strict");

const {
  buildConfig,
  detectGithubReleaseRepository,
  getElectronUpdatePublishConfig,
  getEnvList,
  getWindowsSigntoolOptions,
  hasMacosNotarizationCredentials,
  parseGithubRepositorySlug
} = require("./electron-builder-config.cjs");

test("electron-builder config ships the staged backend as a packaged resource", () => {
  const config = buildConfig({});

  assert.equal(config.directories.output, "dist");
  assert.deepEqual(config.files, [
    "main.js",
    "package.json",
    "preload.cjs",
    "scripts/auth-token.cjs",
    "scripts/bundled-python.cjs",
    "scripts/updates.cjs",
    "assets/icons/app-icon.png",
    {
      from: "../../scripts",
      to: "scripts/shared",
      filter: ["bundled-python.cjs"]
    }
  ]);
  assert.deepEqual(config.extraResources, [
    {
      from: "../../.stage/backend",
      to: "backend",
      filter: ["**/*"]
    }
  ]);
  assert.equal(config.mac.entitlements, "signing/entitlements.mac.plist");
  assert.equal(config.mac.entitlementsInherit, "signing/entitlements.mac.inherit.plist");
  assert.equal(config.mac.hardenedRuntime, true);
  assert.equal(config.mac.gatekeeperAssess, false);
  assert.equal(config.mac.icon, "assets/icons/app-icon.icns");
  assert.deepEqual(config.mac.target, ["dmg", "zip"]);
  assert.equal(config.mac.notarize, false);
  assert.deepEqual(config.dmg, { sign: false });
  assert.equal(config.win.icon, "assets/icons/app-icon.png");
  assert.equal(config.win.signtoolOptions, undefined);
  assert.equal(config.linux.icon, "assets/icons/app-icon.png");
});

test("electron-builder config keeps per-platform artifact names explicit", () => {
  const config = buildConfig({});

  assert.equal(config.mac.artifactName, "desktop-django-starter-macos-${version}-${arch}.${ext}");
  assert.equal(
    config.win.artifactName,
    "desktop-django-starter-windows-${version}-${arch}.${ext}"
  );
  assert.equal(
    config.linux.artifactName,
    "desktop-django-starter-linux-${version}-${arch}.${ext}"
  );
});

test("electron-builder config does not expose test helpers as enumerable keys", () => {
  const config = require("../electron-builder.config.cjs");

  assert.equal(Object.getOwnPropertyNames(config).includes("buildConfig"), false);
  assert.equal(Object.getOwnPropertyNames(config).includes("getEnvList"), false);
  assert.equal(Object.getOwnPropertyNames(config).includes("getWindowsSigntoolOptions"), false);
  assert.equal(Object.getOwnPropertyNames(config).includes("hasMacosNotarizationCredentials"), false);
});

test("electron-builder config includes a GitHub update feed by default", () => {
  const config = buildConfig(
    { GITHUB_REPOSITORY: "example/desktop-django-starter" },
    { readOriginUrl: () => "" }
  );

  assert.deepEqual(config.publish, [
    {
      provider: "github",
      owner: "example",
      repo: "desktop-django-starter",
      releaseType: "draft",
      publishAutoUpdate: true
    }
  ]);
});

test("electron-builder config falls back to the git origin remote for the update feed", () => {
  const publishConfig = getElectronUpdatePublishConfig(
    {},
    { readOriginUrl: () => "git@github.com:ephes/desktop-django-starter.git" }
  );

  assert.deepEqual(publishConfig, [
    {
      provider: "github",
      owner: "ephes",
      repo: "desktop-django-starter",
      releaseType: "draft",
      publishAutoUpdate: true
    }
  ]);
});

test("electron-builder config allows generic update feed override", () => {
  const publishConfig = getElectronUpdatePublishConfig({
    DESKTOP_DJANGO_UPDATE_URL: "https://updates.example.test/desktop-django-starter/"
  });

  assert.deepEqual(publishConfig, [
    {
      provider: "generic",
      url: "https://updates.example.test/desktop-django-starter/",
      publishAutoUpdate: true
    }
  ]);
});

test("electron-builder config allows GitHub release feed override", () => {
  const publishConfig = getElectronUpdatePublishConfig({
    DESKTOP_DJANGO_UPDATE_GITHUB_OWNER: "example",
    DESKTOP_DJANGO_UPDATE_GITHUB_REPO: "internal-desktop-django",
    DESKTOP_DJANGO_UPDATE_GITHUB_RELEASE_TYPE: "release"
  });

  assert.deepEqual(publishConfig, [
    {
      provider: "github",
      owner: "example",
      repo: "internal-desktop-django",
      releaseType: "release",
      publishAutoUpdate: true
    }
  ]);
});

test("electron-builder config detects GitHub owner and repo from common repository formats", () => {
  assert.deepEqual(parseGithubRepositorySlug("example/internal-desktop-django"), {
    owner: "example",
    repo: "internal-desktop-django"
  });
  assert.deepEqual(parseGithubRepositorySlug("git@github.com:example/internal-desktop-django.git"), {
    owner: "example",
    repo: "internal-desktop-django"
  });
  assert.deepEqual(
    parseGithubRepositorySlug("https://github.com/example/internal-desktop-django.git"),
    {
      owner: "example",
      repo: "internal-desktop-django"
    }
  );
  assert.equal(parseGithubRepositorySlug("https://example.com/not-github/repo.git"), null);
});

test("electron-builder config prefers GITHUB_REPOSITORY over git origin detection", () => {
  const detected = detectGithubReleaseRepository(
    { GITHUB_REPOSITORY: "example/from-actions" },
    { readOriginUrl: () => "git@github.com:ephes/from-origin.git" }
  );

  assert.deepEqual(detected, {
    owner: "example",
    repo: "from-actions"
  });
});

test("electron-builder config falls back to the hardcoded repository default", () => {
  const detected = detectGithubReleaseRepository(
    {},
    { readOriginUrl: () => "" }
  );

  assert.deepEqual(detected, {
    owner: "ephes",
    repo: "desktop-django-starter"
  });
});

test("electron-builder enables macOS notarization when Apple credentials are present", () => {
  const env = {
    APPLE_API_KEY: "/tmp/AuthKey_ABCD1234.p8",
    APPLE_API_KEY_ID: "ABCD1234",
    APPLE_API_ISSUER: "8f1ed882-1111-2222-3333-444444444444"
  };

  const config = buildConfig(env);

  assert.equal(hasMacosNotarizationCredentials(env), true);
  assert.equal(config.mac.notarize, true);
});

test("electron-builder enables macOS notarization for Apple ID credentials", () => {
  const env = {
    APPLE_ID: "builds@example.com",
    APPLE_APP_SPECIFIC_PASSWORD: "app-specific-password",
    APPLE_TEAM_ID: "TEAM123456"
  };

  const config = buildConfig(env);

  assert.equal(hasMacosNotarizationCredentials(env), true);
  assert.equal(config.mac.notarize, true);
});

test("electron-builder enables macOS notarization for keychain profile credentials", () => {
  const env = {
    APPLE_KEYCHAIN_PROFILE: "desktop-django-starter-notary"
  };

  const config = buildConfig(env);

  assert.equal(hasMacosNotarizationCredentials(env), true);
  assert.equal(config.mac.notarize, true);
});

test("electron-builder keeps macOS notarization disabled for partial API key credentials", () => {
  const env = {
    APPLE_API_KEY: "/tmp/AuthKey_ABCD1234.p8",
    APPLE_API_KEY_ID: "ABCD1234"
  };

  const config = buildConfig(env);

  assert.equal(hasMacosNotarizationCredentials(env), false);
  assert.equal(config.mac.notarize, false);
});

test("electron-builder exposes optional Windows signing settings from env", () => {
  const env = {
    WIN_CSC_LINK: "file:///tmp/windows-cert.p12",
    WINDOWS_SIGNING_PUBLISHER: "Example Org, Example Org GmbH",
    WIN_SIGN_CERT_SHA1: "ABCDEF0123456789",
    WIN_SIGN_TIMESTAMP_RFC3161_URL: "http://timestamp.example.test"
  };

  const signtoolOptions = getWindowsSigntoolOptions(env);
  const config = buildConfig(env);

  assert.deepEqual(signtoolOptions, {
    signingHashAlgorithms: ["sha256"],
    publisherName: ["Example Org", "Example Org GmbH"],
    certificateSha1: "ABCDEF0123456789",
    rfc3161TimeStampServer: "http://timestamp.example.test"
  });
  assert.deepEqual(config.win.signtoolOptions, signtoolOptions);
});

test("electron-builder does not expose Windows signtool options for generic signing env alone", () => {
  const env = {
    CSC_LINK: "file:///tmp/macos-or-shared-cert.p12",
    CSC_NAME: "Developer ID Application: Example Org"
  };

  const config = buildConfig(env);

  assert.equal(getWindowsSigntoolOptions(env), undefined);
  assert.equal(config.win.signtoolOptions, undefined);
});

test("getEnvList trims items and ignores empty entries", () => {
  assert.deepEqual(
    getEnvList("WINDOWS_SIGNING_PUBLISHER", {
      WINDOWS_SIGNING_PUBLISHER: " Example Org, , Example Org GmbH, "
    }),
    ["Example Org", "Example Org GmbH"]
  );
  assert.equal(
    getEnvList("WINDOWS_SIGNING_PUBLISHER", {
      WINDOWS_SIGNING_PUBLISHER: "   ,  "
    }),
    undefined
  );
});
