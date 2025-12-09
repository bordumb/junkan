# About Junkan (`jnkn`)

## The Name

**Junkan** (循環, じゅんかん, jun-kan) is Japanese for "circulation" or "cycle."

For the ergonomics of CLI typing, I opted to shorten this to `jnkn`.

In Japanese, you can have:

- **好循環** (kō-junkan) — a virtuous cycle
- **悪循環** (aku-junkan) — a vicious cycle

That's exactly what cross-domain dependencies create. 

When everything is connected but nothing is tracked, you get a vicious cycle: change something, break something else, scramble to fix it, break a third thing. Repeat at 3am.

Junkan breaks that cycle by going around your entire infrastructure — Python, Terraform, Kubernetes, dbt — and showing you the connections before they become incidents.

**jnkn** is just the shorthand. Easier to type, fits nicely in a CLI.

## The Philosophy

Most tools check their own domain:

- Terraform validates Terraform
- pytest tests Python
- dbt tests dbt

Nobody checks the seams. The gaps between domains are where production breaks hide.

Junkan's job is to trace the circle — follow a variable from your Python config, through your Terraform outputs, into your Kubernetes secrets, and back. If renaming one thing ripples across your stack, you should know *before* you merge.

## The Goal

Turn 悪循環 into 好循環.

Instead of: *change → deploy → break → page → fix → repeat*

You get: *change → analyze → fix → deploy → sleep*

That's the cycle we're optimizing for.