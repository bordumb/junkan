
# Example Repository

In this walkthrough, we will spin up a simulated **Payment Service** stack that includes:
- **Python** application code
- **Terraform** infrastructure definitions
- **Kubernetes** manifests

You will see how `jnkn` stitches these disparate files together into a single dependency graph.

## 1. Setup the Demo

You don't need to clone anything. Jnkn includes a built-in demo generator.

Create a temporary directory and initialize the demo:

```bash
mkdir try-jnkn
cd try-jnkn

# This downloads the example structure and configures Jnkn
jnkn init --demo
````

You should see:

```text
📂 Created demo project at: .../try-jnkn/jnkn-demo
✨ Initialized successfully!
```

Navigate into the generated project:

```bash
cd jnkn-demo
```

## 2\. The Architecture

Before we scan, let's look at the "trap" waiting in this codebase.

1.  **The Code (`src/app.py`):**
    The Python app crashes if it can't connect to the database. It expects an environment variable named `PAYMENT_DB_HOST`.

    ```python
    DB_HOST = os.getenv("PAYMENT_DB_HOST")
    ```

2.  **The Infrastructure (`terraform/main.tf`):**
    Terraform provisions an RDS instance and outputs its address as `payment_db_host`.

    ```hcl
    output "payment_db_host" {
      value = aws_db_instance.payment_db.address
    }
    ```

3.  **The Glue (`k8s/deployment.yaml`):**
    Kubernetes injects the secret into the container.

    ```yaml
    - name: PAYMENT_DB_HOST
      valueFrom:
        secretKeyRef:
          name: db-secrets
          key: host
    ```

**The Problem:** There are no explicit imports connecting Terraform to Python. If you rename the Terraform output, `terraform plan` will pass, but the Python app will crash in production.

## 3\. Run the Scan

Let's see if Jnkn can find these hidden connections.

```bash
jnkn scan
```

Output:

```text
🔍 Scanning .../try-jnkn/jnkn-demo
   Parsers loaded: python, terraform, kubernetes
   Files found: 3
✅ Scan complete
   Nodes: 7
   Edges: 7
   Saved: .jnkn/lineage.json
```

Jnkn has parsed the files, tokenized the variable names (e.g., `PAYMENT_DB_HOST` → `[payment, db, host]`), and stitched them together based on matching patterns.

## 4\. Analyze Blast Radius

Now, imagine you are the Infrastructure Engineer. You want to refactor the Terraform code.

**Question:** "What happens if I change the `payment_db_host` output?"

Run a blast radius check:

```bash
jnkn blast infra:output.payment_db_host
```

You will see exactly what breaks downstream:

```text
💥 Blast Radius Analysis
════════════════════════
Source: infra:output.payment_db_host

☸️  Kubernetes (1)
  • k8s:default/deployment/payment-service

🐍 Python Code (1)
  • src/app.py (Confidence: High)
```

**Result:** You instantly see that changing Terraform impacts both the Kubernetes deployment configuration and the Python application code.

## 5\. Visualize the Graph

For a high-level view of your architecture, generate an interactive HTML graph.

```bash
jnkn graph --output my-stack.html
```

Open `my-stack.html` in your browser:

1.  **Zoom in** to see the nodes.
2.  **Click** on `infra:aws_db_instance.payment_db`.
3.  Follow the arrows to see how data flows from **Infrastructure** → **Config** → **Code**.

This visual proof is excellent for explaining architectural dependencies to new team members or during architectural reviews.

## 6\. Cleanup

When you are done, simply remove the directory:

```bash
cd ..
rm -rf jnkn-demo
```

## Next Steps

Now that you've seen it work in a perfect environment, try it on your real code.

[:octicons-arrow-right-24: Scan your own repository](https://www.google.com/search?q=scan-monorepo.md)
