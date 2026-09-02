export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request);
    const url = new URL(request.url);
    const path = url.pathname;

    if (path.endsWith('.md') || path.endsWith('.yaml') || path.endsWith('.yml') || path.endsWith('.txt')) {
      const headers = new Headers(response.headers);
      const contentType = headers.get('content-type') || 'text/plain';
      if (!contentType.includes('charset')) {
        headers.set('content-type', contentType + '; charset=utf-8');
      }
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers,
      });
    }

    return response;
  }
};
