# Workflow diagrams

The illustrations use a minimal documentation style: white backgrounds, restrained blue accents, thin connectors, short labels, and generous whitespace. Each summarizes one relationship rather than putting every skill and gate into a dense graph.

| Diagram | Relationship | Editable source |
| --- | --- | --- |
| Investigation workflow | Target intake, independent analysis, experiments, feedback, scaling, and validation | [Mermaid](investigation-workflow.mmd) |
| Test-time scaling and RSA | Left-to-right flow with plain labels for continuing an idea, combining ideas, new exploration, tests, and feedback | [Mermaid](test-time-scaling-rsa.mmd) |
| Candidate expansion | Four automatically allocated extension/refutation perspectives | [Mermaid](candidate-expansion.mmd) |

The `.mmd` files preserve graph topology. The editable SVG originals and PNG mirrors live in [docs/images](../images/). The README embeds PNG files with repository-relative paths, including in offline downloads.

Regenerate the vector figures with Python 3.11+:

```bash
python3 docs/diagrams/render_diagrams.py
```

If CairoSVG is installed (`python3 -m pip install cairosvg`), the same command renders PNG mirrors. No external image, font service, or network resource is used by the renderer. Diagram rendering dependencies are separate from the A1X runtime.

## Scope

- The first pass has four perspectives: value/numerical, authority/trust, lifecycle/composition, and adversarial refutation.
- Earlier analysis can be revisited after any experiment.
- K counts parent handoffs. Closure uses one; pairwise RSA uses two. Fresh lanes receive independent questions.
- Compatibility is a question to test. Incompatible parents remain separate.
- Evidence assessment is not an independent semantic oracle. See [limitations](../research-and-limitations.md).
- Candidate expansion and campaign completion are explained in the README and dedicated source graph; the overview stays compact.

The final assets use explicit vector geometry and text so labels and arrow directions remain reviewable. The renderer is separate from the A1X runtime and does not affect investigation behavior.
