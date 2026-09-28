export default {
	async fetch(request, env) {
		const url = new URL(request.url);
		if (url.pathname === '/submissions' || url.pathname.startsWith('/submissions/')) {
			const rest = url.pathname.slice('/submissions'.length) || '/';
			return Response.redirect(`${url.origin}/papers${rest}`, 301);
		}

		const response = await env.ASSETS.fetch(request);

		const contentType = response.headers.get('content-type') || '';
		if (contentType && !contentType.includes('charset') && isTextType(contentType)) {
			const headers = new Headers(response.headers);
			headers.set('content-type', `${contentType}; charset=utf-8`);
			return new Response(response.body, {
				status: response.status,
				statusText: response.statusText,
				headers,
			});
		}

		return response;
	},
};

function isTextType(ct) {
	return (
		ct.startsWith('text/') ||
		ct.includes('application/json') ||
		ct.includes('application/xml') ||
		ct.includes('application/javascript')
	);
}
