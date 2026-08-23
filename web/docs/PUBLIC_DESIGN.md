# Public UI

The public site is a read-only window into DeltaGrid. It should feel closer to an internal research tool than a product launch page.

The useful things to show are the things that are actually true: current research status, configured coverage, provider limits, authority state, and a few sanitized workspace views. If a number would only be there to make the page look more impressive, leave it out. We do not publish invented P&L, Sharpe ratios, positions, AUM, "AI confidence", or pretend that research software has trading authority.

Keep the layout plain. Tables and short status rows are preferred to feature cards. Monospace is useful for codes, timestamps, and state; it should not take over the whole page. Colour should identify state or focus, not decorate empty space. Avoid giant slogans, glow effects, gradients, fake terminals, and repeated badges saying the same thing.

The public and founder systems are separate. The public build contains sanitized fixtures and public material only. Founder records, authenticated API state, credentials, protected evidence, and private runtime state do not belong in it.

Accessibility is part of the layout, not a separate pass at the end. Keep the skip link, labelled navigation, visible keyboard focus, and reduced-motion handling. A dense interface still has to be usable.

Tests should protect facts and boundaries rather than wording. Copy can change. `Mission 104` remaining not authorized, the absence of private markers, the static-output policy, and anonymous denial at Founder Gateway surfaces are the things that matter.
