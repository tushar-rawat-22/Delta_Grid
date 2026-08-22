# Public design direction

The public DeltaGrid surface should read like research infrastructure, not a generic AI or fintech landing page.

The design uses dense tables, status bands, timestamps, small labels, restrained borders, and a limited state palette. Decorative gradients, oversized marketing cards, fake terminal output, and invented trading metrics are deliberately avoided. Public numbers must come from configured public scope or deterministic demo fixtures; the site must never imply live positions, P&L, alpha, AUM, execution, or capital authority that do not exist.

The landing page explains the system through four things a technical visitor can verify quickly: configured research coverage, bounded public data inputs, current authority boundaries, and sanitized workspace previews. The public observer remains static and separate from the authenticated founder gateway.

Dense does not mean hostile to keyboard or assistive-technology users. The public shell keeps a visible-on-focus skip link, a focusable content target, labelled navigation, active-page semantics, and decorative marks hidden from screen readers. These are regression-tested because a terminal-like visual treatment is not an excuse to make the interface harder to navigate.

Motion is treated the same way. Smooth scrolling and screenshot hover movement are minor presentation details, not product state, so the public shell disables them when the operating system requests reduced motion. A quant interface should feel precise because the information is precise, not because it forces animation on every visitor.

Public metadata follows the same rule as the visible interface. Titles, descriptions, and social-preview metadata identify DeltaGrid as a quantitative research system without adding profitability, execution, or autonomous-trading claims that the product itself does not support. The static observer deliberately avoids absolute canonical or Open Graph URLs because generated HTML must not gain new external references just to improve link previews. The GitHub profile and review guide already provide the stable public entry point.

The live public-boundary monitor should verify durable product semantics rather than freeze a particular headline or CTA. It checks stable authority markers such as Mission 104 remaining not authorized and the presence of founder separation, while security headers, sanitized demo markers, forbidden private markers, and anonymous founder-surface denial remain independently enforced. This lets the public copy evolve without silently weakening the boundary monitor or making a legitimate redesign look like an incident.

This visual rule is part of the product boundary. Future redesigns should preserve the same principle even if the typography or layout changes: information density is useful, decoration is secondary, and state must never be fabricated to make the system appear more mature than it is.
