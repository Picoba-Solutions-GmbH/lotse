export const environment = {
  url: window.location.href.substring(0, window.location.href.indexOf('/ui')),
  wsApiUrl: window.location.href.substring(0, window.location.href.indexOf('/ui')).replace('http', 'ws'),
  local: false,
};
