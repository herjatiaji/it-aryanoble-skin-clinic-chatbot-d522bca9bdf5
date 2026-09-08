# DESIGN.md — Arya Noble Frontend Design System

This document is strictly the source of truth for design patterns, CSS/UI guidelines, and Figma tokens. For architectural rules or project structure, see `AGENTS.md`.

## Styling & UI Best Practices

### Tailwind CSS v4

- **Utility First:** Rely on Tailwind utility classes for all styling.
- **Dynamic Classes:** Use the `cn()` utility (`clsx` + `tailwind-merge`) when conditionally applying Tailwind classes to avoid specificity conflicts.
  ```tsx
  import { cn } from "@/lib/utils"

  <div className={cn("base-classes", isTrue && "conditional-classes", className)}>
  ```
- **Avoid Arbitrary Values:** Avoid arbitrary values (e.g., `w-[300px]`) if a design token exists. Extract repeated arbitrary values into `src/app/globals.css` as CSS variables.

### Shadcn UI (Base-Mira Style)

- We use the `base-mira` style for Shadcn components.
- **Modification:** Shadcn components are owned by the project. You can modify their source code in `src/components/ui/` to match specific Figma design requirements, but try to use CSS variables in `globals.css` for global theming (colors, radiuses) first.
- **Icons:** We use Remix Icons (`@remixicon/react`). Do not use Lucide.

## Design Tokens (Extracted from Figma)

### Colors
**Blue (Primary Palette)**
- 50: `#e6f2fe`
- 100: `#b0d8fc`
- 200: `#8ac5fa`
- 300: `#54abf8`
- 400: `#339af7`
- 500: `#0081f5` (Primary)
- 600: `#0075df`
- 700: `#005cae`
- 800: `#004787`
- 900: `#003667`

**Black (Neutral/Text Palette)**
- 50: `#e7e7e7`
- 100: `#b3b3b3`
- 200: `#8e8e8e`
- 300: `#5b5b5b`
- 400: `#3b3b3b`
- 500: `#0a0a0a`
- 600: `#090909`
- 700: `#070707`
- 800: `#060606`
- 900: `#040404`

**White (Background Palette)**
- 50: `#fefefe`
- 100: `#fcfcfc`
- 200: `#fafafa`
- 300: `#f8f8f8`
- 400: `#f6f6f6`
- 500: `#f4f4f4`
- 600: `#dedede`
- 700: `#adadad`
- 800: `#868686`
- 900: `#666666`

**Green (Success Palette)**
- 50: `#e7fcf2`
- 100: `#b5f5d6`
- 200: `#92f0c2`
- 300: `#60eaa7`
- 400: `#41e595`
- 500: `#11df7b`
- 600: `#0fcb70`
- 700: `#0c9e57`
- 800: `#097b44`
- 900: `#075e34`

**Red (Destructive Palette)**
- 50: `#fce7e7`
- 100: `#f6b4b4`
- 200: `#f19090`
- 300: `#eb5e5e`
- 400: `#e73e3e`
- 500: `#e10e0e`
- 600: `#cd0d0d`
- 700: `#a00a0a`
- 800: `#7c0808`
- 900: `#5f0606`

**Orange (Warning Palette)**
- 50: `#fffae8`
- 100: `#ffefb8`
- 200: `#ffe796`
- 300: `#ffdb66`
- 400: `#ffd548`
- 500: `#ffca1a`
- 600: `#e8b818`
- 700: `#b58f12`
- 800: `#8c6f0e`
- 900: `#6b550b`

### Typography
- **Font Family:** Inter (Primary font for headings and body)
- **Headings:** H1, H2, H3, H4 specifications follow Tailwind base scales.
- **Body:** Base text sizes and line heights follow Tailwind base scales.

### Spacing & Borders
- **Border Radius:** `var(--radius)` (Base `0.5rem`). Every new element must always use `rounded-md`.

## Component Slicing Guidelines

1. **Modular Components:** Do not write one long monolithic file. Break down Figma screens into small, reusable components (Atoms -> Molecules -> Organisms) and place them in separate files (e.g., within a `components/` sub-directory for page-specific pieces).
2. **Desktop First Focus (Tailwind Mobile-First):** The primary target interface for this project is large desktop (`lg` and `xl` breakpoints). Since Tailwind uses mobile-first media queries, you should implement the base layout classes for mobile and strictly use `lg:` overrides for desktop, BUT you must design and finalize the `lg:` desktop layout first before styling the base mobile layout. 
3. **State:** Keep UI components as stateless/dumb as possible. Lift business logic state up to the page or feature level, keeping UI states (e.g., hover, dropdown open) contained within the component.
4. **Dark Mode Exclusion:** Dark mode is **NOT supported** in this project. Do not write `dark:` variants or add a theme provider for dark mode.
5. **Z-Index & Overlays:** Carefully manage your z-indexes. Use standard classes (`z-10` to `z-50`) sequentially. Modals, sheets, and popovers should always be rendered at the root stacking context (e.g., using React Portals implicitly via Radix/Shadcn primitives) to avoid clipping.
