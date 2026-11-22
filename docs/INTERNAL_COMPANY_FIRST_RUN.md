# Shortest *authorized* company-side qualification

**Never run this external bootstrap against actual company production systems.** This is a future operator procedure that the developed product must make executable; the included `python -m fabintel preflight` is explicitly synthetic and reports PENDING.

Target intended internal flow:
1. Obtain company approval for transfer; verify archive checksum, scanner reports and approved target OS architecture.
2. Transfer only reviewed source + binaries/dependencies/manifest through an authorized process. No external outbound connections, cloud models, or shipping real company data back out.
3. Install fully offline on the qualified OS using documented install/test commands. Select approved local/intranet model endpoint and authentication references without embedding credentials.
4. Use the approved site-side bridge to capture discovered logical capabilities, exact discovered tool names/versions, permissions, semantics, relationships, and qualification outcomes into `release/INTERNAL_QUALIFICATION_REPORT_TEMPLATE.json` format. The template names only the frozen logical operations; it does not guess company tool names or endpoints. Run `python -m fabintel qualify-internal --capture <site-capture.json>` to enumerate gaps. The runner validates evidence shape and never declares internal readiness from a file alone.
5. Perform a small authorized read-only true-data pilot with an engineer. Reject real conclusions if source semantics, geometry, constraints, statistics or history are unverified.
6. Publish only the passed scope and actual residual caveats; obtain authorized security/owner and engineering approval before production use.

Company-specific endpoint names, permissions, OS, deployment host, authenticators, models, accepted source definitions and ROI baselines **cannot be established from this ZIP**. The internal preflight must discover them there, never invent them externally. `qualify-internal` reports `PENDING_INTERNAL` even when all capture checks look complete; authorized owners still review the actual evidence and conduct the first real engineer investigation. No claim of zero-minute or guaranteed immediate production is defensible.
