# AI Content Policy Enforcer

**Contract:** `content_policy.py`
**Network:** GenLayer Bradbury Testnet

---

## What it does

On-chain communities, DAOs, forums, publishing platforms, need content moderation. The current options are a trusted admin who can censor arbitrarily, a multisig that is slow and expensive to operate, or no moderation at all.

This contract provides a third option. A policy owner defines rules in plain English. Anyone submits content for review. GenLayer validators evaluate the content against the rules and return APPROVED or REJECTED. The result is recorded on-chain. No single moderator. No admin key. No trust required.

Multiple policies can exist in the same contract simultaneously. A DAO forum, a token-gated community, and a publishing platform can each deploy their own policy and moderate content independently, all through the same contract.

---

## How consensus works

`review()` uses `prompt_non_comparative`, not `strict_eq`.

This is the most important design decision in the contract, and it is different from the other four contracts in this suite.

Two validators evaluating "does this post contain spam or hate speech?" will reach the same APPROVED or REJECTED conclusion, but they will phrase their reasoning differently. With `strict_eq`, that variation in reasoning text would cause the transaction to fail. With `prompt_non_comparative`, validators check that the output meets the criteria structure (a valid verdict plus reasoning) rather than checking that outputs are byte-identical.

`strict_eq` would break content moderation. The verdict is what matters, not the exact words used to explain it. `prompt_non_comparative` handles this correctly by abstracting over natural variation in how validators express the same judgment.

---

## State design

```python
policy_count:     u64
submission_count: u64
policies:         TreeMap[str, str]   # policy_id -> JSON
submissions:      TreeMap[str, str]   # submission_id -> JSON
```

Policies and submissions are separate entities. A policy can have many submissions. Submissions link back to their policy ID. Status of each submission tracks through PENDING → APPROVED or REJECTED.

---

## Methods

### Write

**`create_policy(name, rules, description)`**
Creates a content policy. The caller becomes the owner.
- `name`: short label, e.g. "DAO Forum Rules"
- `rules`: full policy text in plain English. Be specific about what is and is not allowed.
- `description`: one-line summary shown to submitters

**`update_policy_rules(policy_id, new_rules)`**
Policy owner can update the rules at any time. Existing submissions are not retroactively affected.

**`submit_content(policy_id, content, content_url)`**
Submit content for review against a policy.
- `policy_id`: which policy to evaluate against
- `content`: the actual text to review
- `content_url`: optional URL to the full content if it is hosted somewhere. Validators can fetch this for additional context.

**`review(submission_id)`**
Triggers AI review. Anyone can call this, review is permissionless. Validators evaluate the content against the policy and return APPROVED or REJECTED with a one-sentence reasoning.

### Read

**`is_approved(submission_id)`**
Returns `{"approved": bool}`. Primary integration point, check this before displaying content or granting access.

**`get_submission(submission_id)`**
Full submission record including content, verdict, and reasoning.

**`get_policy(policy_id)`**
Full policy record including rules and owner.

**`get_policy_count()`** / **`get_submission_count()`**
Total policies and submissions.

---

## Writing good policies

The policy rules are what validators use to evaluate content. Vague rules produce inconsistent results.

Good:
```
Content must be relevant to DeFi or Web3.
No promotional posts, referral links, or advertisements.
No personal attacks or harassment.
Posts must be in English and contain at least 50 words of original content.
No reposting content that was already approved in the last 7 days.
```

Bad:
```
Be nice and post good stuff.
```

The more specific your rules, the more consistent the moderation. Validators are evaluating against exactly what you wrote.

---

## Flow

```
1. DAO calls create_policy("Forum Rules", "Content must be DeFi-related...", "DAO Forum")
   → policy_id = 0

2. User calls submit_content(0, "My post text here...", "https://forum.dao.com/post/123")
   → submission_id = 0, status = PENDING

3. Anyone calls review(0)
   → Validators read the policy rules
   → Validators read the content + optionally fetch the URL
   → prompt_non_comparative consensus: APPROVED or REJECTED + reasoning

4. Protocol calls is_approved(0)
   → {"approved": true} → display the content
   → {"approved": false} → hide or flag the content
```

---

## Multiple policies in one contract

The same deployed contract handles multiple independent policies:

```
Policy 0 → DAO Forum (strict, DeFi-only content)
Policy 1 → Community Newsletter (moderate, broader topics)
Policy 2 → Grant Applications (specific criteria from grant docs)
```

Each policy has its own owner and rules. Submissions reference a specific policy ID.

---

## Deploy on GenLayer Studio

Upload `content_policy.py`. No constructor arguments. Deploy once. Create as many policies as needed after deployment.
