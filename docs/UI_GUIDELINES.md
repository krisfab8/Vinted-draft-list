# Dodis — UI Guidelines

## Brand Identity

**Name:** Dodis
**Tagline:** Sell smarter. List faster.
**Tone:** Direct, confident, slightly playful. Never corporate, never cold.

---

## Colours

```css
:root {
  /* Primary */
  --d-red:        #C41E1E;   /* "Do" wordmark, primary action danger */
  --d-red-dark:   #A01818;   /* hover state */

  /* Accent */
  --d-green:      #16C784;   /* primary CTA, success states */
  --d-green-dark: #0FA968;   /* hover */
  --d-green-pale: #EDFBF4;   /* success backgrounds */

  --d-blue:       #3B82F6;   /* focus rings, links */
  --d-blue-glow:  rgba(59,130,246,0.18);

  --d-gold:       #F59E0B;   /* warnings, price highlight */

  /* Flame gradient (E3) */
  --d-flame-base: #AA1515;
  --d-flame-mid:  #EE2222;
  --d-flame-tip:  #FFE0C0;

  /* Neutrals */
  --d-bg:     #F8FAFC;
  --d-soft:   #F1F5F9;
  --d-border: #E2E8F0;
  --d-muted:  #64748B;
  --d-text:   #0F172A;
  --d-white:  #FFFFFF;
}
```

---

## Typography

**Primary font:** Plus Jakarta Sans (Google Fonts)
- Wordmark: 800 weight
- UI headings: 700
- Body: 400–500
- Labels/caps: 600, letter-spacing 0.08em

**Fallback stack:** `'Plus Jakarta Sans', system-ui, -apple-system, sans-serif`

**Scale:**
- Page title: 24–28px
- Section heading: 18px
- Card title: 15px
- Body: 14–15px
- Label/caption: 12px

---

## Wordmark

- "Do" = `#C41E1E` (red)
- "is" = white (or `#0F172A` on light backgrounds)
- Font: Plus Jakarta Sans 800
- Flame SVG on dotless ı — E3 gradient, positioned `top: -0.24em` above letter
- Never stretch, rotate, or recolour the wordmark
- Minimum size: 56px tall in icon context

---

## Logo / Icon

- **Primary icon:** White D on red circle (`#C41E1E`), E3 flame visible through D counter
- **Rounded square variant:** for iOS home screen, app stores
- **Monochrome variant:** white on dark for contexts where colour is unavailable
- Do not add drop shadows, outlines, or decorative borders to the icon

---

## Components

### Buttons

```
Primary CTA:    bg --d-green,  text white, radius 12px, font 600
Secondary:      bg --d-soft,   text --d-text, radius 12px
Danger:         bg --d-red,    text white
Ghost:          border --d-border, bg transparent
```

- Padding: `12px 20px` default, `10px 16px` small
- No all-caps on buttons (sentence case)
- Loading state: spinner, keep button width stable

### Cards

```
bg: white
border: 1px solid --d-border
border-radius: 16px
padding: 16px
box-shadow: 0 1px 3px rgba(0,0,0,0.06)
```

### Inputs

```
border: 1.5px solid --d-border
border-radius: 10px
focus: border --d-blue, box-shadow 0 0 0 3px --d-blue-glow
font: inherit, 14px
padding: 10px 12px
```

### Tags / Badges

```
border-radius: 999px (pill)
font: 11px, weight 600, letter-spacing 0.06em
padding: 3px 8px
```

---

## Layout

- Mobile-first. Design for 390px width first.
- Max content width: 480px (centred on desktop)
- Safe area padding: 16px sides
- Bottom nav: 60px tall, always visible on mobile
- Top nav/header: 56px, teal `#0D9488` (existing brand colour until full migration)

---

## Motion

- Keep transitions subtle: `0.15s ease` for state changes
- Celebration moments (first item, sold item) can use scale + opacity animation
- No infinite looping animations on core UI
- Flame in wordmark is static — do not animate it in product UI

---

## States

| State | Treatment |
|-------|-----------|
| Loading | Skeleton or spinner, never blank |
| Empty | Friendly message + CTA, never raw emptiness |
| Error | Red border/icon, human-readable message, action to fix |
| Success | Green, brief, then dismiss |
| Warning | Gold/amber, visible but not alarming |

---

## Voice & Copy

- Use "item" not "product" or "listing" (unless in technical context)
- Use "sold" not "completed" or "closed"
- "Draft" = not yet on Vinted; "Listed" = live on Vinted
- Errors should say what happened and what to do: "Session expired. Tap to reconnect."
- No jargon in user-facing text. Keep it conversational.
- Exclamation marks: use sparingly. Only for genuine celebrations.

---

## Accessibility

- Colour is never the only indicator (always pair with icon or text)
- Minimum touch target: 44×44px
- Focus rings visible on all interactive elements (use `--d-blue-glow`)
- Font sizes: minimum 12px, prefer 14px+ for body text
