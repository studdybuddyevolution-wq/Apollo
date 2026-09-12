export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request)
    const url = new URL(request.url)

    // Never let the SPA entry document get stuck in a browser/CDN cache after
    // a Cloudflare deployment. Vite's hashed JS/CSS assets can remain cached.
    const isHtmlRequest =
      request.method === 'GET' &&
      (url.pathname === '/' || url.pathname.endsWith('.html') || !url.pathname.includes('.'))

    if (!isHtmlRequest) return response

    const headers = new Headers(response.headers)
    headers.set('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0')
    headers.set('Pragma', 'no-cache')
    headers.set('Expires', '0')

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    })
  },
}
