# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import json
from genlayer import *

# ── AI Content Policy Enforcer ────────────────────────────────────────────────
#
# PURPOSE:
#   A moderated content primitive for on-chain communities. A policy owner
#   defines rules in plain English. Anyone submits content for review.
#   Validators evaluate the content against the policy using
#   prompt_non_comparative — and approve or reject it. No human moderator,
#   no centralized moderation team, no single point of censorship.
#
# CONSENSUS DESIGN:
#   review() uses prompt_non_comparative, NOT strict_eq.
#   This is intentional. Two validators evaluating "does this post contain
#   spam or hate speech" may phrase their reasoning differently but still
#   reach the same APPROVED/REJECTED conclusion. prompt_non_comparative
#   checks whether the output meets the criteria (valid verdict + reasoning)
#   rather than requiring byte-identical outputs.
#
#   The distinction from strict_eq: content moderation has inherent
#   subjectivity. Requiring exact match would cause most reviews to fail
#   because validator LLMs express judgment differently. The criteria
#   approach correctly abstracts over that variation.
#
# POLICY DESIGN:
#   Any contract owner can create a policy with custom rules. The same
#   contract supports multiple policies with different owners and rules.
#   A DAO forum, a token-gated community, and a news publishing platform
#   can all use the same contract with different policy IDs.
#
# REUSE:
#   Deploy once. Create a policy. Any app calls submit_content() and
#   review() to get moderated on-chain content without a team.
# ─────────────────────────────────────────────────────────────────────────────


class ContentPolicyEnforcer(gl.Contract):

    policy_count:    u64
    submission_count: u64
    policies:        TreeMap[str, str]   # policy_id -> JSON
    submissions:     TreeMap[str, str]   # submission_id -> JSON

    def __init__(self):
        self.policy_count     = u64(0)
        self.submission_count = u64(0)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _addr(self) -> str:
        return str(gl.message.sender_address).lower().strip()

    def _get_policy(self, pid: int) -> dict:
        raw = self.policies.get(str(pid))
        if not raw:
            raise Exception("Policy not found")
        return json.loads(raw)

    def _get_sub(self, sid: int) -> dict:
        raw = self.submissions.get(str(sid))
        if not raw:
            raise Exception("Submission not found")
        return json.loads(raw)

    def _save_sub(self, sid: int, s: dict):
        self.submissions[str(sid)] = json.dumps(s)

    # ── Read ──────────────────────────────────────────────────────────────────

    @gl.public.view
    def get_policy(self, policy_id: int) -> str:
        return json.dumps(self._get_policy(policy_id))

    @gl.public.view
    def get_submission(self, submission_id: int) -> str:
        return json.dumps(self._get_sub(submission_id))

    @gl.public.view
    def get_policy_count(self) -> str:
        return str(int(self.policy_count))

    @gl.public.view
    def get_submission_count(self) -> str:
        return str(int(self.submission_count))

    @gl.public.view
    def is_approved(self, submission_id: int) -> str:
        """
        Simple boolean check for other contracts to query.
        Returns JSON: {approved: bool}
        """
        s = self._get_sub(submission_id)
        return json.dumps({"approved": s.get("status") == "APPROVED"})

    # ── Write ─────────────────────────────────────────────────────────────────

    @gl.public.write
    def create_policy(self, name: str, rules: str, description: str):
        """
        Create a new content policy. The rules field is plain English —
        describe what content is and isn't allowed.

        Args:
            name:        Short policy name. E.g. "DAO Forum Rules"
            rules:       Full policy text. Be specific. Example:
                         "Content must be relevant to DeFi or Web3.
                          No spam, no hate speech, no personal attacks.
                          No financial advice without disclaimer.
                          Posts must be in English and at least 50 words."
            description: One-line summary shown to submitters

        The caller becomes the policy owner and can update rules later.
        """
        caller = self._addr()
        if len(name.strip()) < 3:
            raise Exception("Policy name too short")
        if len(rules.strip()) < 30:
            raise Exception("Rules too short — be specific about what is and isn't allowed")

        pid = int(self.policy_count)
        self.policies[str(pid)] = json.dumps({
            "id":          pid,
            "owner":       caller,
            "name":        name.strip(),
            "rules":       rules.strip(),
            "description": description.strip(),
            "active":      True,
        })
        self.policy_count = u64(pid + 1)

    @gl.public.write
    def update_policy_rules(self, policy_id: int, new_rules: str):
        """Policy owner can update the rules. Active submissions are not affected."""
        caller = self._addr()
        p      = self._get_policy(policy_id)
        if caller != p["owner"]:
            raise Exception("Only the policy owner can update rules")
        p["rules"] = new_rules.strip()
        self.policies[str(policy_id)] = json.dumps(p)

    @gl.public.write
    def submit_content(self, policy_id: int, content: str, content_url: str):
        """
        Submit content for review against a policy.

        Args:
            policy_id:   Which policy to evaluate against
            content:     The actual content text to review
            content_url: Optional URL where the full content lives
                         (validators can fetch it for additional context)

        Submission is stored as PENDING until review() is called.
        """
        caller  = self._addr()
        p       = self._get_policy(policy_id)
        if not p.get("active"):
            raise Exception("Policy is not active")
        if len(content.strip()) < 5:
            raise Exception("Content too short")

        sid = int(self.submission_count)
        self._save_sub(sid, {
            "id":          sid,
            "policy_id":   policy_id,
            "submitter":   caller,
            "content":     content.strip(),
            "content_url": content_url.strip(),
            "status":      "PENDING",
            "verdict":     "",
            "reasoning":   "",
        })
        self.submission_count = u64(sid + 1)

    @gl.public.write
    def review(self, submission_id: int):
        """
        Trigger AI policy review for a pending submission.
        Anyone can call this — review is permissionless.

        CONSENSUS: prompt_non_comparative
        Validators independently evaluate whether the content meets the policy.
        They do NOT need to produce identical reasoning — they need to produce
        a valid APPROVED or REJECTED verdict that is consistent with the policy
        criteria. Two validators may phrase their reasoning differently but
        still agree on the verdict. prompt_non_comparative handles this
        correctly; strict_eq would cause most reviews to fail due to natural
        variation in LLM reasoning text.
        """
        s = self._get_sub(submission_id)
        if s["status"] != "PENDING":
            raise Exception("Submission is not pending review")

        p       = self._get_policy(s["policy_id"])
        rules   = p["rules"]
        content = s["content"]
        c_url   = s["content_url"]

        extra_context = ""
        if c_url:
            try:
                resp          = gl.nondet.web.get(c_url)
                extra_context = "\nFULL CONTENT (from " + c_url + "):\n" + resp.body.decode("utf-8", "replace")[:3000]
            except Exception:
                extra_context = ""

        policy_name = p["name"]
        full_content = content
        ec = extra_context

        review_prompt = (
            "You are a content moderator enforcing the policy: " + policy_name + "\n\n"
            "POLICY RULES:\n" + rules + "\n\n"
            "CONTENT TO REVIEW:\n" + full_content
            + ec + "\n\n"
            "Does this content comply with the policy rules above?\n"
            "Respond with a JSON object containing:\n"
            "- verdict: either \"APPROVED\" or \"REJECTED\"\n"
            "- reasoning: one sentence explaining your decision\n"
            "Format: {\"verdict\": \"APPROVED\", \"reasoning\": \"...\"}\n"
            "No markdown, no extra text."
        )

        def evaluate() -> str:
            result = str(gl.nondet.exec_prompt(review_prompt)).strip()
            try:
                parsed  = json.loads(result)
                verdict = str(parsed.get("verdict", "")).upper()
                reason  = str(parsed.get("reasoning", ""))
                if verdict not in ("APPROVED", "REJECTED"):
                    return json.dumps({"verdict": "REJECTED", "reasoning": "Could not parse verdict"})
                return json.dumps({"verdict": verdict, "reasoning": reason})
            except Exception:
                if "APPROVED" in result.upper():
                    return json.dumps({"verdict": "APPROVED", "reasoning": result[:200]})
                return json.dumps({"verdict": "REJECTED", "reasoning": result[:200]})

        # prompt_non_comparative: validators check that output is a valid
        # APPROVED/REJECTED verdict consistent with the policy criteria.
        # They do NOT need to produce identical reasoning text.
        raw = gl.eq_principle.prompt_non_comparative(
            evaluate,
            task="Evaluate content against the policy and return a valid verdict.",
            criteria=(
                "Accept if the response is valid JSON with 'verdict' set to "
                "either 'APPROVED' or 'REJECTED' and 'reasoning' as a non-empty string. "
                "The verdict must be consistent with the policy rules provided."
            ),
        )

        result_data = {"verdict": "REJECTED", "reasoning": ""}
        try:
            parsed = json.loads(str(raw))
            result_data = {
                "verdict":   str(parsed.get("verdict", "REJECTED")).upper(),
                "reasoning": str(parsed.get("reasoning", "")),
            }
        except Exception:
            pass

        s["status"]    = result_data["verdict"]
        s["verdict"]   = result_data["verdict"]
        s["reasoning"] = result_data["reasoning"]
        self._save_sub(submission_id, s)
