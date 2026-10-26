"""Human approval gate: review the exact version and record a decision."""

from __future__ import annotations

import html

import streamlit as st

from ..approvals import ApprovalError, record_decision
from ..models import HumanDecision, TaskStatus
from . import common, components, layout


def _decision_labels(version: int) -> dict[str, str]:
    return {
        HumanDecision.APPROVE.value: f"Approve version {version}",
        HumanDecision.REJECT.value: f"Reject version {version} (terminal)",
        HumanDecision.REQUEST_REVISION.value: f"Request a bounded revision of version {version}",
    }


def _action_label(decision: str | None, version: int) -> str:
    if decision == HumanDecision.APPROVE.value:
        return f"Approve version {version}"
    if decision == HumanDecision.REJECT.value:
        return f"Reject version {version}"
    if decision == HumanDecision.REQUEST_REVISION.value:
        return f"Request revision of version {version}"
    return "Choose a decision"


def _pick_task(services):
    task = common.active_task(services.db)
    if task is not None:
        return task
    pending = services.db.pending_approval_tasks(limit=20)
    if not pending:
        return None
    task = pending[0]
    st.session_state["active_task_id"] = task.id
    return task


def _payload_from_state(state: dict) -> dict:
    return {
        "request": state.get("request", ""),
        "draft": state.get("draft", ""),
        "claims": state.get("claims", []),
        "evidence": state.get("evidence", []),
        "policy_report": state.get("policy_report") or {},
        "review_result": state.get("review_result") or {},
        "version_id": state.get("current_version_id"),
        "version_number": state.get("draft_version", 0),
        "content_hash": state.get("current_content_hash"),
        "simulated": bool(state.get("simulated", True)),
        "revision_count": int(state.get("revision_count", 0)),
        "max_revisions": int(state.get("max_revisions", 2)),
    }


def _pill(text: str, tone: str, icon: str = "completed") -> str:
    return components.badge(icon, text=text, tone=tone)


def _checks_html(payload: dict) -> str:
    policy = payload["policy_report"]
    review = payload["review_result"]
    claims = payload["claims"]
    unverified = [claim for claim in claims if claim.get("status") == "unverified"]
    findings = policy.get("findings") or []
    pii = [
        finding
        for finding in findings
        if "pii" in str(finding.get("rule_id", "")).lower()
        or "personal" in str(finding.get("message", "")).lower()
    ]
    pills = [
        _pill("Policy checks passed", "active") if policy.get("passed") else _pill("Policy checks need attention", "review", "alert"),
        _pill("No personal data flagged", "active") if not pii else _pill("Personal data flagged", "blocked", "alert"),
    ]
    if unverified:
        pills.append(_pill(f"{len(unverified)} unverified claim(s)", "blocked", "alert"))
    else:
        pills.append(_pill("Every claim has a source or label", "active"))
    verdict = str(review.get("decision") or "not run").replace("_", " ").title()
    pills.append(_pill(f"Reviewer: {verdict}", "active" if review.get("decision") == "pass" else "review", "eye"))
    return f'<div class="ag-check-pills">{"".join(pills)}</div>'


def _evidence_html(db, task_id: str) -> str:
    rows = db.list_evidence(task_id)
    if not rows:
        return '<div class="ag-note">No evidence rows were stored. Unverified claims are labelled in the draft.</div>'
    items = []
    for index, row in enumerate(rows, start=1):
        filename = html.escape(str(row.get("filename") or "No source found"))
        location = html.escape(str(row.get("location") or ""))
        excerpt = html.escape(str(row.get("excerpt") or ""))[:220]
        items.append(
            f'<div class="ag-evidence__item"><div class="ag-evidence__ref">S{index}</div>'
            f"<div><strong>{filename}</strong><br>{location}"
            f'<div class="ag-note">{excerpt}</div></div></div>'
        )
    return f'<div class="ag-evidence">{"".join(items)}</div>'


def _history_note(db, task_id: str) -> str:
    versions = db.list_output_versions(task_id)
    reviews = db.list_human_reviews(task_id)
    if not versions and not reviews:
        return ""
    labels = [f"v{item.version_number} {item.source.value}" for item in versions]
    for review in reviews:
        labels.append(f"{review.decision.value} by {review.reviewer}")
    return "History: " + " · ".join(labels[-4:])


def _render_technical(payload: dict, db, task_id: str) -> None:
    with st.expander("Version fingerprint and technical checks"):
        st.text_input(
            "Content hash (bound to any approval)",
            payload["content_hash"] or "",
            disabled=True,
        )
        st.caption("This fingerprint protects the exact draft you are reviewing.")
        st.caption(f"Revisions used: {payload['revision_count']} / {payload['max_revisions']}")
        claims = payload["claims"]
        if claims:
            st.dataframe(
                [
                    {
                        "Status": claim.get("status"),
                        "Claim": claim.get("text"),
                        "Source": claim.get("source_ref"),
                        "Rationale": claim.get("rationale", ""),
                    }
                    for claim in claims
                ],
                width="stretch",
                hide_index=True,
            )
        findings = payload["policy_report"].get("findings") or []
        if findings:
            st.dataframe(
                [
                    {
                        "Rule": finding.get("rule_id"),
                        "Severity": finding.get("severity"),
                        "Message": finding.get("message"),
                        "Location": finding.get("location"),
                    }
                    for finding in findings
                ],
                width="stretch",
                hide_index=True,
            )
        reviews = db.list_human_reviews(task_id)
        if reviews:
            st.dataframe(
                [
                    {
                        "Time": review.created_at,
                        "Decision": review.decision.value,
                        "Reviewer": review.reviewer,
                        "Feedback": review.feedback,
                    }
                    for review in reviews
                ],
                width="stretch",
                hide_index=True,
            )


def _render_decision_form(services, task, payload: dict) -> None:
    version = payload["version_number"]
    labels = _decision_labels(version)
    with st.container(border=True, key="ag-decision-form"):
        st.markdown('<div class="ag-card-title">Your decision</div>', unsafe_allow_html=True)
        st.caption("Approval applies only to this version and its content hash.")
        reviewer = st.text_input(
            "Reviewer name",
            value=st.session_state.get("reviewer_name", "Local Reviewer"),
        )
        decision = st.radio(
            "Decision",
            list(labels.keys()),
            format_func=lambda value: labels[value],
            index=None,
            key=f"decision_{task.id}",
        )
        consequences = {
            HumanDecision.APPROVE.value: (
                "Finalizes this exact version and unlocks the approved Markdown/TXT export."
            ),
            HumanDecision.REJECT.value: (
                "Terminal. The task closes and approved export stays blocked."
            ),
            HumanDecision.REQUEST_REVISION.value: (
                "Returns the work with your feedback; the revision budget is limited."
            ),
        }
        if decision in consequences:
            st.caption(consequences[decision])
        feedback = ""
        revision_target = "drafting"
        if decision in {HumanDecision.REJECT.value, HumanDecision.REQUEST_REVISION.value}:
            feedback = st.text_area(
                "Feedback (optional for a rejection; required for a revision)",
                height=100,
                key=f"feedback_{task.id}",
            )
        if decision == HumanDecision.REQUEST_REVISION.value:
            revision_target = st.selectbox(
                "Revision target",
                ["drafting", "analysis"],
                help="Choose analysis to re-extract and re-verify claims, not just rewrite.",
                key=f"revision_target_{task.id}",
            )
        acknowledged = st.checkbox(
            f"I reviewed version {version} and the content hash shown above.",
            key=f"ack_{task.id}",
        )
        reject_confirmed = False
        if decision == HumanDecision.REJECT.value:
            reject_confirmed = st.checkbox(
                f"I understand rejecting version {version} is terminal and cannot be undone.",
                key=f"reject_confirm_{task.id}",
            )
        submitted = st.button(
            _action_label(decision, version),
            type="primary",
            width="stretch",
            disabled=decision is None,
        )
        note = _history_note(services.db, task.id)
        if note:
            st.markdown(f'<div class="ag-note">{html.escape(note)}</div>', unsafe_allow_html=True)

    if not submitted:
        return
    if not reviewer.strip():
        st.error("A reviewer name is required.")
        return
    if not acknowledged:
        st.error("Please confirm that you reviewed the exact version and hash.")
        return
    if decision == HumanDecision.REJECT.value and not reject_confirmed:
        st.error("Please confirm that rejection is terminal before rejecting this version.")
        return
    if decision == HumanDecision.REQUEST_REVISION.value and not feedback.strip():
        st.error("Revision feedback is required.")
        return

    st.session_state["reviewer_name"] = reviewer.strip()
    try:
        record = record_decision(
            services.db,
            task.id,
            payload["version_id"],
            decision,
            reviewer.strip(),
            feedback=feedback,
            actor="human:streamlit",
            max_revisions=payload["max_revisions"],
        )
    except ApprovalError as exc:
        st.error(f"Decision refused: {exc}")
        return

    resume_payload = {
        "decision": decision,
        "reviewer": reviewer.strip(),
        "feedback": feedback,
    }
    if decision == HumanDecision.REQUEST_REVISION.value:
        resume_payload["revision_target"] = revision_target

    try:
        result = services.workflow.resume(task.id, resume_payload)
    except Exception as exc:
        st.error(
            f"Decision recorded as {record.decision.value}, but the graph could not resume: "
            f"{type(exc).__name__}: {exc}"
        )
        return

    if decision == HumanDecision.APPROVE.value and result.status == "completed":
        common.set_flash(
            f"Approved version {payload['version_number']} and finalized the task.", "success"
        )
        common.navigate("Workflow")
    elif decision == HumanDecision.REJECT.value:
        common.set_flash("Task rejected. Rejected output cannot be exported.", "warning")
        common.navigate("Workflow")
    elif result.interrupted:
        common.set_flash(
            "Revision requested. A new output version is ready for review.", "warning"
        )
        common.navigate("Review")
    else:
        common.set_flash(
            f"Revision requested, but the workflow stopped with status '{result.status}'.",
            "error",
        )
        common.navigate("Workflow")


def render(services) -> None:
    db = services.db
    workflow = services.workflow
    task = _pick_task(services)
    if task is None:
        layout.page_header("Review", "Check the draft, then approve, reject, or request changes.")
        st.info("No task is waiting for human review.")
        if st.button("Create a task", type="primary"):
            common.navigate("New Task")
        return

    interrupted = workflow.is_interrupted(task.id)
    state = workflow.get_state(task.id)
    payload = _payload_from_state(state)
    title = f"Review · {common.display_id(task.id)}"
    subtitle = f"Version {payload['version_number']} · {common.short_hash(payload['content_hash'])}"
    layout.page_header(title, subtitle, right=lambda: components.render_badge(task.status))

    if not interrupted or task.status != TaskStatus.AWAITING_HUMAN_REVIEW:
        if task.status in {TaskStatus.APPROVED, TaskStatus.COMPLETED}:
            st.success("This task has been approved. Approved exports are available in History.")
            if st.button("Open History", type="primary"):
                common.navigate("History")
        elif task.status == TaskStatus.AWAITING_HUMAN_REVIEW:
            st.warning(
                "The task is awaiting review, but no saved review step was found. "
                "Open Workflow to see what happened.",
                icon=":material/warning:",
            )
        else:
            st.info("This task is not currently awaiting a human decision.")
        return

    if not payload["version_id"] or not payload["content_hash"] or not payload["draft"].strip():
        st.error("The interrupted state does not contain a complete versioned draft.")
        return

    left, right = st.columns([2.1, 1], gap="large")
    with left:
        with st.container(border=True, key="ag-card-draft"):
            st.markdown('<div class="ag-card-title">Draft (read-only)</div>', unsafe_allow_html=True)
            st.text_area(
                "Draft",
                payload["draft"],
                height=480,
                disabled=True,
                label_visibility="collapsed",
            )
            st.markdown(
                '<div class="ag-note">Read-only in this prototype. Editing would create a new '
                "version and require fresh approval. The draft may contain personal data from "
                "the uploaded files.</div>",
                unsafe_allow_html=True,
            )
        with st.container(border=True, key="ag-card-checks"):
            st.markdown(
                '<div class="ag-card-title">Reviewer and policy checks</div>',
                unsafe_allow_html=True,
            )
            st.markdown(_checks_html(payload), unsafe_allow_html=True)
            reasons = (payload["review_result"].get("reasons") or [])[:3]
            for reason in reasons:
                st.markdown(f"- {reason}")
            st.caption("These are agent checks, not a human approval.")
    with right:
        with st.container(border=True, key="ag-card-evidence"):
            st.markdown('<div class="ag-card-title">Evidence</div>', unsafe_allow_html=True)
            st.markdown(_evidence_html(db, task.id), unsafe_allow_html=True)
            st.markdown(
                '<div class="ag-note">Each claim is linked to a source or labelled unverified.</div>',
                unsafe_allow_html=True,
            )
        _render_decision_form(services, task, payload)
        _render_technical(payload, db, task.id)
