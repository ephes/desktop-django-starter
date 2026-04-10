const DESKTOP_AUTH_HEADER = "X-Desktop-Django-Token";

function requestUrlMatchesOrigin(requestUrl, djangoOrigin) {
  let parsedRequestUrl;
  let parsedDjangoOrigin;

  try {
    parsedRequestUrl = new URL(requestUrl);
    parsedDjangoOrigin = new URL(djangoOrigin);
  } catch (_error) {
    return false;
  }

  return parsedRequestUrl.protocol === parsedDjangoOrigin.protocol
    && parsedRequestUrl.hostname === parsedDjangoOrigin.hostname
    && parsedRequestUrl.port === parsedDjangoOrigin.port;
}

function buildDesktopAuthHeaders(token) {
  if (!token) {
    return {};
  }

  return {
    [DESKTOP_AUTH_HEADER]: token
  };
}

function withDesktopAuthHeader(requestHeaders, token) {
  return {
    ...requestHeaders,
    ...buildDesktopAuthHeaders(token)
  };
}

function getDesktopAuthWebRequestFilter(djangoOrigin) {
  const parsedDjangoOrigin = new URL(djangoOrigin);
  return {
    urls: [`${parsedDjangoOrigin.protocol}//${parsedDjangoOrigin.host}/*`]
  };
}

function desktopAuthHeadersForRequest(details, djangoOrigin, token) {
  if (!token || !requestUrlMatchesOrigin(details.url, djangoOrigin)) {
    return details.requestHeaders;
  }

  return withDesktopAuthHeader(details.requestHeaders, token);
}

module.exports = {
  DESKTOP_AUTH_HEADER,
  buildDesktopAuthHeaders,
  desktopAuthHeadersForRequest,
  getDesktopAuthWebRequestFilter,
  requestUrlMatchesOrigin,
  withDesktopAuthHeader
};
