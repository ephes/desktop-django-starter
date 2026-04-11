# Flying Stable Design Guide

Design decisions and patterns established during the UI redesign session (2026-03-31).

## Branding

- **App name**: Flying Stable (Pegasus/pony theme for the Django desktop starter)
- **Logo**: Custom Pegasus SVG, single-color, inline in the topnav using CSS `currentColor`
- **Sections**: "My Ponies" (CRUD demo), "Stable Routines" (background tasks demo)
- **Item statuses**: Grazing (backlog), Galloping (active), Show Ready (done)
- **Form labels**: Name, Personality, Status
- **Themed messages**: "Your pony needs a name.", "Do you know nothing about your pony?", "Release All Ponies"

## Color System

All colors are CSS custom properties defined in `:root` in `app.css`. No hardcoded hex values outside `:root`.

| Token | Value | Usage |
|-------|-------|-------|
| `--teal-deep` | `#108D82` | Primary teal, table headers, edit actions |
| `--teal-bright` | `#4FC0BC` | Nav links, logo, focus rings, active states |
| `--teal-dark` | `#0A544E` | Page header background, title color in tables |
| `--dark` | `#222121` | Topnav and footer background |
| `--accent` | `#D4790A` | Primary action buttons (amber-orange, tuned to match header image) |
| `--accent-hover` | `#B86808` | Hover state for primary buttons |
| `--danger` | `#C24B5A` | Delete/destructive actions (pinkish-red, deliberately not aggressive) |
| `--danger-hover` | `#A8404E` | Hover state for danger elements |
| `--warning` | `#D4790A` | Galloping status badge |
| `--warning-text` | `#A35E08` | Galloping badge text |
| `--bg-page` | `#F2F4F3` | Page background |
| `--bg-card` | `#FFFFFF` | Panel/card background |
| `--text-primary` | `#222121` | Primary text |
| `--text-muted` | `#5A6B6A` | Secondary/muted text |
| `--border` | `#D4DDDB` | Borders and separators |

## Layout Structure

```
+--[ Topnav (dark) ]------------------------------------------+
| Logo  FLYING STABLE          My Ponies  Routines  [Button]  |
+--[ 2px teal-bright border ]----------------------------------+
+--[ Page Header (teal-dark, 30vh, optional bg image) ]--------+
|                     Centered H1                              |
+--------------------------------------------------------------+
  +--[ Panel (white card, 1.5rem padding) ]------------------+
  | [hint text]                          [Action Button]     |
  |----------------------------------------------------------|
  | [HEADER BAR - full width gray background]                |
  |   Name     Status    Personality           Updated       |
  |----------------------------------------------------------|
  | Content rows with indented separators                    |
  +----------------------------------------------------------+
+--[ Footer (dark, sticky) ]-----------------------------------+
|                            Desktop Django Starter 2026       |
+--------------------------------------------------------------+
```

### Key measurements

- Topnav padding: `0.75rem 1.25rem`
- Page header: `min-height: 30vh`, H1 font-size: `clamp(3.5rem, 9vw, 5rem)`
- Panel padding: `1.5rem`, bottom: `2.25rem`
- Panel toolbar: negative margin to span full panel width, `1.5rem` padding top and bottom
- Table: full panel width via negative margins, cell padding `1rem`, first/last cell padding `1.5rem`
- Logo: `4rem` with `margin: -1rem 0` to extend beyond topnav
- Font: Play (Google Fonts, weights 400 and 700 only)

## Design Patterns

### Empty States

Centered SVG illustration with descriptive text below. Both illustrations follow the same visual language:

- **Opacity layers**: 0.18 (back element), 0.35 (middle), 0.6 (front)
- **Accent circle** (bottom-right): r=36, stroke opacity 0.2, symbol fill opacity 0.35
- **My Ponies**: Stacked document icons with X-in-circle
- **Stable Routines**: Three interlocking gears with play-in-circle
- Illustration CSS width: 280px (items), 235px (tasks, with `margin-top: -1rem`)

### Status Badges

Inline colored badges with matching text and background:

- Grazing: gray text on light gray (`rgba(0,0,0,0.06)`)
- Galloping: amber text on light amber (`rgba(212,148,10,0.12)`)
- Show Ready: teal text on light teal (`rgba(16,141,130,0.1)`)

### Buttons

- **Primary** (`.primary`): Amber fill (`--accent`)
- **Secondary/Ghost** (`.secondary`): Transparent with teal border, hover fills with `rgba(16,141,130,0.15)`
- **Danger** (`.danger`): Pinkish-red fill (`--danger`)
- All buttons: `border-radius: 0.5rem`, `font-weight: 700`, `0.6rem 1.25rem` padding

### Delete Modal

In-page overlay instead of separate page. Fetch-based POST with CSRF token from cookie. Accessible: `role="dialog"`, `aria-modal="true"`, Escape key closes, focus lands on cancel button.

### Form Validation

Custom client-side validation with `novalidate` on the form. Inline tooltip appears below the field with:

- Warning triangle SVG icon
- Pink background (`rgba(194,75,90,0.08)`)
- Small upward-pointing connector triangle
- `justify-self: start` to prevent full-width stretch
- Disappears on input

### Table Rows

- Row separators use `::after` pseudo-elements, indented `1.5rem` from both sides
- Last row has no separator
- Header bar spans full panel width with gray background (`--bg-page`)
- `vertical-align: top` on all cells
- Title column: `max-width: 14rem`, bold, `--teal-dark` color
- Notes column: muted color, `max-width: 20rem`, truncated to 20 words
- Date column: right-aligned, date and time on separate lines
- Actions: Edit (pencil) + Delete (X-in-circle) icons, 16px, muted gray, colored on hover

### Header Background Images

Per-page via `{% block header_class %}` in base template. Use CSS `background-image` with a semi-transparent overlay for text readability:

```css
background-image: linear-gradient(rgba(10, 84, 78, 0.3), rgba(10, 84, 78, 0.3)), url('...');
background-size: cover;
background-position: 20% 45%;
```

## Development Tooling

### Auto-Reload

`django-browser-reload` is configured in `local.py` only. CSS changes trigger automatic browser reload. Template changes may need `Cmd+Shift+R`.

### Screenshots

Playwright is available for automated screenshots:

```python
from playwright.sync_api import sync_playwright
# Use wait_until='domcontentloaded' (not 'networkidle' — browser-reload SSE blocks it)
page.goto('http://127.0.0.1:8000', wait_until='domcontentloaded')
page.wait_for_timeout(1000)
page.screenshot(path='/tmp/screenshot.png')
```

### SVG Optimization

`svgo` is available via Homebrew for optimizing SVG files.

## Splash Screen

Available at `/splash/` and now wired into Electron startup. Standalone HTML with:

- Breathing logo animation
- Three bouncing dots
- "Saddling up..." status text
- Dark background, teal-bright color scheme
- Reused by Electron during backend startup before the main window is ready
- Still separate from Tauri's shell-local splash window and Positron's current startup flow
