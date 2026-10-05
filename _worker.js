export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === '/submissions' || path.startsWith('/submissions/')) {
      const rest = path.slice('/submissions'.length) || '/';
      return Response.redirect(`https://centaurxiv.org/papers${rest}`, 301);
    }

    const response = await env.ASSETS.fetch(request);

    if (path.endsWith('.md') || path.endsWith('.yaml') || path.endsWith('.yml') || path.endsWith('.txt')) {
      const headers = new Headers(response.headers);
      const ext = path.split('.').pop();
      const mime = ext === 'md' ? 'text/markdown' : ext === 'yaml' || ext === 'yml' ? 'text/yaml' : 'text/plain';
      headers.set('content-type', mime + '; charset=utf-8');
      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers,
      });
    }

    return response;
  }
};
