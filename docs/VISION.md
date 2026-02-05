# Vision — The Trust Layer for Autonomous Systems

*Why signed action schemas are the foundation of safe multi-agent coordination.*

---

## The Core Insight

The Action-Registry appears to solve a simple problem: "where do I find the schema for `ssh.exec@2.0.0`?" But the real problem it solves is deeper: **how do autonomous agents trust each other's capabilities without human intermediation?**

In a world of single agents, trust is implicit. The developer configures the tools, the agent uses them. But in a swarm — where agents discover, compose, and invoke each other's capabilities at runtime — trust must be explicit, verifiable, and auditable. The Action-Registry is where that trust lives.

The signature is not a security feature bolted on top. It *is* the product. Without it, the registry is just a JSON store. With it, every action becomes a **signed promise**: "this is exactly what this capability does, and this key vouches for it." That promise is what makes autonomous composition safe.

---

## From Registry to Nervous System

Consider what happens as the system grows:

**Stage 1 — Lookup Table** (where we are now)
An agent needs `files.move@1.1.0`. It queries the registry. Gets the schema. Verifies the signature. Wires it in. This is useful but static — the agent already knew what it needed.

**Stage 2 — Discovery Bus**
An agent needs to "move a file" but doesn't know which action to use. It searches the registry by capability, finds `files.move`, `files.copy`, and `fs.relocate`, compares their schemas, selects the best fit. The registry is now guiding tool selection.

**Stage 3 — Negotiation Protocol**
Agent A needs log analysis done. It doesn't have that capability. It queries the registry and discovers that Agent B has published `analyze.logs@1.0.0` and is online. Agent A invokes Agent B using the schema contract. No human introduced them. The signature chain is the handshake.

**Stage 4 — Immune System**
The swarm is running 200 actions per hour across 15 agents. The registry detects that `docker.deploy@2.2.0` has a rising failure rate. It emits a deprecation warning. ACE's Cognitive Control layer picks up the signal, reroutes tasks to agents using `@2.1.0`, and flags the situation for human review. The registry didn't just serve a schema — it protected the swarm from a bad capability.

This progression — from lookup to discovery to negotiation to governance — is not speculative. Each stage follows logically from the primitives already in place: immutability, signatures, versioning, and a trust store.

---

## Why This Matters for ACE

The ACE framework models cognition as a layered nervous system: aspiration at the top, task execution at the bottom, with strategy, self-modeling, executive function, and cognitive control in between. Each layer needs a different relationship with the Action-Registry.

The **Aspirational Layer** defines what the entity *should* do. Translated to the registry: which action namespaces are ethically permissible? An ACE entity with a medical-assistance aspiration should not be invoking `offensive.exploit@1.0.0`, even if it exists in the registry and has a valid signature. The aspirational layer acts as a namespace filter.

The **Agent Model Layer** defines what the entity *can* do. This is a direct mapping to the registry: the agent's capabilities are the set of action schemas it has published and can execute. Self-knowledge is registry knowledge.

The **Task Prosecution Layer** is where actions are actually invoked. The registry's signature verification is the last gate before execution — the moment where trust is concretely enforced, not just theorized about.

The insight is that ACE's cognitive layers and the Action-Registry are not separate systems that happen to integrate. They are two views of the same thing: **the relationship between capability, trust, and intent.**

---

## Why This Matters for IntelliSwarm

A swarm without a registry is a group of agents chatting. A swarm with a registry is a coordinated system executing verified contracts.

The difference is entropy. When Agent A tells Agent B "move this file" in natural language, there's ambiguity. What format? What error handling? What happens on failure? The message is high-entropy — it contains uncertainty.

When Agent A invokes `files.move@1.1.0` with a schema that specifies `source: string, destination: string, overwrite: boolean`, verified by signature `kid: infra-deploy-1`, there is no ambiguity. The message is low-entropy — it is a contract.

The IntelliSwarm coordinator's job is to decompose high-level intent into low-entropy action invocations. The Action-Registry is what makes that possible. Without it, the coordinator has to maintain its own understanding of every agent's capabilities, keep them in sync, and hope nothing drifts. With the registry, capabilities are published, versioned, signed, and discoverable. The coordinator queries the registry, not the agents.

This is the same pattern as DNS for the internet, or a service mesh for microservices. The registry is the **capability DNS** for agent swarms.

---

## The CWOM Connection

CWOM (Canonical Work Object Model) defines the data substrate for all work: issues, runs, artifacts, constraints, doctrine. The Action-Registry is where doctrine meets execution.

An action schema is a **Doctrine Ref** — it prescribes how a specific capability works. An invocation of that action is a **Run** — it has explicit inputs (context packet, constraints) and produces **Artifacts**. The key trust state at the time of invocation is a **Constraint Snapshot**.

This means every action invocation is automatically CWOM-compliant: traceable, reproducible, and auditable. You can answer:
- Which action version was used?
- Which key signed it?
- Was it verified at invocation time?
- What constraints applied?
- What artifacts resulted?

This is the "scientific method for agentic work" that CWOM promises. The Action-Registry provides the controlled variable: the exact, immutable, signed contract that was executed.

---

## The Economics of Trust

As the swarm scales, a natural economy emerges. Not currency, but reputation.

Actions that are widely consumed, consistently verified, and correlated with successful Runs build trust scores. Actions that fail verification, cause downstream errors, or are frequently deprecated lose trust. Publishers (keys) that consistently deliver stable, well-signed actions earn reputation. Keys that are revoked or associated with bad actions lose it.

This creates a self-regulating quality signal. Agents don't need a human curator to tell them which actions are good. The execution history tells them. The registry becomes a marketplace where reputation is earned by reliability, not claimed by assertion.

The immutability rule is the foundation of this economy. If a publisher could silently change `ssh.exec@2.0.0` after agents had already consumed it, trust would be meaningless. Immutability says: once you promise, you can't take it back. A new version is a new promise. This is what makes reputation computable.

---

## The Long Arc

The longest trajectory for the Action-Registry is to become the **trust layer** for all autonomous systems in the ecosystem — not just ACE and IntelliSwarm, but any agent framework that needs to discover, verify, and invoke capabilities across organizational boundaries.

Federated registries allow organizations to publish their internal actions while consuming external ones. Signature chains span registry boundaries. An action published by Team A's registry and consumed by Team B's agent retains its full trust chain. No central authority required — just cryptography and convention.

This is the decentralized app store for agent capabilities. Except instead of humans browsing and installing, it's agents autonomously composing toolchains from verified, versioned, signed contracts. The immutability rule, the signature verification, and the trust hierarchy are the three pillars that make this possible.

From a signed JSON store to the nervous system of an autonomous cognitive entity. Every step follows from the invariants established on day one.

---

*The registry doesn't just connect agents. It governs what they're allowed to do to each other.*
