# Project instructions

- Work inside the JEV project. Use native Windows tools; do not invoke local Docker, WSL or virtual machines.
- Runtime inference must remain local NanoJev and local OCR. Do not introduce Claude, cloud APIs or API keys into the application.
- Return source evidence with locators. Do not silently introduce generated answers or summaries.
- Preserve user document directories, uploads, immutable source snapshots and running libraries.
- Never commit models, indexes, private documents, real-corpus evaluation outputs, credentials, node_modules or release binaries.
- Keep research under docs/research separate from claims about implemented capabilities.
- Verify Python changes with pytest, Electron lifecycle changes with npm test, and frontend changes with the production build. Real model smoke tests are separate from unit tests.
- Release assets belong in GitHub Releases. Keep the original model precision and hashes, preserve third-party notices, and verify all package payloads.
- If using a browser, close temporary tabs when finished and preserve the user's existing tabs.
