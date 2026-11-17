const { requestUrlMatchesOrigin } = require("./auth-token.cjs");

function isExternalOpenableUrl(targetUrl) {
  let parsedUrl;
  try {
    parsedUrl = new URL(targetUrl);
  } catch (_error) {
    return false;
  }

  return ["http:", "https:", "mailto:"].includes(parsedUrl.protocol);
}

function getNavigationGuardAction(targetUrl, djangoOrigin) {
  if (requestUrlMatchesOrigin(targetUrl, djangoOrigin)) {
    return {
      allowNavigation: true,
      openExternal: false
    };
  }

  return {
    allowNavigation: false,
    openExternal: isExternalOpenableUrl(targetUrl)
  };
}

// Electron emits `will-redirect` (not `will-navigate`) for server-side 3xx
// redirects, so an off-origin redirect from Django would otherwise load an
// external page in the main window with the preload bridge attached. Apply the
// same origin rule as `will-navigate` to main-frame redirects. Subframe
// redirects follow the subframe policy instead: subframes do not get the
// preload bridge (`nodeIntegrationInSubFrames` stays false), the IPC handler
// checks the sender origin, and blocking them would break ordinary embeds.
// Anything that does not explicitly say it is a subframe is treated as the
// main frame so missing details fail closed.
function getRedirectGuardAction(details, djangoOrigin) {
  if (details && details.isMainFrame === false) {
    return {
      allowNavigation: true,
      openExternal: false
    };
  }

  return getNavigationGuardAction(details ? details.url : undefined, djangoOrigin);
}

// Only pages served from the local Django origin may use the preload bridge.
// `event.senderFrame` can be null when the frame navigated away or was
// destroyed before the message was handled; refuse in that case.
function isTrustedIpcSender(event, djangoOrigin) {
  const senderFrame = event ? event.senderFrame : null;
  if (!senderFrame || !djangoOrigin) {
    return false;
  }

  return requestUrlMatchesOrigin(senderFrame.url, djangoOrigin);
}

// No renderer capability is needed by the starter. Adaptations may opt in to
// individual permissions for this live main frame; never infer a subframe's
// origin from the containing WebContents. Missing document evidence denies.
function registerSessionPermissionPolicy(owner, djangoOrigin, trustedPermissions = []) {
  const allowed = new Set(trustedPermissions);
  const admits = (contents, permission, details) => (
    allowed.has(permission)
    && contents === owner
    && !owner.isDestroyed()
    && details?.isMainFrame === true
    && requestUrlMatchesOrigin(details.requestingUrl, djangoOrigin)
    && requestUrlMatchesOrigin(owner.getURL(), djangoOrigin)
  );
  owner.session.setPermissionRequestHandler((contents, permission, callback, details) => {
    callback(admits(contents, permission, details));
  });
  owner.session.setPermissionCheckHandler((contents, permission, requestingOrigin, details) => (
    admits(contents, permission, details)
    && requestUrlMatchesOrigin(requestingOrigin, djangoOrigin)
  ));
}

function getWindowOpenGuardResponse(targetUrl, djangoOrigin) {
  const navigationAction = getNavigationGuardAction(targetUrl, djangoOrigin);

  return {
    action: "deny",
    openExternal: navigationAction.openExternal
  };
}

module.exports = {
  getNavigationGuardAction,
  getRedirectGuardAction,
  getWindowOpenGuardResponse,
  isExternalOpenableUrl,
  isTrustedIpcSender,
  registerSessionPermissionPolicy
};
