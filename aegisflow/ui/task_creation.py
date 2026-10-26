"""New-task form: upload, validate, and launch the governed workflow."""

from __future__ import annotations

import streamlit as st

from ..document_processing import document_to_state, save_and_extract
from ..models import TaskStatus
from . import common, layout

SAMPLE_REQUEST = "Please prepare a meeting brief from the uploaded notes."


def _start(services, request: str, output_format: str, manual_minutes: float | None, uploads):
    settings = services.settings
    db = services.db
    task = db.create_task(
        request=request,
        output_format=output_format,
        simulated=settings.simulated,
        manual_minutes=manual_minutes,
    )
    files: list[dict] = []
    documents: dict[str, dict] = {}
    for upload in uploads or []:
        data = upload.getvalue()
        meta, extracted, path = save_and_extract(
            settings.upload_dir,
            task.id,
            upload.name,
            data,
            settings.max_file_mb,
        )
        db.add_file(
            task.id,
            meta.filename,
            path,
            meta.extension,
            meta.size_bytes,
            meta.sha256,
            meta.pages,
            meta.status.value,
            meta.message,
            file_id=meta.file_id,
        )
        doc = document_to_state(meta, extracted)
        documents[meta.file_id] = doc
        files.append(doc)

    try:
        result = services.workflow.start(
            task.id,
            task.request,
            task.output_format,
            files,
            documents,
            manual_minutes=task.manual_minutes,
        )
    except Exception as exc:  # defensive boundary for the UI
        try:
            db.transition_task(
                task.id,
                TaskStatus.FAILED,
                escalation_reason=f"Workflow start failed: {type(exc).__name__}",
            )
        except ValueError:
            pass
        st.error(f"Workflow could not start: {type(exc).__name__}: {exc}")
        return task

    st.session_state["active_task_id"] = task.id
    if result.interrupted:
        common.set_flash(
            "The draft is ready. Check it, then approve, reject, or request changes.",
            "warning",
        )
        common.navigate("Review")
    elif result.status in {"blocked", "failed"}:
        common.set_flash(
            "The workflow stopped before completion. Open Workflow to see what happened.",
            "error",
        )
        common.navigate("Workflow")
    else:
        common.set_flash(f"Workflow finished with status '{result.status}'.", "success")
        common.navigate("Workflow")
    return task


def _steps() -> str:
    steps = (
        ("1 Plan", "The Planner lists subtasks and the agents needed."),
        ("2 Do the work", "Agents work in parallel and record what they used."),
        ("3 Check the draft", "The Reviewer labels claims it cannot verify."),
        ("4 You decide", "Approve the exact version, request a bounded revision, or reject."),
    )
    rows = "".join(
        f'<div class="ag-step"><div class="ag-step__label">{label}</div>'
        f'<div class="ag-step__text">{text}</div></div>'
        for label, text in steps
    )
    return f'<div class="ag-steps">{rows}</div>'


def render(services) -> None:
    settings = services.settings
    layout.page_header(
        "New task",
        "Describe what you need. A Planner will build a plan you can inspect before work starts.",
    )
    form_col, side_col = st.columns([2.2, 1], gap="large")

    with form_col:
        with st.container(border=True, key="ag-card-request"):
            st.markdown('<div class="ag-card-title">Your request</div>', unsafe_allow_html=True)
            with st.form("new_task_form", clear_on_submit=False):
                request = st.text_area(
                    "What do you need?",
                    value=SAMPLE_REQUEST,
                    height=110,
                    help="At least 8 characters. Describe the result you want.",
                )
                uploads = st.file_uploader(
                    f"Documents (max {settings.max_file_mb:g} MB each)",
                    type=["pdf", "txt", "docx"],
                    accept_multiple_files=True,
                    help="PDF, TXT, or DOCX. Files are treated as data, never as instructions.",
                )
                st.caption("If a file cannot be read, AegisFlow will tell you instead of guessing.")
                col1, col2 = st.columns(2)
                output_format = col1.selectbox(
                    "Output format",
                    ["markdown", "txt"],
                    format_func=lambda value: "Markdown (.md)" if value == "markdown" else "Plain text (.txt)",
                )
                manual_minutes = col2.number_input(
                    "Manual time estimate (minutes)",
                    min_value=0.0,
                    max_value=600.0,
                    value=45.0,
                    step=5.0,
                    help="Used only to estimate time saved; it is not a quality score.",
                )
                undisclosed_ack = st.checkbox(
                    "I understand that simulated output must be reviewed by a human and labeled if shared.",
                    value=settings.simulated,
                    disabled=not settings.simulated,
                )
                submitted = st.form_submit_button("Submit task", type="primary", width="stretch")

            if submitted:
                if len(request.strip()) < 8:
                    st.error("The request must contain at least 8 characters.")
                    return
                if settings.simulated and not undisclosed_ack:
                    st.error("Please acknowledge the simulated-output condition.")
                    return
                with st.status(
                    "Running the governed workflow...", expanded=True
                ) as status:
                    st.write("Planner → analysts → draft → assurance → human review")
                    _start(
                        services,
                        request.strip(),
                        output_format,
                        manual_minutes or None,
                        uploads,
                    )
                    status.update(label="Workflow started", state="complete")

    with side_col:
        with st.container(border=True, key="ag-card-next"):
            st.markdown('<div class="ag-card-title">What happens next</div>', unsafe_allow_html=True)
            st.markdown(_steps(), unsafe_allow_html=True)
            st.markdown(
                '<div class="ag-note">AegisFlow will not invent content. If no readable file is '
                "supplied, the task stops and tells you what is missing.</div>",
                unsafe_allow_html=True,
            )
            if not settings.simulated:
                st.warning(
                    "Real mode: extracted document text will be sent to the configured provider.",
                    icon=":material/dns:",
                )
