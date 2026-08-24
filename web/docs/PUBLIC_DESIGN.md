# Public UI

The public site is a read-only window into DeltaGrid. It should feel like a quantitative research control surface used for review, not a product launch page.

The first screen should answer, in order:

1. What is the current research result?
2. What authority is open or closed?
3. What programme stage is active?
4. What evidence and data surface exists?
5. Where should a reviewer drill down next?

Use the things that are actually true: current research status, configured coverage, provider limits, authority state, evidence boundaries, and sanitized workspace views. If a number exists only to make the page look impressive, leave it out. Do not publish invented P&L, Sharpe ratios, positions, AUM, "AI confidence", or imply that research software has trading authority.

Prefer dense tables, status tape, short decision rows, and progressive drill-down. Tables should get the width they need. Keep headings short and sentence-case. Use monospace for codes, timestamps, state, and tabular values rather than as a visual theme.

Colour is semantic. Muted red can mark closed authority or a blocker, amber can mark a prepared or watch state, and neutral text can carry ordinary information. Green is reserved for a verified positive state; it should not be the product brand. Avoid gradients, glow, glass effects, oversized slogans, decorative cards, rounded-pill overload, fake terminals, and screenshot galleries used as page decoration.

The public and founder systems are separate. The public build contains sanitized fixtures and public material only. Founder records, authenticated API state, credentials, protected evidence, and private runtime state do not belong in it.

Accessibility is part of the layout. Keep the skip link, labelled navigation, visible keyboard focus, reduced-motion handling, readable small type, and mobile reflow. Density is useful only while hierarchy remains obvious.

When the current layout becomes too dense, choose between three options rather than adding more cards: collapse supplementary rows, move detail to an existing dedicated route, or split public review and founder workflow information more sharply. The least decorative option that preserves the decision hierarchy wins.

Tests should protect facts and boundaries rather than exact copy. `Mission 104` remaining not authorized, the absence of private markers, the static-output policy, and anonymous denial at Founder Gateway surfaces are the durable requirements.
