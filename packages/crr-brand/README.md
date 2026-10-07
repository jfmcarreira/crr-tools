# CRR brand

Canonical CRR visual assets and framework-independent CSS, consumed by both apps.

- `assets/logo.png`: canonical CRR logo.
- `assets/favicon.png`: canonical CRR favicon.
- `styles/tokens.css`: shared palette around `#ed1c24`, font stack, radii,
  shadows, spacing and focus-ring values.
- `styles/base.css`: box sizing, body defaults, links, controls, focus and tables.
- `styles/components.css`: the existing primary/quiet button, panel and error
  alert patterns used by both Vue and Jinja. Existing class names are supported
  directly so templates retain their own structure.

Load tokens, base and components **before** the application's own stylesheet.
Application CSS owns sizes, typography hierarchy, responsive layout, control
spacing, specialist badges and print-card dimensions. Local variable names are
aliases of `--crr-*` tokens, keeping existing styles/components compatible.

Tournament's `frontend/` resolves `@crr-brand` through Vite and uses `assets/` as its public
asset directory. Shifts mounts this directory at `/brand` using FastAPI
`StaticFiles`; Jinja uses `url_for('brand', ...)` so `ROOT_PATH` is respected.
Its PDF exporter reads this same logo. Both Docker builds copy the package from
the repository-root context, preserving its relative path to each application.

Brand-only changes trigger both application CI jobs. This package contains no
domain code or UI framework components and has no independent public version.

After changing branding, run both application test/build commands and verify the affected desktop, mobile and print layouts.
