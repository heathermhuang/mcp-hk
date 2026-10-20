/* Same-origin assets and initializer work under the API's restrictive CSP. */
SwaggerUIBundle({
  url: '/openapi.json',
  dom_id: '#swagger-ui',
  layout: 'BaseLayout',
  deepLinking: true,
  showExtensions: true,
  showCommonExtensions: true,
  validatorUrl: null,
  presets: [SwaggerUIBundle.presets.apis],
  onComplete() { document.getElementById('docs-status').hidden = true; },
});
