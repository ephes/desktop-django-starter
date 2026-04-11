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

function getWindowOpenGuardResponse(targetUrl, djangoOrigin) {
  const navigationAction = getNavigationGuardAction(targetUrl, djangoOrigin);

  return {
    action: "deny",
    openExternal: navigationAction.openExternal
  };
}

module.exports = {
  getNavigationGuardAction,
  getWindowOpenGuardResponse,
  isExternalOpenableUrl
};
