# Frontend Contract

Apply this contract to every user-visible web interface. Set `frontend.applicable` to `false` only when the approved output has no UI.

## Required behavior

Represent `loading`, `empty`, `error`, and `success` explicitly when the interface waits on or renders variable data. A state may be documented as unreachable only with a concrete architecture reason; do not silently omit it.

Preserve user input through recoverable errors where safe. Prevent duplicate submissions while a mutation is pending. Error copy should state what happened, what the user can do, and must not expose stack traces, secrets, internal IDs, or provider payloads.

## Accessibility

At acceptance, verify at least:

- keyboard reachability and activation order;
- visible focus and sensible focus movement after navigation, dialogs, and errors;
- programmatic labels, names, roles, and error associations;
- color contrast and non-color status cues.

Use native HTML semantics before custom ARIA. Record actual checks in `frontend.accessibility_checks`; package installation or component-library claims are not evidence.

## Responsive behavior

Verify representative small, medium, and large viewports unless the source handoff limits supported devices. Avoid horizontal overflow, clipped controls, unreadable line lengths, and interactions available only through hover. Record the checked viewport classes in `frontend.responsive_checks`.

## Visual authority

Follow an existing design system when present. Otherwise derive only the minimum layout and tokens needed to satisfy the handoff. Aesthetic preference must not rewrite locked product behavior. Screenshots can support visual acceptance but do not replace interaction, accessibility, or error-state checks.
