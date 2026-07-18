# DeltaGrid documentation style

## Purpose

This standard keeps DeltaGrid documentation clear, protects historical and
research integrity, and prevents writing from implying authority that the
project does not have.

Use it for new documentation, status banners, companion summaries, operator
guidance, and user-visible software output.

## Choose the correct document type

Choose one primary reader need before writing:

- **Overview** — orient a new reader and link to deeper material.
- **Explanation** — describe why the system or a decision works as it does.
- **How-to guide** — help a reader complete a specific verified task.
- **Technical reference** — state exact interfaces, fields, commands, or rules.
- **Historical record** — preserve what happened and was decided earlier.
- **Evidence record** — preserve deterministic results, identities, and facts.
- **Future design** — describe a possibility that is not current authority.

Do not mix an operator procedure, public overview, historical log, and future
proposal into one document unless the boundaries are unmistakable.

## State document status

Every new human-facing document must say near the beginning whether it is:

- current;
- historical;
- superseded;
- design-only; or
- evidence.

Current documents should name the authority they support. Superseded documents
should point to their replacement. Design-only documents must say that they do
not prove implementation or grant authorization.

## Write for humans

- Begin with what the component or document is for.
- Use active voice and short paragraphs.
- Prefer ordinary words over internal programme language.
- Explain why an important control exists, not only its code or threshold.
- Put a human description before a machine status code.
- Define technical terms that the intended reader may not know.
- Use descriptive headings that help readers scan the page.
- Link to evidence instead of copying large evidence blocks.
- Separate present status from history and future possibilities.

## Preserve machine precision

- Do not humanize or reformat hashes, protocol IDs, access counters, checksum
  manifests, or raw contract values.
- Retain raw status codes in contracts, evidence, logs, and machine output.
- Add a human explanation around a machine value when people need to read it.
- Never alter evidence merely to improve style.
- Never replace a deterministic source record with its prose summary.

## Avoid generated-looking prose

Avoid:

- repeating the same safety paragraph in every section;
- using mission-style templates for ordinary changes;
- inflated labels such as *institutional*, *executive*, *intelligence*,
  *governance board*, *control plane*, or *autonomous* unless necessary;
- invented completion percentages;
- repetitive “inputs, outputs, safety boundary, next mission” sections;
- claiming a design exists because a document describes it;
- copying the complete project status into every file;
- adding headings or lists that do not help a reader make a decision.

State shared safety and project status once, then link to the controlling
document where repetition would add noise.

## Claims and authorization

Documentation must never imply these claims without controlling evidence:

- validated alpha or profitability;
- production readiness;
- paper-trading authorization;
- live-trading authorization;
- capital authorization;
- autonomous operation;
- guaranteed future performance.

The existence of code, tests, a roadmap, or a design is not authorization to use
it. Passing tests proves the tested software properties, not an economic edge.

## Historical records

Preserve the body text of historical records. Earlier status, next-action, and
authorization statements are part of the decision lineage even when later work
has superseded them.

A future banner or companion summary may clarify the present status, identify a
replacement, or route readers to the final freeze. It must not silently rewrite
the historical result, metric, protocol, hash, access count, or decision.

## Internal machine statuses

Machine:

`ALPHA_SEARCH_B_REJECTED_DEVELOPMENT`

Human:

“Rejected during development testing.”

Both can coexist. Use the exact code at machine boundaries and plain language in
ordinary prose, with a link or advanced-details section when the mapping matters.

## Review checklist

Before publishing, confirm that:

1. The intended reader and document type are clear.
2. The current, historical, superseded, design-only, or evidence status is clear.
3. Present claims match the final freeze and controlling records.
4. No wording implies paper, live, capital, ML, or autonomous authorization.
5. Human descriptions precede unavoidable machine codes.
6. Historical bodies, hashes, counters, and evidence remain unchanged.
7. Important controls include a concise reason.
8. Repeated boilerplate has been removed or linked once.
9. Relative links resolve and commands are verified for their stated scope.
10. The document says no more than its evidence supports.
